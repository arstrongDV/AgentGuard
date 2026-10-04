"""T1: PII detection with checksum validation (IBAN mod-97, card Luhn) to keep false positives low."""

import re

from app.checks.redact import Match, apply_placeholders, non_overlapping
from app.core.context import RequestContext
from app.core.decision import CheckResult, Decision, Finding, Span
from app.core.pipeline import Runtime

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")
CARD = re.compile(r"(?<![\d+])(?:\d[ -]?){12,18}\d(?!\d)")
PHONE_INTL = re.compile(r"(?<![\w+])\+\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{2,4}){2,4}\b")
PHONE_US = re.compile(r"(?<![\d+])\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")

PRIORITY = ["EMAIL", "IBAN", "CREDIT_CARD", "PHONE"]
SEVERITY = {"EMAIL": "medium", "PHONE": "medium", "IBAN": "high", "CREDIT_CARD": "high"}


def iban_valid(candidate: str) -> bool:
    s = candidate.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    rearranged = s[4:] + s[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def luhn_valid(candidate: str) -> bool:
    digits = [int(d) for d in candidate if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def find_pii(text: str, entities: list[str]) -> list[Match]:
    found: list[Match] = []
    if "EMAIL" in entities:
        found += [Match(m.start(), m.end(), "EMAIL", "PII-EMAIL") for m in EMAIL.finditer(text)]
    if "IBAN" in entities:
        found += [Match(m.start(), m.end(), "IBAN", "PII-IBAN") for m in IBAN.finditer(text) if iban_valid(m.group())]
    if "CREDIT_CARD" in entities:
        found += [Match(m.start(), m.end(), "CREDIT_CARD", "PII-CREDIT-CARD") for m in CARD.finditer(text) if luhn_valid(m.group())]
    if "PHONE" in entities:
        for pattern in (PHONE_INTL, PHONE_US):
            found += [Match(m.start(), m.end(), "PHONE", "PII-PHONE") for m in pattern.finditer(text)]
    return non_overlapping(found, PRIORITY)


async def pii(ctx: RequestContext, rt: Runtime) -> CheckResult:
    agent = ctx.agent
    action = {
        "llm_in": agent.pii_in_action,
        "llm_out": agent.pii_out_action,
        "mcp_call": agent.pii_tool_args_action,
        "mcp_result": agent.pii_result_action,
    }[ctx.stage]
    result = CheckResult()
    for index, item in enumerate(ctx.texts):
        matches = find_pii(item.value, agent.pii_entities)
        if not matches:
            continue
        for m in matches:
            result.findings.append(Finding(
                check="pii", rule_id=m.rule_id, category="pii", severity=SEVERITY[m.kind],
                score=1.0 if m.kind in ("IBAN", "CREDIT_CARD") else 0.9,
                message=f"{m.kind.replace('_', ' ').lower()} detected", span=Span(start=m.start, end=m.end, field=item.path),
            ))
        if action == "redact":
            result.replacements[index] = apply_placeholders(item.value, matches, ctx.redactor.placeholder)
    if result.findings:
        result.decision = {"redact": Decision.redact, "block": Decision.block, "allow": Decision.allow}[action]
    return result
