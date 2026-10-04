"""Resolve global settings + strictness presets + agent overrides into one flat profile per agent.

Checks only read EffectiveAgent, so inheritance rules live in exactly one place.
"""

from pydantic import BaseModel

from app.policy.models import (
    Action,
    AgentPolicy,
    ApprovalSettings,
    ArgConstraint,
    Budget,
    Mode,
    PiiEntity,
    Policy,
    Strictness,
)

PRESETS: dict[str, dict] = {
    "low": {"injection_threshold": 0.95, "injection_gate": 0.5, "judge": False, "pii_out": None, "loop": 8},
    "medium": {"injection_threshold": 0.85, "injection_gate": 0.3, "judge": True, "pii_out": None, "loop": 5},
    # high: PII in LLM answers is blocked (tool results are still only redacted, or agents could not work)
    "high": {"injection_threshold": 0.70, "injection_gate": 0.0, "judge": True, "pii_out": "block", "loop": 3},
}


class EffectiveAgent(BaseModel):
    id: str
    mode: Mode
    strictness: Strictness
    models_allowed: list[str]
    tools_allowed: list[str]
    tools_need_approval: list[str]
    tool_args: dict[str, dict[str, ArgConstraint]]
    approval: ApprovalSettings
    budget: Budget
    pii_entities: list[PiiEntity]
    pii_in_action: Action
    pii_out_action: Action  # LLM answers (what the human sees)
    pii_result_action: Action  # tool results (what the agent sees)
    pii_tool_args_action: Action
    secrets_in_action: Action
    secrets_out_action: Action
    banned_terms: list[str]
    banned_action: Action
    loop_max_repeats: int
    loop_window_s: int
    requests_per_minute: int
    injection_threshold: float
    injection_gate: float
    judge_enabled: bool


def resolve_agent(agent_id: str, agent: AgentPolicy, policy: Policy) -> EffectiveAgent:
    strictness = agent.strictness or policy.strictness
    preset = PRESETS[strictness]
    c = policy.controls
    return EffectiveAgent(
        id=agent_id,
        mode=agent.mode or policy.mode,
        strictness=strictness,
        models_allowed=agent.models_allowed if agent.models_allowed is not None else policy.models_allowed,
        tools_allowed=agent.tools_allowed,
        tools_need_approval=agent.tools_need_approval,
        tool_args=agent.tool_args,
        approval=agent.approval,
        budget=agent.budget,
        pii_entities=c.pii.entities,
        pii_in_action=c.pii.action,
        pii_out_action=c.pii.outbound_action or preset["pii_out"] or c.pii.action,
        pii_result_action=c.pii.outbound_action or c.pii.action,
        pii_tool_args_action=c.pii.tool_args_action,
        secrets_in_action=c.secrets.action,
        secrets_out_action=c.secrets.outbound_action,
        banned_terms=c.banned_topics.terms,
        banned_action=c.banned_topics.action,
        loop_max_repeats=c.loop.max_repeats or preset["loop"],
        loop_window_s=c.loop.window_s,
        requests_per_minute=c.rate_limit.requests_per_minute,
        injection_threshold=c.prompt_injection.threshold or preset["injection_threshold"],
        injection_gate=c.prompt_injection.gate if c.prompt_injection.gate is not None else preset["injection_gate"],
        judge_enabled=c.llm_judge.enabled and preset["judge"],
    )
