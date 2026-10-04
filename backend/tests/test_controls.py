"""Data-driven guardrail tests: every case in tests/cases/*.yaml runs through the real pipeline,
real policy.yaml and real signature feed. Add a case = add a few lines of YAML."""

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.checks import CHECKS
from app.core.context import Redactor, RequestContext, TextItem
from app.core.events import ToolRef
from app.core.pipeline import Runtime, run_pipeline
from app.core.text import collect_strings
from app.policy.feed import load_feed
from app.policy.store import PolicyStore
from app.state import State

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = Path(__file__).parent / "cases"


def load_cases() -> list[dict[str, Any]]:
    cases = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        for case in yaml.safe_load(path.read_text(encoding="utf-8")):
            case["_file"] = path.stem
            cases.append(case)
    return cases


CASES = load_cases()
STORE = PolicyStore(REPO_ROOT / "policy.yaml")
STORE.load()
FEED = load_feed(STORE.feed_path)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_case(case: dict[str, Any]):
    snapshot = STORE.current()
    agent = snapshot.agents[case.get("agent", "support-bot")]
    if "mode" in case:
        agent = agent.model_copy(update={"mode": case["mode"]})
    stage = case["channel"]

    tool = None
    if stage == "mcp_call":
        spec = case["tool"]
        tool = ToolRef(server=spec.get("server", "crm"), name=spec["name"], arguments=spec.get("arguments") or {})
        texts = collect_strings(tool.arguments, ("arguments",))
    else:
        texts = [TextItem(("text",), case["input"])]

    ctx = RequestContext("trace", "task", agent, stage, texts, Redactor(), model=case.get("model", "mock"), tool=tool)
    result = await run_pipeline(ctx, Runtime(snapshot, FEED, State()), CHECKS)

    expect = case["expect"]
    fired = {f.rule_id for f in result.findings}
    assert result.decision.value == expect["decision"], f"decision {result.decision.value}, rules fired: {sorted(fired)}"
    for rule in expect.get("rules", []):
        assert rule in fired, f"expected rule {rule}, fired: {sorted(fired)}"
    for rule in expect.get("not_rules", []):
        assert rule not in fired, f"rule {rule} should not fire"
    if "contains" in expect:
        assert expect["contains"] in result.redacted_text
    if "not_contains" in expect:
        assert expect["not_contains"] not in result.redacted_text
    if "max_risk" in expect:
        assert result.risk <= expect["max_risk"], f"risk {result.risk}"
    if "monitor_only" in expect:
        assert result.monitor_only == expect["monitor_only"]
    if "would_have" in expect:
        assert result.would_have is not None and result.would_have.value == expect["would_have"]


def test_case_suite_size():
    """The suite is part of the deliverable: keep it big and balanced."""
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    by_decision = Counter(c["expect"]["decision"] for c in CASES)
    print(f"\n{len(CASES)} YAML cases: " + " · ".join(f"{n} {d}" for d, n in sorted(by_decision.items())))
    assert len(CASES) >= 50
    assert {"allow", "block", "redact", "needs_approval"} <= set(by_decision)
