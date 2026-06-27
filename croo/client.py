"""
Velora — CROO Protocol Client
Wraps the official croo-sdk Python package.

Install: pip install croo-sdk
Package name on PyPI: croo-sdk
Import name: croo

Handles full order lifecycle:
  negotiation → accept → order_created → order_paid → deliver → settle
"""
from __future__ import annotations

import asyncio
import os
from typing import List, Optional

from croo import AgentClient, Config, ListOptions, DeliverOrderRequest, DeliverableType
from croo import APIError, is_not_found, is_insufficient_balance, is_invalid_status

from velora.core.config import settings
from velora.core.logger import get_logger

log = get_logger("velora.croo.client")


def _get_sdk_key() -> str:
    """
    Resolve CROO SDK key.
    Priority:
      1. $CROO_API_KEY  (Base44 secret — injected by platform)
      2. $CROO_SDK_KEY  (legacy env var name)
    """
    key = os.environ.get("CROO_API_KEY") or os.environ.get("CROO_SDK_KEY", "")
    if not key:
        raise RuntimeError(
            "CROO API key not found. Set CROO_API_KEY or CROO_SDK_KEY environment variable."
        )
    if not key.startswith("croo_sk_"):
        raise RuntimeError(
            f"CROO API key format invalid. Expected 'croo_sk_...' but got: {key[:12]}..."
        )
    return key


class CROOClient:
    """
    Production CROO SDK wrapper.

    Key behaviors:
    - Lazy-initializes the AgentClient on first use
    - Retries transient failures with exponential backoff
    - Structured logging on every CROO operation
    - Clean error mapping (not_found, insufficient_balance, invalid_status)
    """

    def __init__(self) -> None:
        self._client: Optional[AgentClient] = None

    def _build_client(self) -> AgentClient:
        sdk_key = _get_sdk_key()
        config = Config(
            base_url=settings.CROO_API_URL,      # https://api.croo.network
            ws_url=settings.CROO_WS_URL,          # wss://api.croo.network/ws
            rpc_url=settings.BASE_RPC_URL,         # https://mainnet.base.org
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

    async def accept_negotiation(self, negotiation_id: str) -> bool:
        """
        Accept a negotiation.
        CROO backend:
          1. Collects Provider Executor signature
          2. Submits createOrder on-chain
          3. Both parties receive order_created via WebSocket
        """
        for attempt in range(1, settings.DELIVERY_RETRY_ATTEMPTS + 1):
            try:
                result = await self.client.accept_negotiation(negotiation_id)
                log.info(
                    "Negotiation accepted",
                    extra={
                        "negotiation_id": negotiation_id,
                        "order_id": getattr(result, "order_id", None),
                    },
                )
                return True
            except APIError as e:
                if is_invalid_status(e):
                    # Already accepted/rejected/expired — not an error
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
                extra={"negotiation_id": negotiation_id, "code": e.code, "reason": e.reason},
            )

    async def get_negotiation(self, negotiation_id: str):
        try:
            return await self.client.get_negotiation(negotiation_id)
        except APIError as e:
            if is_not_found(e):
                return None
            raise

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
            log.info("Fetched paid (active) orders", extra={"count": len(orders)})
            return orders
        except APIError as e:
            log.error("list_orders failed", extra={"code": e.code, "reason": e.reason})
            return []

    # ── Delivery ──────────────────────────────────────────────────────────────

    async def deliver_order(self, order_id: str, result_text: str) -> bool:
        """
        Deliver completed task result.
        CROO flow:
          deliver_order → CROO verifies keccak256 hash → funds released from CAPVault
        Retries on transient failures.
        """
        for attempt in range(1, settings.DELIVERY_RETRY_ATTEMPTS + 1):
            try:
                req = DeliverOrderRequest(
                    deliverable_type=DeliverableType.TEXT,
                    deliverable_text=result_text,
                )
                await self.client.deliver_order(order_id, req)
                log.info(
                    "Order delivered successfully",
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
                    extra={"order_id": order_id, "error": str(e), "attempt": attempt},
                )
                if attempt < settings.DELIVERY_RETRY_ATTEMPTS:
                    await asyncio.sleep(settings.DELIVERY_RETRY_DELAY * attempt)

        log.error("All delivery attempts exhausted", extra={"order_id": order_id})
        return False

    async def deliver_order_file(self, order_id: str, file_name: str, file_bytes: bytes) -> bool:
        """Upload a file deliverable and deliver the download URL."""
        try:
            object_key = await self.client.upload_file(file_name, file_bytes)
            download_url = await self.client.get_download_url(object_key)
            return await self.deliver_order(order_id, f"Download your result: {download_url}")
        except Exception as e:
            log.error("File delivery failed", extra={"order_id": order_id, "error": str(e)})
            return False

    async def reject_order(self, order_id: str, reason: str) -> None:
        """
        Reject a paid order — triggers automatic refund to requester.
        Use only when Velora genuinely cannot execute the task.
        """
        try:
            await self.client.reject_order(order_id, reason)
            log.info("Order rejected", extra={"order_id": order_id, "reason": reason})
        except APIError as e:
            log.error(
                "reject_order failed",
                extra={"order_id": order_id, "code": e.code, "reason": e.reason},
            )

    # ── WebSocket ─────────────────────────────────────────────────────────────

    async def connect_websocket(self):
        """
        Open the CROO real-time event stream.

        CROO SDK features:
        - Auto-reconnect with exponential backoff (1s → 30s max)
        - Ping/pong heartbeat every 30s
        - Agent transitions from 'draft' to 'online' on first successful connect

        IMPORTANT: WebSocket callbacks are SYNCHRONOUS.
        Use asyncio.create_task() inside callbacks for async operations.
        """
        stream = await self.client.connect_websocket()
        log.info(
            "CROO WebSocket connected — Velora is now ONLINE",
            extra={"agent_id": settings.CROO_AGENT_ID},
        )
        return stream

    # ── Connection Test ───────────────────────────────────────────────────────

    async def test_connection(self) -> dict:
        """
        Verify the CROO API key and connection are working.
        Returns a status dict.
        """
        try:
            # List negotiations as a lightweight auth test
            opts = ListOptions(role="provider", status="pending", page=1, page_size=1)
            await self.client.list_negotiations(opts)
            return {
                "connected": True,
                "agent_id": settings.CROO_AGENT_ID,
                "api_url": settings.CROO_API_URL,
                "key_prefix": _get_sdk_key()[:16] + "...",
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
