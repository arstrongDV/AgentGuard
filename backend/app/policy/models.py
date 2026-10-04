"""Pydantic schema of policy.yaml. See backend/docs/policy-schema.md."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["monitor", "enforce"]
Strictness = Literal["low", "medium", "high"]
Action = Literal["allow", "redact", "block"]
PiiEntity = Literal["EMAIL", "PHONE", "IBAN", "CREDIT_CARD"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PiiControl(Strict):
    action: Action = "redact"
    outbound_action: Action | None = None
    tool_args_action: Action = "allow"  # tools legitimately receive PII (send_email.to); detect, don't rewrite
    entities: list[PiiEntity] = ["EMAIL", "PHONE", "IBAN", "CREDIT_CARD"]


class SecretsControl(Strict):
    action: Action = "block"
    outbound_action: Action = "redact"


class BannedTopicsControl(Strict):
    action: Action = "block"
    terms: list[str] = []


class PromptInjectionControl(Strict):
    action: Action = "block"
    threshold: float | None = None
    monitor_below: float = 0.6
    gate: float | None = None


class LlmJudgeControl(Strict):
    enabled: bool = False
    model: str = "granite3-guardian:2b"
    only_for_risk_above: float = 0.5
    timeout_s: float = 3.0
    on_timeout: Literal["allow", "block"] = "allow"


class SignaturesControl(Strict):
    feed: str = "./feeds/signatures.json"
    url: str | None = None
    refresh_s: int = 60


class LoopControl(Strict):
    max_repeats: int | None = None
    window_s: int = 60


class RateLimitControl(Strict):
    requests_per_minute: int = 60


class Controls(Strict):
    pii: PiiControl = PiiControl()
    secrets: SecretsControl = SecretsControl()
    banned_topics: BannedTopicsControl = BannedTopicsControl()
    prompt_injection: PromptInjectionControl = PromptInjectionControl()
    llm_judge: LlmJudgeControl = LlmJudgeControl()
    signatures: SignaturesControl = SignaturesControl()
    loop: LoopControl = LoopControl()
    rate_limit: RateLimitControl = RateLimitControl()


class ModelCost(Strict):
    input: float = 0.0  # USD per 1K tokens
    output: float = 0.0
    virtual: bool = False


class Budget(Strict):
    tokens_per_day: int | None = None
    usd_per_day: float | None = None
    max_tool_calls_per_task: int | None = None


class ArgConstraint(Strict):
    pattern: str | None = None
    max: float | None = None
    min: float | None = None
    allowed: list[str | int | float] | None = None


class ApprovalSettings(Strict):
    timeout_s: float = 60
    on_timeout: Literal["deny", "approve"] = "deny"


class AgentPolicy(Strict):
    key_sha256: str
    description: str = ""
    mode: Mode | None = None
    strictness: Strictness | None = None
    models_allowed: list[str] | None = None
    tools_allowed: list[str] = []
    tools_need_approval: list[str] = []
    tool_args: dict[str, dict[str, ArgConstraint]] = {}
    approval: ApprovalSettings = ApprovalSettings()
    budget: Budget = Budget()


class McpServer(Strict):
    url: str


class PinnedModel(Strict):
    sha256: str


class SupplyChain(Strict):
    pinned: dict[str, PinnedModel] = {}
    allowed_hf_orgs: list[str] = []


class Policy(Strict):
    version: int = 1
    mode: Mode = "enforce"
    strictness: Strictness = "medium"
    block_status_code: Literal[200, 403] = 200
    models_allowed: list[str] = []
    costs: dict[str, ModelCost] = {}
    controls: Controls = Controls()
    supply_chain: SupplyChain = SupplyChain()
    mcp_servers: dict[str, McpServer] = {}
    high_risk_tools: list[str] = []
    agents: dict[str, AgentPolicy] = Field(default_factory=dict)
