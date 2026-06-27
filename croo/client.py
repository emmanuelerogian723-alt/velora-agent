"""
Velora — CROO Protocol Client
Wraps the official croo-sdk Python package.
Handles: negotiation → accept → pay → deliver → settle
Full order lifecycle with retries, structured logging, and error mapping.
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from croo import AgentClient, Config, EventType, Event, ListOptions
from croo import APIError, is_not_found, is_insufficient_balance, is_invalid_status

from velora.core.config import settings
from velora.core.logger import get_logger

log = get_logger("velora.croo.client")


class CROOClient:
    """
    Thin wrapper around the official CROO SDK AgentClient.
    Adds:
      - retry logic on transient errors
      - structured logging on every operation
      - clean error propagation
    """

    def __init__(self) -> None:
        self._client: Optional[AgentClient] = None

    def _build_client(self) -> AgentClient:
        config = Config(
            base_url=settings.CROO_API_URL,
            ws_url=settings.CROO_WS_URL,
            rpc_url=settings.BASE_RPC_URL,
        )
        return AgentClient(config, settings.CROO_SDK_KEY)

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
            log.error("Failed to list negotiations", extra={"code": e.code, "reason": e.reason})
            return []

    async def accept_negotiation(self, negotiation_id: str) -> bool:
        """Accept a negotiation and trigger on-chain order creation."""
        for attempt in range(1, settings.DELIVERY_RETRY_ATTEMPTS + 1):
            try:
                result = await self.client.accept_negotiation(negotiation_id)
                log.info(
                    "Negotiation accepted",
                    extra={"negotiation_id": negotiation_id, "order_id": getattr(result, "order_id", None)},
                )
                return True
            except APIError as e:
                if is_invalid_status(e):
                    log.warning("Negotiation already in invalid state", extra={"negotiation_id": negotiation_id})
                    return False
                log.warning(
                    f"Accept negotiation attempt {attempt} failed",
                    extra={"negotiation_id": negotiation_id, "error": str(e)},
                )
                if attempt < settings.DELIVERY_RETRY_ATTEMPTS:
                    await asyncio.sleep(settings.DELIVERY_RETRY_DELAY * attempt)
        return False

    async def reject_negotiation(self, negotiation_id: str, reason: str) -> None:
        try:
            await self.client.reject_negotiation(negotiation_id, reason)
            log.info("Negotiation rejected", extra={"negotiation_id": negotiation_id, "reason": reason})
        except APIError as e:
            log.error("Failed to reject negotiation", extra={"negotiation_id": negotiation_id, "error": str(e)})

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
        try:
            opts = ListOptions(role="provider", status="paid", page=1, page_size=50)
            orders = await self.client.list_orders(opts)
            log.info("Fetched active orders", extra={"count": len(orders)})
            return orders
        except APIError as e:
            log.error("Failed to list orders", extra={"error": str(e)})
            return []

    # ── Delivery ──────────────────────────────────────────────────────────────

    async def deliver_order(self, order_id: str, result_text: str) -> bool:
        """
        Deliver a completed task to the requester.
        Retries on transient failures.  Returns True on success.
        """
        from croo import DeliverableType

        for attempt in range(1, settings.DELIVERY_RETRY_ATTEMPTS + 1):
            try:
                await self.client.deliver_order(
                    order_id,
                    {"deliverable_type": DeliverableType.TEXT, "deliverable_text": result_text},
                )
                log.info(
                    "Order delivered",
                    extra={"order_id": order_id, "result_length": len(result_text)},
                )
                return True
            except APIError as e:
                if is_invalid_status(e):
                    log.warning("Order not in deliverable state", extra={"order_id": order_id})
                    return False
                log.warning(
                    f"Delivery attempt {attempt} failed",
                    extra={"order_id": order_id, "error": str(e), "attempt": attempt},
                )
                if attempt < settings.DELIVERY_RETRY_ATTEMPTS:
                    await asyncio.sleep(settings.DELIVERY_RETRY_DELAY * attempt)
        log.error("All delivery attempts exhausted", extra={"order_id": order_id})
        return False

    async def deliver_order_with_file(self, order_id: str, file_name: str, file_bytes: bytes) -> bool:
        """Upload a file deliverable and deliver the download URL."""
        try:
            object_key = await self.client.upload_file(file_name, file_bytes)
            download_url = await self.client.get_download_url(object_key)
            return await self.deliver_order(order_id, f"[Download Result]: {download_url}")
        except Exception as e:
            log.error("File delivery failed", extra={"order_id": order_id, "error": str(e)})
            return False

    async def reject_order(self, order_id: str, reason: str) -> None:
        try:
            await self.client.reject_order(order_id, reason)
            log.info("Order rejected", extra={"order_id": order_id, "reason": reason})
        except APIError as e:
            log.error("Failed to reject order", extra={"order_id": order_id, "error": str(e)})

    # ── WebSocket ─────────────────────────────────────────────────────────────

    async def connect_websocket(self):
        """Open the CROO WebSocket stream and return it."""
        stream = await self.client.connect_websocket()
        log.info("CROO WebSocket connected")
        return stream

    # ── Cleanup ───────────────────────────────────────────────────────────────

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            log.info("CROO client closed")


# Singleton
croo_client = CROOClient()
