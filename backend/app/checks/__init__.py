"""Check registry. Order matters: cheap gates (T0) first, then deterministic rules (T1).

T2 (injection classifier) and T3 (LLM judge) plug in here later, gated by risk.
"""

from app.checks.budget import budget, loop_detection, rate_limit, task_tool_calls
from app.checks.gates import model_allowlist, tool_acl
from app.checks.pii import pii
from app.checks.secrets import secrets
from app.checks.signatures import banned_topics, signatures
from app.core.pipeline import Check

ALL = frozenset({"llm_in", "llm_out", "mcp_call", "mcp_result"})
INBOUND = frozenset({"llm_in", "mcp_call"})

CHECKS: list[Check] = [
    # T0: identity-scoped gates
    Check("model_allowlist", 0, frozenset({"llm_in"}), model_allowlist),
    Check("tool_acl", 0, frozenset({"mcp_call"}), tool_acl),
    Check("rate_limit", 0, INBOUND, rate_limit),
    Check("budget", 0, frozenset({"llm_in"}), budget),
    Check("task_tool_calls", 0, frozenset({"mcp_call"}), task_tool_calls),
    Check("loop", 0, frozenset({"mcp_call"}), loop_detection),
    # T1: deterministic content rules
    Check("signatures", 1, ALL, signatures),
    Check("secrets", 1, ALL, secrets),
    Check("pii", 1, ALL, pii),
    Check("banned_topics", 1, frozenset({"llm_in", "llm_out"}), banned_topics),
]
