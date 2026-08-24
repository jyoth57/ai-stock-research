from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_name: str = "AIStockResearch"
    app_env: str = "development"   # development | staging | production
    debug: bool = True
    secret_key: str = "change-me-in-production"

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    database_url: str = "postgresql://postgres:password@localhost:5432/aistockresearch"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── LLM provider (watsonx | deepseek | openai | ollama) ──────────────────
    llm_provider: str = "watsonx"

    # IBM Cloud Pak for Data (CPD / watsonx)
    watsonx_url:        str = ""
    watsonx_project_id: str = ""
    watsonx_model:      str = "openai/gpt-oss-120b"
    watsonx_version:    str = "2023-05-29"
    watsonx_username:   str = ""   # SSO username
    watsonx_api_key:    str = ""   # CPD API key (exchanged for Bearer token)
    watsonx_token:      str = ""   # optional: direct Bearer token (overrides api_key)

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_max_tokens: int = 4096
    embedding_model: str = "text-embedding-3-small"

    # Ollama (local)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "deepseek-r1:7b"

    # ── Data paths (resolved relative to project root) ────────────────────────
    raw_data_dir: Path = _PROJECT_ROOT / "data" / "raw"
    processed_data_dir: Path = _PROJECT_ROOT / "data" / "processed"
    reports_dir: Path = _PROJECT_ROOT / "data" / "reports"
    chroma_persist_dir: Path = _PROJECT_ROOT / "data" / "chroma"
    knowledge_dir: Path = _PROJECT_ROOT / "knowledge"
    log_dir: Path = _PROJECT_ROOT / "logs"

    # ── NSE / Market ──────────────────────────────────────────────────────────
    ohlcv_start_date: str = "2015-01-01"
    default_interval: str = "1d"

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    json_logs: bool = False   # True in production / Docker

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4

    # ── Dashboard ─────────────────────────────────────────────────────────────
    dashboard_port: int = 8501

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def project_root(self) -> Path:
        return _PROJECT_ROOT


# Singleton — import this everywhere
settings = Settings()
