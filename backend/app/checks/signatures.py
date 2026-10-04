"""T1: historical attack signatures from the feed, plus the policy's banned topics."""

import re
import unicodedata

from app.checks.redact import Match, apply_placeholders
from app.core.context import RequestContext
from app.core.decision import CheckResult, Decision, Finding, Span, combine
from app.core.pipeline import Runtime

ZERO_WIDTH = re.compile(r"[​‌‍⁠﻿]")
WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Defeat simple obfuscation: Unicode compatibility forms, zero-width characters, odd whitespace."""
    return WHITESPACE.sub(" ", ZERO_WIDTH.sub("", unicodedata.normalize("NFKC", text)))


async def signatures(ctx: RequestContext, rt: Runtime) -> CheckResult:
    compiled = rt.feed.by_stage.get(ctx.stage, [])
    result = CheckResult()
    for index, item in enumerate(ctx.texts):
        normalized = normalize(item.value)
        to_redact: list[Match] = []
        for c in compiled:
            sig = c.sig
            m = c.regex.search(item.value if sig.match_on == "raw" else normalized)
            if not m:
                continue
            exact = sig.match_on == "raw" or normalized == item.value  # offsets are only exact on the raw text
            span = Span(start=m.start(), end=m.end(), field=item.path) if exact else Span(start=0, end=0, field=item.path)
            result.findings.append(Finding(
                check="signatures", rule_id=sig.id, category=sig.category, severity=sig.severity, score=1.0,
                message=sig.description or f"signature {sig.id} matched", span=span,
            ))
            if sig.action == "redact":
                # redact on the raw text so the rest of the content is untouched
                to_redact += [Match(r.start(), r.end(), "REMOVED_LINK", sig.id) for r in c.regex.finditer(item.value)]
            result.decision = combine(result.decision, Decision(sig.action))
        if to_redact:
            result.replacements[index] = apply_placeholders(item.value, to_redact, lambda kind, _value: f"[{kind}]")
    return result


async def banned_topics(ctx: RequestContext, rt: Runtime) -> CheckResult:
    terms = ctx.agent.banned_terms
    if not terms:
        return CheckResult()
    pattern = re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.IGNORECASE)
    result = CheckResult()
    for item in ctx.texts:
        m = pattern.search(normalize(item.value))
        if m:
            result.findings.append(Finding(
                check="banned_topics", rule_id="TOPIC-BANNED", category="banned_topic", severity="medium", score=1.0,
                message=f"banned topic '{m.group(1).lower()}'", span=Span(start=0, end=0, field=item.path),
            ))
    if result.findings and ctx.agent.banned_action == "block":
        result.decision = Decision.block
    return result
