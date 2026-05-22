"""
Application configuration — loaded from environment variables / .env file.

Uses pydantic-settings BaseSettings with .env file support.
All settings can be overridden via environment variables (case-insensitive).
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service identity ──────────────────────────────────────────────────────
    SERVICE_NAME: str = "analytics"
    VERSION: str = "1.0.0"
    ENV: str = "development"  # development | staging | production
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["*"]

    # ── Database ──────────────────────────────────────────────────────────────
    # Full Postgres connection URL (shared with QuantDinger database)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/quantdinger"

    # Postgres schema owned by Analytics. All tables created via Alembic
    # migrations live in this schema. The database role used by Analytics
    # only has GRANT USAGE on this schema (Property 3 — schema isolation).
    DB_SCHEMA: str = "analytics"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 20

    # Prefix prepended to every key/channel set by Analytics, so we never
    # collide with QuantDinger Flask keys (which use "qd:"). Property 10.
    REDIS_KEY_PREFIX: str = "analytics:"

    # ── Auth (Analytics-native JWT) ───────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Master API key for admin operations (optional, dev only)
    MASTER_API_KEY: str = ""

    # ── QuantDinger JWT bridge ────────────────────────────────────────────────
    # Shared secret with QuantDinger Flask backend (must match Flask SECRET_KEY).
    # Used by core/auth.py::verify_quantdinger_jwt to verify tokens issued by
    # QuantDinger so users authenticated against QD can call Analytics endpoints
    # without re-login. See design.md "Auth flow chia sẻ".
    # Leave empty to disable the JWT bridge.
    QUANTDINGER_JWT_SECRET: str = ""
    QUANTDINGER_JWT_ALGORITHM: str = "HS256"

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_FREE: int = 60       # req/min for free tier
    RATE_LIMIT_PAID: int = 600      # req/min for paid tier

    # ── Python runner ─────────────────────────────────────────────────────────
    # Path to fincept-qt/scripts directory (resolved at runtime if empty)
    SCRIPTS_DIR: str = ""
    # Path to Python venv executables
    VENV_NUMPY1_PYTHON: str = ""    # e.g. /path/to/venv-numpy1/bin/python
    VENV_NUMPY2_PYTHON: str = ""    # e.g. /path/to/venv-numpy2/bin/python
    # Default venv to use when not specified
    DEFAULT_VENV: str = "venv-numpy2"
    # Max concurrent Python subprocesses
    MAX_CONCURRENT_PROCESSES: int = 5
    # Default script timeout (seconds)
    DEFAULT_TIMEOUT: int = 60

    # ── Agent-specific timeouts ───────────────────────────────────────────────
    AGENT_RUN_TIMEOUT: int = 120
    AGENT_PLAN_TIMEOUT: int = 300
    MAX_CONCURRENT_AGENT_RUNS: int = 10

    # ── News fetcher settings ─────────────────────────────────────────────────
    # Interval between RSS fetch cycles (seconds)
    NEWS_FETCH_INTERVAL: int = 30
    # Number of consecutive errors before a source is auto-disabled
    NEWS_SOURCE_ERROR_THRESHOLD: int = 5
    # Per-source fetch timeout (seconds)
    NEWS_FETCH_TIMEOUT: int = 10
    # Redis Stream key for the news pipeline queue
    NEWS_QUEUE_STREAM: str = "analytics:news:queue"
    # Redis pubsub channel prefix for realtime news fanout
    NEWS_PUBSUB_PREFIX: str = "analytics:news:pubsub:"
    # NLP model for sentiment analysis (HuggingFace model ID)
    NEWS_SENTIMENT_MODEL: str = "ProsusAI/finbert"
    # spaCy model for NER
    NEWS_NER_MODEL: str = "en_core_web_sm"
    # Audit log retention in days
    AUDIT_LOG_RETENTION_DAYS: int = 90

    # ── External API keys (injected into subprocess env) ─────────────────────
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    POLYGON_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    ALPHA_VANTAGE_API_KEY: str = ""
    FRED_API_KEY: str = ""
    MARINETRAFFIC_API_KEY: str = ""
    ACLED_API_KEY: str = ""
    HELIUS_API_KEY: str = ""

    # ── LLM defaults (OpenAI-compatible) ─────────────────────────────────────
    # Server-side default LLM — used when client does not pass llm_config.
    # Supports any OpenAI-compatible endpoint (Groq, Together, DeepSeek, Ollama…).
    # Default provider is NOT "fincept" — user must configure their own endpoint.
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_API_KEY: str = ""           # fallback key if client does not pass one

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json | console

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("SCRIPTS_DIR", mode="before")
    @classmethod
    def resolve_scripts_dir(cls, v: str) -> str:
        if v:
            p = Path(v)
            if p.exists():
                return str(p.resolve())
            # Relative path support
            return str(Path(v).resolve())
        # Auto-detect: walk up from this file to find fincept-qt/scripts
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = parent / "fincept-qt" / "scripts"
            if candidate.exists():
                return str(candidate)
        return ""

    @field_validator("VENV_NUMPY2_PYTHON", mode="before")
    @classmethod
    def resolve_venv_numpy2(cls, v: str) -> str:
        """Auto-detect venv-numpy2 python if not set."""
        if v:
            return v
        # Try common locations relative to project root
        here = Path(__file__).resolve()
        candidates = []
        for parent in here.parents:
            candidates += [
                parent / "fincept-qt" / "venv-numpy2" / "Scripts" / "python.exe",  # Windows
                parent / "fincept-qt" / "venv-numpy2" / "bin" / "python",           # Linux/macOS
                parent / "venv-numpy2" / "Scripts" / "python.exe",
                parent / "venv-numpy2" / "bin" / "python",
            ]
        for c in candidates:
            if c.exists():
                return str(c)
        return ""

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def redis_key_prefix(self) -> str:
        """Convenience accessor — always returns REDIS_KEY_PREFIX."""
        return self.REDIS_KEY_PREFIX

    @property
    def quantdinger_jwt_enabled(self) -> bool:
        """True when the QuantDinger JWT bridge is configured."""
        return bool(self.QUANTDINGER_JWT_SECRET)


settings = Settings()
