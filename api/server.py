"""
Velora — FastAPI Server
Exposes health checks, status, and internal management endpoints.
The CROO provider runtime runs as a background task.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader

from velora.core.config import settings
from velora.core.logger import get_logger
from velora.croo.provider import velora_provider
from velora.skills.router import skill_router

log = get_logger("velora.api.server")

_startup_time = time.time()


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start CROO provider on startup, clean up on shutdown."""
    log.info("Velora starting up", extra={"version": settings.APP_VERSION, "env": settings.ENVIRONMENT})

    # Start the CROO provider runtime as a background task
    provider_task = asyncio.create_task(velora_provider.start())

    yield

    # Graceful shutdown
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
    description="Production-grade autonomous AI agent — CROO Network provider",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
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
    """Optional internal API key protection."""
    if not settings.VELORA_API_KEY:
        return True  # No key configured = open
    if key != settings.VELORA_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


# ── Middleware ────────────────────────────────────────────────────────────────

@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)
    log.info(
        "HTTP request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


# ── Health & Status ───────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root() -> Dict[str, Any]:
    return {
        "agent": "Velora",
        "version": settings.APP_VERSION,
        "status": "online",
        "croo_agent_id": settings.CROO_AGENT_ID,
    }


@app.get("/health", tags=["Health"])
async def health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "uptime_seconds": round(time.time() - _startup_time, 1),
        "version": settings.APP_VERSION,
    }


@app.get("/status", tags=["Status"])
async def status() -> Dict[str, Any]:
    return {
        "agent": "Velora",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "croo": {
            "agent_id": settings.CROO_AGENT_ID,
            "provider_running": velora_provider.is_running,
            "active_orders": velora_provider.active_order_count,
            "max_concurrent": settings.MAX_CONCURRENT_ORDERS,
            "auto_accept": settings.NEGOTIATION_AUTO_ACCEPT,
        },
        "skills": {
            "available": skill_router.available_skills,
            "count": len(skill_router.available_skills),
        },
        "uptime_seconds": round(time.time() - _startup_time, 1),
    }


# ── Management (protected) ────────────────────────────────────────────────────

@app.post("/admin/restart-provider", tags=["Admin"])
async def restart_provider(_: bool = Security(verify_api_key)) -> Dict[str, str]:
    """Restart the CROO provider runtime (hot restart)."""
    await velora_provider.stop()
    asyncio.create_task(velora_provider.start())
    log.info("Provider restarted via admin endpoint")
    return {"status": "restarting"}


@app.get("/admin/orders", tags=["Admin"])
async def list_active_orders(_: bool = Security(verify_api_key)) -> Dict[str, Any]:
    """List currently executing orders."""
    from velora.croo.client import croo_client
    orders = await croo_client.list_active_orders()
    return {
        "active_in_memory": velora_provider.active_order_count,
        "paid_on_croo": len(orders),
        "orders": [{"id": o.id, "status": getattr(o, "status", "?"), "service_id": getattr(o, "service_id", "?")} for o in orders],
    }


# ── Global Error Handler ──────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("Unhandled exception", extra={"path": str(request.url.path), "error": str(exc)}, exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": str(exc)})
