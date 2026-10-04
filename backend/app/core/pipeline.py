"""The check pipeline: the only place that knows about check ordering, tiers and short-circuiting."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter

from app.core.context import RequestContext
from app.core.decision import CheckResult, CheckTiming, Decision, Finding, combine, risk_score
from app.core.text import joined
from app.ml import MLRuntime
from app.policy.feed import SignatureFeed, Stage
from app.policy.store import PolicySnapshot
from app.state import State

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Runtime:
    """Everything a check may read. One instance per request."""

    snapshot: PolicySnapshot
    feed: SignatureFeed
    state: State
    ml: MLRuntime | None = None


CheckFn = Callable[[RequestContext, Runtime], Awaitable[CheckResult]]
# Gate: (ctx, runtime, risk so far) -> reason to skip, or None to run. This is how expensive checks
# (ML classifier, LLM judge) only run when the cheap tiers say the traffic is worth a closer look.
GateFn = Callable[[RequestContext, Runtime, float], str | None]


@dataclass(frozen=True)
class Check:
    name: str
    tier: int
    stages: frozenset[Stage]
    run: CheckFn
    gate: GateFn | None = None


@dataclass
class PipelineResult:
    decision: Decision
    monitor_only: bool
    would_have: Decision | None
    risk: float
    findings: list[Finding]
    timings: list[CheckTiming]
    total_ms: float
    original_text: str
    redacted_text: str
    blocking: Finding | None  # the finding that caused block / needs_approval

    @property
    def enforced_block(self) -> bool:
        return self.decision == Decision.block


async def run_pipeline(ctx: RequestContext, rt: Runtime, checks: list[Check]) -> PipelineResult:
    start = perf_counter()
    original = joined(ctx.texts)
    decision = Decision.allow
    blocking: Finding | None = None
    blocked_tier: int | None = None
    redacted = False

    for check in checks:
        if ctx.stage not in check.stages:
            continue
        if blocked_tier is not None and check.tier > blocked_tier:
            ctx.timings.append(
                CheckTiming(check=check.name, tier=check.tier, ms=0.0, skipped_reason=f"short-circuit: blocked in T{blocked_tier}")
            )
            continue

        if check.gate is not None:
            reason = check.gate(ctx, rt, risk_score(ctx.findings))
            if reason is not None:
                ctx.timings.append(CheckTiming(check=check.name, tier=check.tier, ms=0.0, skipped_reason=reason))
                continue

        t0 = perf_counter()
        try:
            result = await check.run(ctx, rt)
        except Exception as e:  # a broken check must never take the gateway down: fail open, but record it
            log.exception("check %s failed", check.name)
            result = CheckResult(
                findings=[Finding(check=check.name, rule_id="CHECK-ERROR", category="internal", severity="low", score=0.0, message=str(e))]
            )
        ctx.timings.append(CheckTiming(check=check.name, tier=check.tier, ms=round((perf_counter() - t0) * 1000, 3)))

        ctx.findings.extend(result.findings)
        for index, text in result.replacements.items():
            ctx.texts[index].value = text
            redacted = True
        if result.decision in (Decision.block, Decision.needs_approval) and result.findings:
            if blocking is None or (result.decision == Decision.block and decision != Decision.block):
                blocking = result.findings[0]
        decision = combine(decision, result.decision)
        if decision == Decision.block and blocked_tier is None:
            blocked_tier = check.tier

    if decision == Decision.redact and not redacted:
        decision = Decision.allow

    monitor_only, would_have = False, None
    if ctx.agent.mode == "monitor" and decision in (Decision.block, Decision.needs_approval):
        monitor_only, would_have = True, decision
        decision = Decision.redact if redacted else Decision.allow

    return PipelineResult(
        decision=decision,
        monitor_only=monitor_only,
        would_have=would_have,
        risk=risk_score(ctx.findings),
        findings=ctx.findings,
        timings=ctx.timings,
        total_ms=round((perf_counter() - start) * 1000, 3),
        original_text=original,
        redacted_text=joined(ctx.texts),
        blocking=blocking,
    )


def block_message(result: PipelineResult, what: str = "Request") -> str:
    f = result.blocking
    if f is None:
        return f"[AgentGuard] {what} blocked by policy."
    return f"[AgentGuard] {what} blocked: {f.message} ({f.rule_id})"
