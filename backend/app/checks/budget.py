"""T0 gates: rate limit, token/USD budgets, tool calls per task, loop detection."""

import hashlib
import json

from app.core.context import RequestContext
from app.core.decision import CheckResult, Decision, Finding
from app.core.pipeline import Runtime


def _block(check: str, rule_id: str, message: str) -> CheckResult:
    return CheckResult(Decision.block, [Finding(check=check, rule_id=rule_id, category="budget", severity="medium", score=1.0, message=message)])


async def rate_limit(ctx: RequestContext, rt: Runtime) -> CheckResult:
    limit = ctx.agent.requests_per_minute
    count = rt.state.hit_rate(ctx.agent.id)
    if count > limit:
        return _block("rate_limit", "RATE-LIMIT", f"{count} requests in the last minute (limit {limit})")
    return CheckResult()


async def budget(ctx: RequestContext, rt: Runtime) -> CheckResult:
    """Pre-check: refuse new LLM calls once today's budget is spent. Spend is recorded after each response."""
    limits, usage = ctx.agent.budget, rt.state.usage(ctx.agent.id)
    if limits.tokens_per_day is not None and usage.tokens >= limits.tokens_per_day:
        return _block("budget", "BUDGET-TOKENS", f"daily token budget used: {usage.tokens}/{limits.tokens_per_day}")
    if limits.usd_per_day is not None and usage.usd >= limits.usd_per_day:
        return _block("budget", "BUDGET-USD", f"daily cost budget used: ${usage.usd:.4f}/${limits.usd_per_day:.2f}")
    return CheckResult()


async def task_tool_calls(ctx: RequestContext, rt: Runtime) -> CheckResult:
    limit = ctx.agent.budget.max_tool_calls_per_task
    if limit is None:
        return CheckResult()
    count = rt.state.hit_task(ctx.agent.id, ctx.task_id)
    if count > limit:
        return _block("budget", "TASK-TOOL-CALLS", f"{count} tool calls in task {ctx.task_id} (limit {limit})")
    return CheckResult()


async def loop_detection(ctx: RequestContext, rt: Runtime) -> CheckResult:
    assert ctx.tool is not None
    canonical = json.dumps(ctx.arguments, sort_keys=True, default=str)
    key = hashlib.sha256(f"{ctx.agent.id}|{ctx.tool.server}|{ctx.tool.name}|{canonical}".encode()).hexdigest()
    previous = rt.state.hit_loop(key, ctx.agent.loop_window_s)
    limit = ctx.agent.loop_max_repeats
    if previous >= limit:
        return CheckResult(
            Decision.block,
            [Finding(check="loop", rule_id="LOOP-DETECTED", category="budget", severity="high", score=1.0,
                     message=f"same call {ctx.tool.name} repeated {previous + 1}× within {ctx.agent.loop_window_s}s (limit {limit})")],
        )
    return CheckResult()
