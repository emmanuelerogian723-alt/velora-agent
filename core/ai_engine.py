"""
Velora — AI Engine
Multi-provider LLM router with automatic fallback chain.
Supports: OpenAI, Groq, Anthropic, Google Gemini, OpenRouter, Ollama.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

from core.config import settings
from core.logger import get_logger

log = get_logger("velora.ai_engine")


class AIProvider(str, Enum):
    OPENAI = "openai"
    GROQ = "groq"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"


@dataclass
class AIMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class AIResponse:
    content: str
    provider: AIProvider
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


class AIEngine:
    """
    Unified LLM interface.  Tries providers in order until one succeeds.
    Thread-safe; uses a single shared async httpx client.
    """

    PROVIDER_CONFIGS: Dict[AIProvider, Dict[str, Any]] = {
        AIProvider.OPENAI: {
            "url": "https://api.openai.com/v1/chat/completions",
            "model": "gpt-4o",
            "key_attr": "OPENAI_API_KEY",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
        },
        AIProvider.GROQ: {
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "model": "llama-3.1-70b-versatile",
            "key_attr": "GROQ_API_KEY",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
        },
        AIProvider.ANTHROPIC: {
            "url": "https://api.anthropic.com/v1/messages",
            "model": "claude-3-5-sonnet-20241022",
            "key_attr": "ANTHROPIC_API_KEY",
            "auth_header": "x-api-key",
            "auth_prefix": "",
        },
        AIProvider.GEMINI: {
            "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent",
            "model": "gemini-1.5-pro",
            "key_attr": "GOOGLE_GEMINI_API_KEY",
            "auth_header": None,  # uses query param
            "auth_prefix": "",
        },
        AIProvider.OPENROUTER: {
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "model": "anthropic/claude-3.5-sonnet",
            "key_attr": "OPENROUTER_API_KEY",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer ",
        },
        AIProvider.OLLAMA: {
            "url": None,  # built dynamically from OLLAMA_BASE_URL
            "model": "llama3.1",
            "key_attr": None,
            "auth_header": None,
            "auth_prefix": "",
        },
    }

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._provider_order = self._build_provider_order()

    def _build_provider_order(self) -> List[AIProvider]:
        primary = AIProvider(settings.AI_PRIMARY_PROVIDER)
        fallbacks = [AIProvider(p) for p in settings.AI_FALLBACK_CHAIN if p != settings.AI_PRIMARY_PROVIDER]
        return [primary] + fallbacks

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    def _get_api_key(self, provider: AIProvider) -> Optional[str]:
        cfg = self.PROVIDER_CONFIGS[provider]
        if cfg["key_attr"] is None:
            return None
        return getattr(settings, cfg["key_attr"], None)

    def _is_available(self, provider: AIProvider) -> bool:
        key = self._get_api_key(provider)
        if provider == AIProvider.OLLAMA:
            return bool(settings.OLLAMA_BASE_URL)
        return bool(key)

    async def _call_openai_compat(
        self,
        provider: AIProvider,
        messages: List[AIMessage],
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> AIResponse:
        cfg = self.PROVIDER_CONFIGS[provider]
        key = self._get_api_key(provider)

        if provider == AIProvider.OLLAMA:
            url = f"{settings.OLLAMA_BASE_URL}/api/chat"
        else:
            url = cfg["url"]

        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend([{"role": m.role, "content": m.content} for m in messages])

        payload: Dict[str, Any] = {
            "model": cfg["model"],
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        headers = {"Content-Type": "application/json"}
        if cfg["auth_header"] and key:
            headers[cfg["auth_header"]] = f"{cfg['auth_prefix']}{key}"

        resp = await self.client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return AIResponse(
            content=content,
            provider=provider,
            model=cfg["model"],
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            raw=data,
        )

    async def _call_anthropic(
        self,
        messages: List[AIMessage],
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> AIResponse:
        key = settings.ANTHROPIC_API_KEY
        cfg = self.PROVIDER_CONFIGS[AIProvider.ANTHROPIC]

        msgs = [{"role": m.role, "content": m.content} for m in messages]
        payload: Dict[str, Any] = {
            "model": cfg["model"],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": msgs,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        resp = await self.client.post(cfg["url"], json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        content = data["content"][0]["text"]
        usage = data.get("usage", {})
        return AIResponse(
            content=content,
            provider=AIProvider.ANTHROPIC,
            model=cfg["model"],
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            raw=data,
        )

    async def _call_gemini(
        self,
        messages: List[AIMessage],
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> AIResponse:
        key = settings.GOOGLE_GEMINI_API_KEY
        cfg = self.PROVIDER_CONFIGS[AIProvider.GEMINI]
        url = f"{cfg['url']}?key={key}"

        parts = []
        if system_prompt:
            parts.append({"text": f"[System]: {system_prompt}\n\n"})
        for m in messages:
            parts.append({"text": f"[{m.role}]: {m.content}"})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        resp = await self.client.post(url, json=payload, headers={"Content-Type": "application/json"})
        resp.raise_for_status()
        data = resp.json()
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        return AIResponse(content=content, provider=AIProvider.GEMINI, model=cfg["model"], raw=data)

    async def complete(
        self,
        messages: List[AIMessage],
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> AIResponse:
        """
        Try providers in order. Returns first successful response.
        Raises RuntimeError if all providers fail.
        """
        last_error: Optional[Exception] = None

        for provider in self._provider_order:
            if not self._is_available(provider):
                continue
            try:
                log.debug("Trying AI provider", extra={"provider": provider.value})

                if provider == AIProvider.ANTHROPIC:
                    result = await self._call_anthropic(messages, system_prompt, max_tokens, temperature)
                elif provider == AIProvider.GEMINI:
                    result = await self._call_gemini(messages, system_prompt, max_tokens, temperature)
                else:
                    result = await self._call_openai_compat(provider, messages, system_prompt, max_tokens, temperature)

                log.info(
                    "AI response received",
                    extra={
                        "provider": provider.value,
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                    },
                )
                return result

            except Exception as e:
                log.warning(
                    "AI provider failed, trying next",
                    extra={"provider": provider.value, "error": str(e)},
                )
                last_error = e
                await asyncio.sleep(0.5)

        raise RuntimeError(f"All AI providers exhausted. Last error: {last_error}")

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton
ai_engine = AIEngine()
