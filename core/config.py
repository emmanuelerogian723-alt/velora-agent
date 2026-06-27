"""
Velora — Core Configuration
Loads all settings from environment variables.
Validates on startup — bad config = fast fail.

Secret naming:
  CROO_API_KEY  = Base44 secret name (auto-injected by platform)
  CROO_SDK_KEY  = legacy / local .env name
Both are checked; CROO_API_KEY takes priority.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "Velora"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = Field(default="velora-default-secret-key-change-in-production")

    # ── CROO Protocol ─────────────────────────────────────────────────────────
    CROO_API_URL: str = "https://api.croo.network"
    CROO_WS_URL: str = "wss://api.croo.network/ws"
    # CROO_API_KEY is resolved dynamically via os.environ in croo/client.py
    # so it does NOT need to be declared here — it is picked up at runtime
    CROO_SDK_KEY: str = Field(default="")  # fallback / local dev
    CROO_AGENT_ID: str = Field(default="")
    BASE_RPC_URL: str = "https://mainnet.base.org"

    # ── AI Providers ─────────────────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_GEMINI_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: Optional[str] = "http://localhost:11434"

    AI_PRIMARY_PROVIDER: str = "openai"
    AI_FALLBACK_CHAIN: List[str] = ["groq", "anthropic", "gemini", "openrouter", "ollama"]
    AI_DEFAULT_MODEL: str = "gpt-4o"
    AI_MAX_TOKENS: int = 4096
    AI_TEMPERATURE: float = 0.2

    # ── Web Search ────────────────────────────────────────────────────────────
    SERPER_API_KEY: Optional[str] = None
    BRAVE_SEARCH_API_KEY: Optional[str] = None

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://velora:velora@localhost:5432/velora"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL_DEFAULT: int = 3600
    REDIS_TTL_TASK_RESULT: int = 86400

    # ── API Server ────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    WORKERS: int = 1
    ALLOWED_ORIGINS: List[str] = ["*"]

    # ── Security ──────────────────────────────────────────────────────────────
    API_KEY_HEADER: str = "X-Velora-Key"
    VELORA_API_KEY: Optional[str] = None

    # ── CROO Order Behavior ───────────────────────────────────────────────────
    NEGOTIATION_AUTO_ACCEPT: bool = True
    MAX_CONCURRENT_ORDERS: int = 10
    TASK_TIMEOUT_SECONDS: int = 300
    DELIVERY_RETRY_ATTEMPTS: int = 3
    DELIVERY_RETRY_DELAY: float = 2.0

    @model_validator(mode="after")
    def check_croo_key_available(self) -> "Settings":
        """
        Verify at least one CROO key source is configured.
        Checks both CROO_API_KEY (Base44 platform secret) and CROO_SDK_KEY.
        """
        croo_api_key = os.environ.get("CROO_API_KEY", "")
        croo_sdk_key = self.CROO_SDK_KEY or ""
        if not croo_api_key and not croo_sdk_key:
            import warnings
            warnings.warn(
                "No CROO API key configured. Set CROO_API_KEY or CROO_SDK_KEY. "
                "Get your key from https://agent.croo.network",
                stacklevel=2,
            )
        return self

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
