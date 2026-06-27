"""
Velora — FastAPI Server
CROO calls Velora via WebSocket (provider receives events).
This HTTP server exposes: health, status, CROO connection test, and admin endpoints.

The CROO provider runtime starts as a background async task on startup.
"""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader

from core.config import settings
from core.logger import get_logger
from protocol.provider import velora_provider
from skills.router import skill_router

log = get_logger("velora.api.server")
_startup_time = time.time()


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "Velora starting",
        extra={
            "version": settings.APP_VERSION,
            "env": settings.ENVIRONMENT,
            "agent_id": settings.CROO_AGENT_ID,
            "croo_api": settings.CROO_API_URL,
        },
    )

    # Test CROO connection on startup
    from protocol.client import croo_client
    conn = await croo_client.test_connection()
    if conn["connected"]:
        log.info("CROO connection verified", extra=conn)
    else:
        log.error("CROO connection FAILED on startup", extra=conn)

    # Launch provider runtime as background task
    provider_task = asyncio.create_task(velora_provider.start())

    yield  # ── server running ──

    log.info("Velora shutting down")
    await velora_provider.stop()
    provider_task.cancel()
    try:
        await provider_task
    except asyncio.CancelledError:
        pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Velora",
    description=(
        "Production autonomous AI agent — CROO Network provider.\n\n"
        "Velora connects to CROO via WebSocket, auto-accepts negotiations, "
        "executes tasks using its AI engine, and delivers results on-chain for USDC."
    ),
    version=settings.APP_VERSION,
    docs_url="/docs",   # always expose docs (useful for CROO testing)
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ──────────────────────────────────────────────────────────────────────

api_key_header = APIKeyHeader(name=settings.API_KEY_HEADER, auto_error=False)


def verify_api_key(key: str = Security(api_key_header)) -> bool:
    if not settings.VELORA_API_KEY:
        return True  # No key configured = open (dev mode)
    if key != settings.VELORA_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


# ── Request Logger Middleware ─────────────────────────────────────────────────

@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)
    log.info(
        "HTTP",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration_ms,
        },
    )
    return response


# ── Health & Root ─────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"], summary="Agent info")
async def root() -> Dict[str, Any]:
    """Quick identity check — used by CROO and monitoring."""
    return {
        "agent": "Velora",
        "version": settings.APP_VERSION,
        "status": "online",
        "croo_agent_id": settings.CROO_AGENT_ID,
        "croo_api": settings.CROO_API_URL,
        "skills": skill_router.available_skills,
    }


@app.get("/health", tags=["Health"], summary="Health check")
async def health() -> Dict[str, Any]:
    """Used by Docker HEALTHCHECK, Render, and load balancers."""
    return {
        "status": "healthy",
        "uptime_seconds": round(time.time() - _startup_time, 1),
        "version": settings.APP_VERSION,
    }


# ── Status ────────────────────────────────────────────────────────────────────

@app.get("/status", tags=["Status"], summary="Full provider status")
async def status() -> Dict[str, Any]:
    """
    Returns full operational status including:
    - CROO provider runtime state
    - Active order count
    - Available skills
    - AI providers configured
    """
    ai_providers = []
    if os.environ.get("OPENAI_API_KEY"):
        ai_providers.append("openai")
    if os.environ.get("GROQ_API_KEY"):
        ai_providers.append("groq")
    if os.environ.get("ANTHROPIC_API_KEY"):
        ai_providers.append("anthropic")
    if os.environ.get("GOOGLE_GEMINI_API_KEY"):
        ai_providers.append("gemini")
    if os.environ.get("OPENROUTER_API_KEY"):
        ai_providers.append("openrouter")
    if settings.OLLAMA_BASE_URL:
        ai_providers.append("ollama")

    return {
        "agent": "Velora",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": round(time.time() - _startup_time, 1),
        "croo": {
            "agent_id": settings.CROO_AGENT_ID,
            "api_url": settings.CROO_API_URL,
            "ws_url": settings.CROO_WS_URL,
            "provider_running": velora_provider.is_running,
            "active_orders": velora_provider.active_order_count,
            "max_concurrent": settings.MAX_CONCURRENT_ORDERS,
            "auto_accept": settings.NEGOTIATION_AUTO_ACCEPT,
        },
        "skills": {
            "available": skill_router.available_skills,
            "count": len(skill_router.available_skills),
        },
        "ai": {
            "primary": settings.AI_PRIMARY_PROVIDER,
            "configured": ai_providers,
            "fallback_chain": settings.AI_FALLBACK_CHAIN,
        },
    }


# ── CROO Connection Test ──────────────────────────────────────────────────────

@app.get("/croo/test", tags=["CROO"], summary="Test CROO API connection")
async def test_croo_connection() -> Dict[str, Any]:
    """
    Verify the CROO SDK key is valid and the API is reachable.
    Returns connection status and agent details.
    """
    from protocol.client import croo_client
    result = await croo_client.test_connection()
    if not result["connected"]:
        raise HTTPException(status_code=503, detail=result)
    return result


@app.get("/croo/negotiations", tags=["CROO"], summary="List pending negotiations")
async def list_negotiations() -> Dict[str, Any]:
    """List all pending negotiations waiting for Velora to accept."""
    from protocol.client import croo_client
    negs = await croo_client.list_pending_negotiations()
    return {
        "count": len(negs),
        "negotiations": [
            {
                "id": getattr(n, "id", "?"),
                "service_id": getattr(n, "service_id", "?"),
                "status": getattr(n, "status", "?"),
            }
            for n in negs
        ],
    }


@app.get("/croo/orders", tags=["CROO"], summary="List active (paid) orders")
async def list_orders() -> Dict[str, Any]:
    """List all paid orders currently in execution."""
    from protocol.client import croo_client
    orders = await croo_client.list_active_orders()
    return {
        "active_in_memory": velora_provider.active_order_count,
        "paid_on_croo": len(orders),
        "orders": [
            {
                "id": getattr(o, "id", "?"),
                "status": getattr(o, "status", "?"),
                "service_id": getattr(o, "service_id", "?"),
            }
            for o in orders
        ],
    }


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.post("/admin/restart-provider", tags=["Admin"], summary="Hot-restart provider")
async def restart_provider(_: bool = Security(verify_api_key)) -> Dict[str, str]:
    """Restart the CROO WebSocket provider without taking the HTTP server down."""
    await velora_provider.stop()
    asyncio.create_task(velora_provider.start())
    log.info("Provider restarted via admin endpoint")
    return {"status": "restarting", "message": "Provider is reconnecting to CROO"}


# ── Global Error Handler ──────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error(
        "Unhandled exception",
        extra={"path": str(request.url.path), "error": str(exc)},
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )
