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

    policy_path: Path = REPO_ROOT / "policy.yaml"
    data_dir: Path = BACKEND_DIR / "data"
    watch_policy: bool = True

    llm_provider: Literal["ollama", "mock"] = "ollama"
    ollama_url: str = "http://localhost:11434"
    llm_timeout_s: float = 120.0
    mcp_timeout_s: float = 30.0

    admin_token: str = "dev-admin"
    ml_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
