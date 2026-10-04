"""Shared fixtures. Tests never touch Ollama, Hugging Face or the network: the LLM is the mock
provider and MCP upstreams are in-process ASGI apps."""

import shutil
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from tests.fake_mcp import make_fake_mcp

REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN = {"Authorization": "Bearer test-admin"}
SUPPORT_KEY = "ag-support-demo-key"
FINANCE_KEY = "ag-finance-demo-key"


@pytest.fixture(autouse=True)
def hermetic_env(monkeypatch):
    """Deployment settings (docker-compose sets MCP_HOST, POLICY_PATH...) must not leak into tests."""
    for name in ("MCP_HOST", "POLICY_PATH", "DATA_DIR", "LLM_PROVIDER", "OLLAMA_URL", "ADMIN_TOKEN", "ML_ENABLED", "JUDGE_ENABLED",
                 "MODELS_DIR", "WATCHFILES_FORCE_POLLING"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def policy_file(tmp_path: Path) -> Path:
    """A private copy of the real policy.yaml + feed, so tests can edit it freely."""
    (tmp_path / "feeds").mkdir()
    shutil.copy(REPO_ROOT / "feeds" / "signatures.json", tmp_path / "feeds" / "signatures.json")
    shutil.copy(REPO_ROOT / "policy.yaml", tmp_path / "policy.yaml")
    return tmp_path / "policy.yaml"


@pytest.fixture
def settings(policy_file: Path, tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        policy_path=policy_file,
        data_dir=tmp_path / "data",
        llm_provider="mock",
        watch_policy=False,
        admin_token="test-admin",
        ml_enabled=False,  # semantic tiers are tested with fakes (tests/test_semantic.py)
        judge_enabled=False,
    )


@pytest.fixture
async def app(settings: Settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
def svc(app):
    return app.state.services


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def fake_mcp(svc):
    """Route the gateway's upstream MCP traffic to an in-process fake server. Returns its call log."""
    upstream, calls = make_fake_mcp()
    original = svc.http
    svc.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=upstream), base_url="http://upstream")
    yield calls
    await svc.http.aclose()
    svc.http = original
