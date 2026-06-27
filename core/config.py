"""
Velora — Core Configuration
Loads all env vars, validates them, exposes a single settings object.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "Velora"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field("production", pattern="^(development|staging|production)$")
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = Field(..., min_length=32)

    # ── CROO Protocol ─────────────────────────────────────────────────────────
    CROO_API_URL: str = "https://api.croo.network"
    CROO_WS_URL: str = "wss://api.croo.network/ws"
    CROO_SDK_KEY: str = Field(..., description="croo_sk_... API key from agent.croo.network")
    CROO_AGENT_ID: str = Field(..., description="Agent ID from CROO dashboard")
    BASE_RPC_URL: str = "https://mainnet.base.org"

    # ── AI Providers (at least one required) ─────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_GEMINI_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: Optional[str] = "http://localhost:11434"

    # AI model preferences (ordered fallback chain)
    AI_PRIMARY_PROVIDER: str = "openai"
    AI_FALLBACK_CHAIN: List[str] = ["groq", "anthropic", "gemini", "openrouter", "ollama"]
    AI_DEFAULT_MODEL: str = "gpt-4o"
    AI_MAX_TOKENS: int = 4096
    AI_TEMPERATURE: float = 0.2

    # ── Web Search ────────────────────────────────────────────────────────────
    SERPER_API_KEY: Optional[str] = None
    BRAVE_SEARCH_API_KEY: Optional[str] = None

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        "postgresql+asyncpg://velora:velora@localhost:5432/velora",
        description="Async PostgreSQL connection string"
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL_DEFAULT: int = 3600       # 1 hour
    REDIS_TTL_TASK_RESULT: int = 86400  # 24 hours

    # ── API Server ────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    WORKERS: int = 1
    ALLOWED_ORIGINS: List[str] = ["*"]

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60         # seconds

    # ── Security ──────────────────────────────────────────────────────────────
    API_KEY_HEADER: str = "X-Velora-Key"
    VELORA_API_KEY: Optional[str] = None  # optional internal API key

    # ── CROO Order Behavior ───────────────────────────────────────────────────
    NEGOTIATION_AUTO_ACCEPT: bool = True
    MAX_CONCURRENT_ORDERS: int = 10
    TASK_TIMEOUT_SECONDS: int = 300
    DELIVERY_RETRY_ATTEMPTS: int = 3
    DELIVERY_RETRY_DELAY: float = 2.0

    @field_validator("CROO_SDK_KEY")
    @classmethod
    def croo_key_format(cls, v: str) -> str:
        if not v.startswith("croo_sk_"):
            raise ValueError("CROO_SDK_KEY must start with 'croo_sk_'")
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": True}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
