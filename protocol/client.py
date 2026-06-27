"""
Velora — CROO Protocol Client
Wraps croo-sdk v0.2.1 (pip install croo-sdk).

Correct SDK types confirmed from source:
  Negotiation.negotiation_id  (not .id)
  Order.order_id              (not .id)
  Event.negotiation_id / .order_id
  EventType.NEGOTIATION_CREATED = "order_negotiation_created"
  DeliverOrderRequest(deliverable_type=str, deliverable_text=str)
  DeliverableType.TEXT = "text"
  accept_negotiation(negotiation_id: str) -> AcceptNegotiationResult
  deliver_order(order_id: str, req: DeliverOrderRequest) -> DeliverOrderResult
"""
from __future__ import annotations

import asyncio
import os
from typing import List, Optional

from croo import (
    AgentClient, Config, ListOptions,
    DeliverOrderRequest, DeliverableType,
    APIError, is_not_found, is_invalid_status,
)

from core.config import settings
from core.logger import get_logger

log = get_logger("velora.protocol.client")


def _get_sdk_key() -> str:
    """
    Resolve CROO SDK key — checks two env var names:
      CROO_API_KEY  — Base44 platform secret injection
      CROO_SDK_KEY  — local .env / Render env var name
    """
    key = os.environ.get("CROO_API_KEY") or os.environ.get("CROO_SDK_KEY", "")
    if not key:
        raise RuntimeError(
            "CROO API key not found. Set CROO_API_KEY or CROO_SDK_KEY. "
            "Get your key from https://agent.croo.network"
        )
    return key


