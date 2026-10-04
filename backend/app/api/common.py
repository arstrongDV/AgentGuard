import secrets
from typing import Any

from fastapi import HTTPException, Request

from app.core.context import RequestContext
from app.core.decision import Decision, Finding
from app.core.events import AuditEvent, Tokens, ToolRef, summarize, truncate
from app.core.ids import iso, ulid, utcnow
from app.core.pipeline import PipelineResult
from app.policy.effective import EffectiveAgent
from app.services import Services

TASK_HEADER = "x-agentguard-task"


def get_services(request: Request) -> Services:
    return request.app.state.services


def require_admin(request: Request) -> None:
    """Mutating dashboard endpoints need `Authorization: Bearer <ADMIN_TOKEN>`."""
    svc = get_services(request)
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, svc.settings.admin_token):
        raise HTTPException(status_code=401, detail="admin token required")


def identify_agent(svc: Services, api_key: str | None, channel: str) -> EffectiveAgent | None:
    """Look the key up in the policy. Unknown keys are audited, so brute force shows up in the feed."""
    agent = svc.policy.current().agent_for_key(api_key) if api_key else None
    if agent is None:
        trace = ulid()
        svc.emit(AuditEvent(
            id=ulid(), ts=iso(utcnow()), trace_id=trace, task_id=trace, agent_id="unknown",
            channel=channel, direction="request", decision=Decision.block, risk=0.6,  # type: ignore[arg-type]
            findings=[Finding(check="auth", rule_id="AUTH-UNKNOWN-KEY", category="auth", severity="medium", score=1.0,
                              message="missing or unknown agent key")],
            summary="rejected: missing or unknown agent key", policy_version=svc.policy.current().version,
        ))
    return agent


def build_event(
    ctx: RequestContext,
    result: PipelineResult | None,
    policy_version: str,
    *,
    summary: str | None = None,
    decision: Decision | None = None,
    findings: list[Finding] | None = None,
    model: str | None = None,
    tool: ToolRef | None = None,
    upstream_ms: float | None = None,
    tokens: Tokens | None = None,
    cost_usd: float | None = None,
    cost_virtual: bool | None = None,
    approval_id: str | None = None,
    error: str | None = None,
) -> AuditEvent:
    """One audit event per pipeline run (request or response). Fields can be overridden for
    events that are not a plain pipeline result (approval outcome, upstream error)."""
    redacted = result.redacted_text if result else ""
    return AuditEvent(
        id=ulid(),
        ts=iso(utcnow()),
        trace_id=ctx.trace_id,
        task_id=ctx.task_id,
        agent_id=ctx.agent.id,
        channel=ctx.channel,  # type: ignore[arg-type]
        direction=ctx.direction,  # type: ignore[arg-type]
        model=model or ctx.model,
        tool=tool or ctx.tool,
        decision=decision or (result.decision if result else Decision.allow),
        monitor_only=result.monitor_only if result else False,
        would_have=result.would_have if result else None,
        risk=result.risk if result else 0.0,
        findings=findings if findings is not None else (result.findings if result else []),
        summary=summary if summary is not None else summarize(redacted),
        original_text=truncate(result.original_text) if result else None,
        redacted_text=truncate(redacted) if result else None,
        timings=result.timings if result else [],
        total_ms=result.total_ms if result else 0.0,
        upstream_ms=upstream_ms,
        tokens=tokens,
        cost_usd=cost_usd,
        cost_virtual=cost_virtual,
        approval_id=approval_id,
        error=error,
        policy_version=policy_version,
    )


def decision_headers(trace_id: str, decision: Decision, risk: float) -> dict[str, Any]:
    return {"x-agentguard-decision": decision.value, "x-agentguard-trace-id": trace_id, "x-agentguard-risk": f"{risk:.2f}"}
