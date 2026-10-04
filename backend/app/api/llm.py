"""LLM Gateway: OpenAI-compatible /v1/chat/completions and /v1/models in front of Ollama."""

import json
import time
from collections.abc import Iterator
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from app.api.common import TASK_HEADER, build_event, decision_headers, get_services, identify_agent
from app.checks import CHECKS
from app.core.context import Redactor, RequestContext
from app.core.decision import Decision, combine
from app.core.events import Tokens
from app.core.ids import ulid
from app.core.pipeline import PipelineResult, block_message, run_pipeline
from app.core.text import apply_strings, chat_request_texts, chat_response_texts
from app.policy.effective import EffectiveAgent
from app.providers import UpstreamError
from app.services import Services

router = APIRouter(tags=["llm gateway"])


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[dict[str, Any]]
    stream: bool = False


def openai_error(status: int, message: str, type_: str, code: str | None = None, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": type_, "code": code}}, status_code=status, headers=headers)


def authenticate(request: Request, svc: Services, channel: str) -> EffectiveAgent | None:
    key = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    return identify_agent(svc, key or None, channel)


@router.post("/v1/chat/completions")
async def chat_completions(body: ChatCompletionRequest, request: Request, svc: Services = Depends(get_services)):
    agent = authenticate(request, svc, "llm")
    if agent is None:
        return openai_error(401, "Invalid or missing AgentGuard agent key", "invalid_api_key")

    rt = svc.runtime()
    version = rt.snapshot.version
    trace_id = ulid()
    task_id = request.headers.get(TASK_HEADER) or trace_id
    redactor = Redactor()
    payload = body.model_dump(exclude={"stream"})
    payload.pop("stream_options", None)

    # --- request side -------------------------------------------------
    ctx_in = RequestContext(trace_id, task_id, agent, "llm_in", chat_request_texts(payload), redactor, model=body.model)
    result_in = await run_pipeline(ctx_in, rt, CHECKS)
    svc.emit(build_event(ctx_in, result_in, version))
    if result_in.decision == Decision.block:
        return blocked_response(body, result_in, rt.snapshot.policy.block_status_code, trace_id)
    apply_strings(payload, ctx_in.texts)

    # --- upstream -----------------------------------------------------
    t0 = perf_counter()
    try:
        upstream = await svc.provider.chat(payload)
    except UpstreamError as e:
        ctx_err = RequestContext(trace_id, task_id, agent, "llm_out", [], redactor, model=body.model)
        svc.emit(build_event(ctx_err, None, version, summary="upstream LLM error", error=str(e),
                             upstream_ms=round((perf_counter() - t0) * 1000, 1)))
        return openai_error(502, str(e), "upstream_error", headers={"x-agentguard-trace-id": trace_id})
    upstream_ms = round((perf_counter() - t0) * 1000, 1)

    # --- response side ------------------------------------------------
    ctx_out = RequestContext(trace_id, task_id, agent, "llm_out", chat_response_texts(upstream), redactor, model=body.model,
                             proposed_tools=proposed_tool_names(upstream))
    result_out = await run_pipeline(ctx_out, rt, CHECKS)
    if result_out.decision == Decision.block:
        replace_choices(upstream, block_message(result_out, "Response"))
    else:
        apply_strings(upstream, ctx_out.texts)

    tokens, cost, virtual = account_usage(svc, agent, body.model, upstream)
    svc.emit(build_event(ctx_out, result_out, version, upstream_ms=upstream_ms, tokens=tokens, cost_usd=cost, cost_virtual=virtual))

    headers = decision_headers(trace_id, combine(result_in.decision, result_out.decision), max(result_in.risk, result_out.risk))
    if body.stream:
        return StreamingResponse(as_sse_chunks(upstream), media_type="text/event-stream", headers=headers)
    return JSONResponse(upstream, headers=headers)


@router.get("/v1/models")
async def list_models(request: Request, svc: Services = Depends(get_services)):
    agent = authenticate(request, svc, "llm")
    if agent is None:
        return openai_error(401, "Invalid or missing AgentGuard agent key", "invalid_api_key")
    return {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "agentguard"} for m in agent.models_allowed]}


# --- helpers -------------------------------------------------------------


def blocked_response(body: ChatCompletionRequest, result: PipelineResult, status_code: int, trace_id: str):
    message = block_message(result)
    headers = decision_headers(trace_id, Decision.block, result.risk)
    if status_code == 403:
        code = result.blocking.rule_id if result.blocking else None
        return openai_error(403, message, "agentguard_blocked", code, headers)
    completion = {
        "id": f"chatcmpl-agentguard-{trace_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": message}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    if body.stream:
        return StreamingResponse(as_sse_chunks(completion), media_type="text/event-stream", headers=headers)
    return JSONResponse(completion, headers=headers)


def proposed_tool_names(completion: dict[str, Any]) -> list[str]:
    return [
        str((call.get("function") or {}).get("name", ""))
        for choice in completion.get("choices") or []
        for call in (choice.get("message") or {}).get("tool_calls") or []
    ]


def replace_choices(completion: dict[str, Any], message: str) -> None:
    for choice in completion.get("choices") or []:
        choice["message"] = {"role": "assistant", "content": message}
        choice["finish_reason"] = "stop"


def account_usage(svc: Services, agent: EffectiveAgent, model: str, completion: dict[str, Any]) -> tuple[Tokens | None, float | None, bool | None]:
    usage = completion.get("usage")
    if not usage:
        return None, None, None
    tokens = Tokens(prompt=usage.get("prompt_tokens", 0), completion=usage.get("completion_tokens", 0))
    price = svc.policy.current().policy.costs.get(model)
    cost = round((tokens.prompt * price.input + tokens.completion * price.output) / 1000, 6) if price else 0.0
    virtual = price.virtual if price else False
    svc.state.add_usage(agent.id, model, tokens.prompt + tokens.completion, cost, virtual)
    return tokens, cost, virtual


def as_sse_chunks(completion: dict[str, Any]) -> Iterator[str]:
    """Re-emit a buffered completion as OpenAI stream chunks. Output checks need the whole text first,
    so streaming is buffered: the client still gets a valid stream, just in one content chunk."""
    base = {"id": completion.get("id"), "object": "chat.completion.chunk", "created": completion.get("created"), "model": completion.get("model")}
    for choice in completion.get("choices") or []:
        message = choice.get("message") or {}
        delta: dict[str, Any] = {"role": "assistant", "content": message.get("content")}
        if message.get("tool_calls"):
            delta["tool_calls"] = [{"index": i, **call} for i, call in enumerate(message["tool_calls"])]
        index = choice.get("index", 0)
        yield f"data: {json.dumps({**base, 'choices': [{'index': index, 'delta': delta, 'finish_reason': None}]})}\n\n"
        yield f"data: {json.dumps({**base, 'choices': [{'index': index, 'delta': {}, 'finish_reason': choice.get('finish_reason', 'stop')}]})}\n\n"
    yield "data: [DONE]\n\n"
