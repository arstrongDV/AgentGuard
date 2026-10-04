"""T2 (injection classifier) and T3 (LLM judge), each behind a gate.

Gates are what keep the hybrid design fast: most benign traffic is decided by T0/T1 in about a
millisecond and never pays for a model. Every skip is recorded with its reason in the pipeline timeline.
"""

import asyncio
import json
import re

from app.core.context import RequestContext, TextItem
from app.core.decision import CheckResult, Decision, Finding, Span
from app.core.pipeline import Runtime
from app.ml.judge import JudgeUnavailable

MIN_TEXT_CHARS = 20
MIN_WORDS = 3
WORD = re.compile(r"[^\W\d_]{2,}[.,!?;:'\")]*")  # letters (any script), trailing punctuation allowed
WORD_SPLIT = re.compile(r"\s+")
PLACEHOLDER_ONLY = re.compile(r"^(\s*\[[A-Z_]+_\d+\]\s*)+$")

# Granite Guardian risk names asked per stage
JUDGE_RISK = {"llm_in": "jailbreak", "llm_out": "harm", "mcp_call": "harm", "mcp_result": "jailbreak"}


# --- T2: injection classifier ------------------------------------------------


def classifiable(ctx: RequestContext) -> list[tuple[str, TextItem]]:
    """The natural-language text the classifier should see.

    The model is trained on prompts: it scores JSON *structure* as an injection (a plain CRM record gets 0.99).
    So JSON tool output is unpacked into its string values, and only values that read like sentences are
    classified. An instruction hidden in a `notes` field is a sentence; ids, emails and placeholders are not."""
    out: list[tuple[str, TextItem]] = []
    for item in ctx.texts:
        for text in _natural_language(item.value):
            out.append((text, item))
    return out


def _natural_language(value: str) -> list[str]:
    stripped = value.strip()
    if stripped[:1] in "{[":
        try:
            return [t for t in _string_leaves(json.loads(stripped)) if _is_sentence(t)]
        except ValueError:
            pass
    return [value] if _is_sentence(value) else []