class CROOClient:
    """
    Production CROO SDK wrapper with retry logic and structured logging.
    Implements full order lifecycle: negotiate → accept → pay → deliver → settle
    """

    def __init__(self) -> None:
        self._client: Optional[AgentClient] = None

    def _build_client(self) -> AgentClient:
        sdk_key = _get_sdk_key()
        config = Config(
            base_url=settings.CROO_API_URL,
            ws_url=settings.CROO_WS_URL,
            rpc_url=settings.BASE_RPC_URL,
        )
        log.info(
            "Initializing CROO AgentClient",
            extra={
                "api_url": settings.CROO_API_URL,
                "ws_url": settings.CROO_WS_URL,
                "agent_id": settings.CROO_AGENT_ID,
                "key_prefix": sdk_key[:16] + "...",
            },
        )
        return AgentClient(config, sdk_key)

    @property
    def client(self) -> AgentClient:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    # ── Negotiation ──────────────────────────────────────────────────────────

    async def list_pending_negotiations(self) -> list:
        """Return all pending negotiations where Velora is the provider."""
        try:
            opts = ListOptions(role="provider", status="pending", page=1, page_size=50)
            negs = await self.client.list_negotiations(opts)
            log.info("Fetched pending negotiations", extra={"count": len(negs)})
            return negs
        except APIError as e:
            log.error("list_negotiations failed", extra={"code": e.code, "reason": e.reason})
            return []
        except Exception as e:
            log.error("list_negotiations unexpected error", extra={"error": str(e)})
            return []

    async def accept_negotiation(self, negotiation_id: str) -> bool:
        """
        Accept negotiation. CROO backend:
          1. Collects Provider Executor signature
          2. Submits createOrder on-chain
          3. Both parties get order_created via WebSocket
        """
        for attempt in range(1, settings.DELIVERY_RETRY_ATTEMPTS + 1):
            try:
                result = await self.client.accept_negotiation(negotiation_id)
                log.info(
                    "Negotiation accepted",
                    extra={
                        "negotiation_id": negotiation_id,
                        "order_id": result.order.order_id if result.order else None,
                    },
                )
                return True
            except APIError as e:
                if is_invalid_status(e):
                    log.warning(
                        "Negotiation already in terminal state",
                        extra={"negotiation_id": negotiation_id, "code": e.code},
                    )
                    return False
                log.warning(
                    f"accept_negotiation attempt {attempt} failed",
                    extra={"negotiation_id": negotiation_id, "error": str(e)},
                )
                if attempt < settings.DELIVERY_RETRY_ATTEMPTS:
                    await asyncio.sleep(settings.DELIVERY_RETRY_DELAY * attempt)
            except Exception as e:
                log.error(
                    f"accept_negotiation unexpected error attempt {attempt}",
                    extra={"negotiation_id": negotiation_id, "error": str(e)},
                )
                if attempt < settings.DELIVERY_RETRY_ATTEMPTS:
                    await asyncio.sleep(settings.DELIVERY_RETRY_DELAY * attempt)
        return False

    async def reject_negotiation(self, negotiation_id: str, reason: str) -> None:
        try:
            await self.client.reject_negotiation(negotiation_id, reason)
            log.info(
                "Negotiation rejected",
                extra={"negotiation_id": negotiation_id, "reason": reason},
            )
        except APIError as e:
            log.error(
                "reject_negotiation failed",
                extra={"negotiation_id": negotiation_id, "code": e.code},
            )

    # ── Order ─────────────────────────────────────────────────────────────────

    async def get_order(self, order_id: str):
        try:
            return await self.client.get_order(order_id)
        except APIError as e:
            if is_not_found(e):
                log.warning("Order not found", extra={"order_id": order_id})
                return None
            raise

    async def list_active_orders(self) -> list:
        """List all paid orders waiting for delivery."""
        try:
            opts = ListOptions(role="provider", status="paid", page=1, page_size=50)
            orders = await self.client.list_orders(opts)
            log.info("Fetched paid orders", extra={"count": len(orders)})
            return orders
        except APIError as e:
            log.error("list_orders failed", extra={"code": e.code, "reason": e.reason})
            return []
        except Exception as e:
            log.error("list_orders unexpected error", extra={"error": str(e)})
            return []

    # ── Delivery ──────────────────────────────────────────────────────────────

    async def deliver_order(self, order_id: str, result_text: str) -> bool:
        """
        Deliver completed task. CROO verifies keccak256 hash then releases
        USDC from CAPVault to Velora's AA wallet.
        """
        for attempt in range(1, settings.DELIVERY_RETRY_ATTEMPTS + 1):
            try:
                req = DeliverOrderRequest(
                    deliverable_type=DeliverableType.TEXT,
                    deliverable_text=result_text,
                )
                await self.client.deliver_order(order_id, req)
                log.info(
                    "Order delivered",
                    extra={
                        "order_id": order_id,
                        "result_length": len(result_text),
                        "attempt": attempt,
                    },
                )
                return True
            except APIError as e:
                if is_invalid_status(e):
                    log.warning(
                        "Order not in deliverable state",
                        extra={"order_id": order_id, "code": e.code},
                    )
                    return False
                log.warning(
                    f"deliver_order attempt {attempt} failed",
                    extra={"order_id": order_id, "error": str(e)},
                )
                if attempt < settings.DELIVERY_RETRY_ATTEMPTS:
                    await asyncio.sleep(settings.DELIVERY_RETRY_DELAY * attempt)
            except Exception as e:
                log.error(
                    f"deliver_order unexpected error attempt {attempt}",
                    extra={"order_id": order_id, "error": str(e)},
                )
                if attempt < settings.DELIVERY_RETRY_ATTEMPTS:
                    await asyncio.sleep(settings.DELIVERY_RETRY_DELAY * attempt)

        log.error("All delivery attempts exhausted", extra={"order_id": order_id})
        return False

    async def deliver_order_file(
        self, order_id: str, file_name: str, file_bytes: bytes
    ) -> bool:
        """Upload file deliverable and deliver the download URL."""
        try:
            object_key = await self.client.upload_file(file_name, file_bytes)
            download_url = await self.client.get_download_url(object_key)
            return await self.deliver_order(
                order_id, f"Your file is ready: {download_url}"
            )
        except Exception as e:
            log.error("File delivery failed", extra={"order_id": order_id, "error": str(e)})
            return False

    async def reject_order(self, order_id: str, reason: str) -> None:
        """Reject a paid order — triggers automatic refund to requester."""
        try:
            await self.client.reject_order(order_id, reason)
            log.info("Order rejected", extra={"order_id": order_id, "reason": reason})
        except APIError as e:
            log.error(
                "reject_order failed",
                extra={"order_id": order_id, "code": e.code},
            )

    # ── WebSocket ─────────────────────────────────────────────────────────────

    async def connect_websocket(self):
        """
        Open CROO real-time event stream.
        Agent transitions: draft → online on first successful connect.
        SDK auto-reconnects with exponential backoff (1s → 30s).
        """
        stream = await self.client.connect_websocket()
        log.info(
            "CROO WebSocket connected — Velora is ONLINE",
            extra={"agent_id": settings.CROO_AGENT_ID},
        )
        return stream

    # ── Health Check ──────────────────────────────────────────────────────────

    async def test_connection(self) -> dict:
        """Verify CROO API key and connection work."""
        try:
            opts = ListOptions(role="provider", status="pending", page=1, page_size=1)
            await self.client.list_negotiations(opts)
            sdk_key = _get_sdk_key()
            return {
                "connected": True,
                "agent_id": settings.CROO_AGENT_ID,
                "api_url": settings.CROO_API_URL,
                "key_prefix": sdk_key[:16] + "...",
            }
        except APIError as e:
            return {
                "connected": False,
                "error": str(e),
                "code": e.code,
                "reason": e.reason,
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    # ── Cleanup ───────────────────────────────────────────────────────────────

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
            log.info("CROO client closed")


# Module-level singleton
croo_client = CROOClient()
