"""T1: credentials and keys. Block inbound (an agent should never send them), redact outbound."""

import math
import re
from collections import Counter
from dataclasses import dataclass

from app.checks.redact import Match, apply_placeholders, non_overlapping
from app.core.context import RequestContext
from app.core.decision import CheckResult, Decision, Finding, Span
from app.core.pipeline import Runtime


@dataclass(frozen=True)
class SecretPattern:
    rule_id: str
    regex: re.Pattern[str]
    label: str
    group: int = 0  # which group is the secret itself
    min_entropy: float = 0.0


PATTERNS = [
    SecretPattern("SECRET-AWS-KEY", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "AWS access key"),
    SecretPattern("SECRET-GITHUB-TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b"), "GitHub token"),
    SecretPattern("SECRET-SLACK-TOKEN", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    SecretPattern("SECRET-API-KEY", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"), "API key"),
    SecretPattern("SECRET-PRIVATE-KEY", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"), "private key"),
    SecretPattern("SECRET-JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "JWT"),
    SecretPattern(
        "SECRET-GENERIC",
        re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|token)\b\s*[:=]\s*[\"']?([^\s\"']{8,})"),
        "credential assignment",
        group=2,
        min_entropy=3.0,
    ),
]


def shannon_entropy(value: str) -> float:
    counts = Counter(value)
    return -sum(c / len(value) * math.log2(c / len(value)) for c in counts.values())


def find_secrets(text: str) -> list[Match]:
    found = []
    for p in PATTERNS:
        for m in p.regex.finditer(text):
            value = m.group(p.group)
            if shannon_entropy(value) >= p.min_entropy:
                found.append(Match(m.start(p.group), m.end(p.group), "SECRET", p.rule_id))
    return non_overlapping(found, ["SECRET"])


async def secrets(ctx: RequestContext, rt: Runtime) -> CheckResult:
    action = ctx.agent.secrets_in_action if ctx.inbound else ctx.agent.secrets_out_action
    labels = {p.rule_id: p.label for p in PATTERNS}
    result = CheckResult()
    for index, item in enumerate(ctx.texts):
        matches = find_secrets(item.value)
        if not matches:
            continue
        for m in matches:
            result.findings.append(Finding(
                check="secrets", rule_id=m.rule_id, category="secret", severity="critical", score=1.0,
                message=f"{labels[m.rule_id]} detected", span=Span(start=m.start, end=m.end, field=item.path),
            ))
        if action == "redact":
            result.replacements[index] = apply_placeholders(item.value, matches, ctx.redactor.placeholder)
    if result.findings:
        result.decision = {"redact": Decision.redact, "block": Decision.block, "allow": Decision.allow}[action]
    return result