def _string_leaves(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _string_leaves(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _string_leaves(v)]
    return []


def _is_sentence(text: str) -> bool:
    """At least MIN_WORDS real words (letters only): IBANs, ids and placeholders are not prose."""
    words = sum(1 for w in WORD_SPLIT.split(text) if WORD.fullmatch(w))
    return len(text) >= MIN_TEXT_CHARS and words >= MIN_WORDS and not PLACEHOLDER_ONLY.match(text)


def injection_gate(ctx: RequestContext, rt: Runtime, risk: float) -> str | None:
    classifier = rt.ml.classifier if rt.ml else None
    if classifier is None:
        return "ML disabled"
    if not classifier.ready:
        return f"model {classifier.status}"
    if not classifiable(ctx):
        return "no natural-language text"
    if ctx.stage == "mcp_result":
        return None  # tool output is the indirect-injection surface: always classified
    gate = ctx.agent.injection_gate
    if risk >= gate:
        return None
    return f"risk {risk:.2f} below gate {gate:g}"


async def injection(ctx: RequestContext, rt: Runtime) -> CheckResult:
    assert rt.ml and rt.ml.classifier
    candidates = classifiable(ctx)
    scores = await asyncio.to_thread(rt.ml.classifier.score_many, [text for text, _ in candidates])
    score, (_, item) = max(zip(scores, candidates), key=lambda pair: pair[0])
    control = rt.snapshot.policy.controls.prompt_injection
    threshold = ctx.agent.injection_threshold
    span = Span(start=0, end=0, field=item.path)
    if score >= threshold:
        return CheckResult(
            Decision.allow if control.action == "allow" else Decision.block,
            [Finding(check="injection", rule_id="ML-INJECTION", category="prompt_injection", severity="critical", score=round(score, 4),
                     message=f"injection classifier {score:.2f} ≥ threshold {threshold:g}", span=span)],
        )
    if score >= control.monitor_below:
        return CheckResult(
            Decision.allow,
            [Finding(check="injection", rule_id="ML-INJECTION-SUSPECT", category="prompt_injection", severity="medium",
                     score=round(score, 4), message=f"injection classifier {score:.2f}: suspicious, below threshold {threshold:g}", span=span)],
        )
    return CheckResult()


# --- T3: LLM judge -------------------------------------------------------------


def judge_gate(ctx: RequestContext, rt: Runtime, risk: float) -> str | None:
    judge = rt.ml.judge if rt.ml else None
    if not ctx.agent.judge_enabled:
        return "judge disabled by policy"
    if judge is None:
        return "judge not configured"
    if not judge.available():
        return f"judge unavailable: {judge.detail or 'Ollama offline'}"
    if not any(len(t.value) >= MIN_TEXT_CHARS for t in ctx.texts) and ctx.stage != "mcp_call":
        return "no text to judge"
    policy = rt.snapshot.policy
    if ctx.tool and ctx.stage == "mcp_call" and (ctx.tool.name in policy.high_risk_tools or ctx.agent.strictness == "high"):
        return None  # high-risk actions always get a second opinion
    low = policy.controls.llm_judge.only_for_risk_above
    if ctx.agent.strictness == "high":
        low = min(low, 0.3)
    high = ctx.agent.injection_threshold
    if low <= risk < high:
        return None
    return f"risk {risk:.2f} outside the uncertain band [{low:g}, {high:g})"


async def llm_judge(ctx: RequestContext, rt: Runtime) -> CheckResult:
    assert rt.ml and rt.ml.judge
    control = rt.snapshot.policy.controls.llm_judge
    risk_name = JUDGE_RISK[ctx.stage]
    text = "\n".join(t.value for t in ctx.texts)
    if ctx.stage == "mcp_call" and ctx.tool:
        text = f"Tool call: {ctx.tool.name}({text})"
    try:
        verdict = await rt.ml.judge.ask(control.model, risk_name, text, control.timeout_s)
    except JudgeUnavailable as e:
        return CheckResult(skipped_reason=f"judge unavailable: {e}")  # degraded to the cheaper tiers
    except TimeoutError as e:
        blocked = control.on_timeout == "block"
        return CheckResult(
            Decision.block if blocked else Decision.allow,
            [Finding(check="llm_judge", rule_id="JUDGE-TIMEOUT", category="availability", severity="medium" if blocked else "low",
                     score=1.0 if blocked else 0.0, message=f"{e}; policy on_timeout={control.on_timeout}")],
        )
    if not verdict.risky:
        return CheckResult()
    return CheckResult(
        Decision.block,
        [Finding(check="llm_judge", rule_id=f"JUDGE-{risk_name.upper()}", category="prompt_injection" if risk_name == "jailbreak" else "harmful_content",
                 severity="high", score=verdict.score, message=f"{control.model} flagged this as '{risk_name}'" + (" (cached)" if verdict.cached else ""))],
    )


# --- T1: tool calls proposed by the model --------------------------------------


async def output_tool_calls(ctx: RequestContext, rt: Runtime) -> CheckResult:
    """The model wants the agent to call a tool this agent may not use: usually an injection that worked.
    Caught here even when the agent runs the tool itself instead of through our MCP proxy."""
    if not ctx.proposed_tools:
        return CheckResult()
    visible = set(ctx.agent.tools_allowed) | set(ctx.agent.tools_need_approval)
    forbidden = [name for name in ctx.proposed_tools if name not in visible]
    if not forbidden:
        return CheckResult()
    action = rt.snapshot.policy.controls.output_tool_calls.action
    return CheckResult(
        Decision.block if action == "block" else Decision.allow,
        [Finding(check="output_tool_calls", rule_id="TOOL-CALL-NOT-ALLOWED", category="tool_acl", severity="high", score=1.0,
                 message=f"model proposed calling {', '.join(forbidden)}, which {ctx.agent.id} may not use")],
    )
