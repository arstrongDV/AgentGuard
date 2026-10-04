"""Dashboard API: health, metrics, budgets, policy, approvals, audit export."""

import csv
import io
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from ruamel.yaml import YAML

from app.api.common import get_services, require_admin
from app.core.events import AuditEvent
from app.core.ids import iso
from app.metrics import MAX_EVENTS, compute_metrics, window_start
from app.policy.store import PolicyError, parse_policy
from app.services import Services

router = APIRouter(tags=["dashboard"])


@router.get("/health")
async def health(svc: Services = Depends(get_services)):
    return {
        "status": "ok",
        "environment": svc.settings.environment,
        "llm": await svc.provider.status(),
        "ml": svc.ml.classifier.status if svc.ml.classifier else "disabled",
        "ml_detail": svc.ml.classifier.detail if svc.ml.classifier else "",
        "judge": await svc.judge_status(),
        "policy_version": svc.policy.current().version,
        "feed_version": svc.feed.version,
        "signatures": svc.feed.count,
    }


# --- metrics & budgets ----------------------------------------------------


@router.get("/api/metrics")
def metrics(window: Literal["15m", "1h", "24h"] = "15m", svc: Services = Depends(get_services)):
    now = datetime.now(UTC)
    events = svc.audit.query(limit=MAX_EVENTS, since=iso(window_start(window, now)), ascending=True)
    return compute_metrics(events, window, now)


@router.get("/api/budgets")
def budgets(svc: Services = Depends(get_services)):
    snapshot = svc.policy.current()
    out = []
    for agent_id, agent in snapshot.agents.items():
        usage = svc.state.usage(agent_id)
        models = usage.by_model
        out.append({
            "agent_id": agent_id,
            "tokens": {"used": usage.tokens, "limit": agent.budget.tokens_per_day},
            "usd": {"used": round(usage.usd, 6), "limit": agent.budget.usd_per_day,
                    "virtual": bool(models) and all(m.virtual for m in models.values())},
            "by_model": [{"model": name, "tokens": m.tokens, "usd": round(m.usd, 6)} for name, m in sorted(models.items())],
            "rate": {"rpm": svc.state.rpm(agent_id), "limit": agent.requests_per_minute},
            "blocked_today": svc.state.blocked_today(agent_id),
            "resets_in_s": svc.state.seconds_until_reset(),
        })
    return out


# --- policy ---------------------------------------------------------------


@router.get("/api/policy")
def get_policy(svc: Services = Depends(get_services)):
    snapshot = svc.policy.current()
    return {
        "version": snapshot.version,
        "yaml": svc.settings.policy_path.read_text(encoding="utf-8"),
        "effective": {
            "mode": snapshot.policy.mode,
            "strictness": snapshot.policy.strictness,
            "feed": {"version": svc.feed.version, "signatures": svc.feed.count},
            "agents": {agent_id: a.model_dump(mode="json") for agent_id, a in snapshot.agents.items()},
        },
    }


@router.patch("/api/policy", dependencies=[Depends(require_admin)])
def patch_policy(patch: dict[str, Any] = Body(...), svc: Services = Depends(get_services)):
    """JSON merge-patch (RFC 7396) applied to policy.yaml. Comments and layout are preserved.
    The file stays the single source of truth: we write it, then reload from it."""
    path: Path = svc.settings.policy_path
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096  # never re-wrap the hand-written inline mappings
    document = yaml.load(path.read_text(encoding="utf-8"))
    merge_patch(document, patch)
    buffer = io.StringIO()
    yaml.dump(document, buffer)
    new_text = buffer.getvalue()
    try:
        snapshot = parse_policy(new_text.encode(), path.parent)
    except PolicyError as e:
        return JSONResponse({"error": e.message, "path": _first_path(patch)}, status_code=422)
    write_atomic(path, new_text)
    svc.reload_policy()
    return {"version": snapshot.version}


def merge_patch(target: Any, patch: Any) -> Any:
    if not isinstance(patch, dict):
        return patch
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_patch(target[key], value)
        else:
            target[key] = value
    return target


def _first_path(patch: Any, prefix: str = "") -> str:
    if isinstance(patch, dict) and len(patch) == 1:
        key, value = next(iter(patch.items()))
        return _first_path(value, f"{prefix}.{key}" if prefix else str(key))
    return prefix


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:  # e.g. a single file bind-mounted into a container cannot be replaced
        tmp.unlink(missing_ok=True)
        path.write_text(text, encoding="utf-8")


# --- approvals ------------------------------------------------------------


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "deny"]
    note: str | None = None


@router.get("/api/approvals")
def list_approvals(status: Literal["pending", "approved", "denied", "timeout"] | None = None, svc: Services = Depends(get_services)):
    return [a.model_dump(mode="json") for a in svc.approvals.list(status)]


@router.post("/api/approvals/{approval_id}", dependencies=[Depends(require_admin)])
def resolve_approval(approval_id: str, body: ApprovalDecision, svc: Services = Depends(get_services)):
    try:
        approval = svc.approvals.resolve(approval_id, body.decision, body.note)
    except KeyError:
        if any(a.id == approval_id for a in svc.approvals.list()):
            raise HTTPException(status_code=409, detail="approval already resolved") from None
        raise HTTPException(status_code=404, detail="approval not found") from None
    return approval.model_dump(mode="json")


# --- audit export ---------------------------------------------------------

CSV_COLUMNS = ["id", "ts", "trace_id", "task_id", "agent_id", "channel", "direction", "decision", "monitor_only", "would_have",
               "risk", "rules", "categories", "model", "tool", "summary", "total_ms", "upstream_ms", "prompt_tokens",
               "completion_tokens", "cost_usd", "error", "policy_version"]


@router.get("/api/audit/export")
def export_audit(
    format: Literal["csv", "jsonl"] = "csv",
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    agent: str | None = None,
    svc: Services = Depends(get_services),
):
    events = svc.audit.iterate(since=from_, until=to, agent=agent)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    if format == "jsonl":
        body: Iterator[str] = (e.model_dump_json() + "\n" for e in events)
        media = "application/x-ndjson"
    else:
        body = csv_rows(events)
        media = "text/csv"
    return StreamingResponse(body, media_type=media,
                             headers={"content-disposition": f'attachment; filename="agentguard-audit-{stamp}.{format}"'})


def csv_rows(events: Iterator[AuditEvent]) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for e in events:
        writer.writerow([
            e.id, e.ts, e.trace_id, e.task_id, e.agent_id, e.channel, e.direction, e.decision.value, e.monitor_only,
            e.would_have.value if e.would_have else "", e.risk, " ".join(f.rule_id for f in e.findings),
            " ".join(sorted({f.category for f in e.findings})), e.model or "",
            f"{e.tool.server}.{e.tool.name}" if e.tool else "", e.summary, e.total_ms, e.upstream_ms or "",
            e.tokens.prompt if e.tokens else "", e.tokens.completion if e.tokens else "",
            e.cost_usd if e.cost_usd is not None else "", e.error or "", e.policy_version,
        ])
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()
    yield buffer.getvalue()

