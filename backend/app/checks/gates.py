"""T0 gates: model allowlist and tool ACL (least privilege)."""

import re

from app.core.context import RequestContext
from app.core.decision import CheckResult, Decision, Finding
from app.core.pipeline import Runtime
from app.policy.models import ArgConstraint


async def model_allowlist(ctx: RequestContext, rt: Runtime) -> CheckResult:
    allowed = ctx.agent.models_allowed
    if not allowed or ctx.model in allowed:
        return CheckResult()
    return CheckResult(
        Decision.block,
        [Finding(check="model_allowlist", rule_id="MODEL-NOT-ALLOWED", category="supply_chain", severity="high", score=1.0,
                 message=f"model '{ctx.model}' is not allowed for {ctx.agent.id}")],
    )


async def tool_acl(ctx: RequestContext, rt: Runtime) -> CheckResult:
    assert ctx.tool is not None
    agent, name = ctx.agent, ctx.tool.name

    if name in agent.tools_need_approval:
        decision = Decision.needs_approval
        findings = [Finding(check="tool_acl", rule_id="TOOL-NEEDS-APPROVAL", category="tool_acl", severity="medium", score=0.5,
                            message=f"tool '{name}' requires human approval")]
    elif name in agent.tools_allowed:
        decision, findings = Decision.allow, []
    else:
        return CheckResult(
            Decision.block,
            [Finding(check="tool_acl", rule_id="TOOL-NOT-ALLOWED", category="tool_acl", severity="high", score=1.0,
                     message=f"tool '{name}' is not allowed for {agent.id}")],
        )

    for arg, constraint in agent.tool_args.get(name, {}).items():
        value = ctx.arguments.get(arg)
        if value is None:
            continue
        problem = _violation(value, constraint)
        if problem:
            decision = Decision.block
            findings.insert(0, Finding(check="tool_acl", rule_id="TOOL-ARG-CONSTRAINT", category="tool_acl", severity="high", score=1.0,
                                       message=f"{name}.{arg} {problem}"))
    return CheckResult(decision, findings)


def _violation(value: object, c: ArgConstraint) -> str | None:
    if c.pattern is not None and not re.search(c.pattern, str(value)):
        return f"'{value}' does not match /{c.pattern}/"
    if c.allowed is not None and value not in c.allowed:
        return f"'{value}' is not one of {c.allowed}"
    if c.max is not None or c.min is not None:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return f"'{value}' is not a number"
        if c.max is not None and number > c.max:
            return f"{number:g} exceeds the maximum of {c.max:g}"
        if c.min is not None and number < c.min:
            return f"{number:g} is below the minimum of {c.min:g}"
    return None
