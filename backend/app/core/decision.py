from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class Decision(StrEnum):
    allow = "allow"
    redact = "redact"
    needs_approval = "needs_approval"
    block = "block"


# block > needs_approval > redact > allow
_RANK = {Decision.allow: 0, Decision.redact: 1, Decision.needs_approval: 2, Decision.block: 3}

Severity = Literal["low", "medium", "high", "critical"]
SEVERITY_WEIGHT: dict[str, float] = {"low": 0.3, "medium": 0.6, "high": 0.9, "critical": 1.0}


def combine(*decisions: Decision) -> Decision:
    return max(decisions, key=_RANK.__getitem__, default=Decision.allow)


def action_to_decision(action: str) -> Decision:
    """Map a policy action string (allow | redact | block | needs_approval) to a Decision."""
    return Decision(action)


class Span(BaseModel):
    start: int
    end: int
    field: str | None = None


class Finding(BaseModel):
    check: str
    rule_id: str
    category: str
    severity: Severity
    score: float
    message: str
    span: Span | None = None


class CheckTiming(BaseModel):
    check: str
    tier: int
    ms: float
    skipped_reason: str | None = None


@dataclass
class CheckResult:
    decision: Decision = Decision.allow
    findings: list[Finding] = field(default_factory=list)
    # index into ctx.texts -> replacement text (redaction)
    replacements: dict[int, str] = field(default_factory=dict)
    # set when the check found out it could not run (dependency down): recorded as a skip, not as a run
    skipped_reason: str | None = None


def risk_score(findings: list[Finding]) -> float:
    """Noisy-OR over findings: 1 - prod(1 - weight * score). Monotonic and explainable."""
    remaining = 1.0
    for f in findings:
        remaining *= 1.0 - SEVERITY_WEIGHT[f.severity] * max(0.0, min(1.0, f.score))
    return round(1.0 - remaining, 4)
