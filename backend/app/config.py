from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    app_name: str = "AgentGuard API"
    environment: str = "development"
    debug: bool = True
    cors_origins: str = "http://localhost:5173"
    # Any local dev port: Vite moves to 5174+ when 5173 is taken, and the dashboard must keep working.
    cors_origin_regex: str | None = r"http://(localhost|127\.0\.0\.1)(:\d+)?"

    policy_path: Path = REPO_ROOT / "policy.yaml"
    data_dir: Path = BACKEND_DIR / "data"
    watch_policy: bool = True

    llm_provider: Literal["auto", "ollama", "mock"] = "auto"  # auto: Ollama when reachable, else the mock LLM
    ollama_url: str = "http://localhost:11434"
    llm_timeout_s: float = 120.0
    mcp_timeout_s: float = 30.0

    admin_token: str = "dev-admin"

    ml_enabled: bool = True  # T2 injection classifier (needs requirements-ml.txt + `make models`)
    ml_threads: int = 2
    models_dir: Path = BACKEND_DIR / "models"
    judge_enabled: bool = True  # T3 LLM judge via Ollama; skipped automatically while Ollama is unreachable

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
