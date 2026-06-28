"""
Velora — CROO Provider Runtime
Listens for CROO events, executes tasks, delivers results.

Order lifecycle:
  negotiation_created → accept → order_created → order_paid → execute → deliver → settle
"""
from __future__ import annotations

import asyncio
from typing import Dict, Optional

from croo import EventType, Event

from core.config import settings
from core.logger import get_logger
from protocol.client import croo_client
from skills.router import skill_router

log = get_logger("velora.croo.provider")

_RECONNECT_DELAYS = [5, 10, 20, 30, 60]   # seconds — capped at 60s


class VeloraProvider:
    """
    Production CROO provider runtime.
    Single WebSocket connection enforced via _ws_lock.
    Auto-reconnects with exponential back-off on disconnect.
    """

    def __init__(self) -> None:
        self._active_orders: Dict[str, asyncio.Task] = {}
        self._stream = None
        self._running = False
        self._ws_lock = asyncio.Lock()   # prevents duplicate connections
        self._reconnect_attempt = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            log.warning("VeloraProvider.start() called while already running — ignoring")
            return

        self._running = True
        log.info("VeloraProvider starting", extra={"agent_id": settings.CROO_AGENT_ID})

        # Pick up any paid orders missed during downtime
        await self._recover_pending_orders()

        # Main event loop with back-off reconnect
        while self._running:
            try:
                await self._run_event_loop()
                self._reconnect_attempt = 0   # reset on clean exit
            except Exception as e:
                delay = _RECONNECT_DELAYS[
                    min(self._reconnect_attempt, len(_RECONNECT_DELAYS) - 1)
                ]
                self._reconnect_attempt += 1
                log.error(
                    "Provider event loop crashed — reconnecting",
                    extra={"error": str(e), "retry_in_seconds": delay, "attempt": self._reconnect_attempt},
                )
                await asyncio.sleep(delay)

    async def stop(self) -> None:
        self._running = False
        for task in self._active_orders.values():
            task.cancel()
        if self._stream:
            try:
                await self._stream.close()
            except Exception:
                pass
            self._stream = None
        await croo_client.close()
        log.info("VeloraProvider stopped")

    # ── Event Loop ────────────────────────────────────────────────────────

    async def _run_event_loop(self) -> None:
        # Guard: only one WebSocket at a time
        async with self._ws_lock:
            if self._stream is not None:
                log.warning("WebSocket already open — closing stale connection first")
                try:
                    await self._stream.close()
                except Exception:
                    pass
                self._stream = None

            self._stream = await croo_client.connect_websocket()

        log.info("CROO WebSocket stream active")

        # Register handlers
        self._stream.on(EventType.NEGOTIATION_CREATED,  self._on_negotiation_created)
        self._stream.on(EventType.NEGOTIATION_REJECTED, self._on_negotiation_rejected)
        self._stream.on(EventType.NEGOTIATION_EXPIRED,  self._on_negotiation_expired)
        self._stream.on(EventType.ORDER_CREATED,        self._on_order_created)
        self._stream.on(EventType.ORDER_PAID,           self._on_order_paid)
        self._stream.on(EventType.ORDER_COMPLETED,      self._on_order_completed)
        self._stream.on(EventType.ORDER_REJECTED,       self._on_order_rejected)
        self._stream.on(EventType.ORDER_EXPIRED,        self._on_order_expired)

        # Keep alive — SDK handles ping/pong
        while self._running:
            await asyncio.sleep(1)

    # ── Event Handlers ─────────────────────────────────────────────────────

    def _on_negotiation_created(self, event: Event) -> None:
        negotiation_id = event.negotiation_id
        log.info("Negotiation received", extra={"negotiation_id": negotiation_id})

        if len(self._active_orders) >= settings.MAX_CONCURRENT_ORDERS:
            log.warning(
                "Concurrency limit reached — rejecting",
                extra={"negotiation_id": negotiation_id, "active": len(self._active_orders)},
            )
            asyncio.create_task(
                croo_client.reject_negotiation(
                    negotiation_id, "Provider at capacity. Please retry shortly."
                )
            )
            return

        if settings.NEGOTIATION_AUTO_ACCEPT:
            asyncio.create_task(self._handle_accept_negotiation(negotiation_id))

    def _on_negotiation_rejected(self, event: Event) -> None:
        log.info("Negotiation rejected by requester",
                 extra={"negotiation_id": getattr(event, "negotiation_id", "?")})

    def _on_negotiation_expired(self, event: Event) -> None:
        log.info("Negotiation expired",
                 extra={"negotiation_id": getattr(event, "negotiation_id", "?")})

    def _on_order_created(self, event: Event) -> None:
        log.info("Order created on-chain, awaiting payment",
                 extra={"order_id": event.order_id})

    def _on_order_paid(self, event: Event) -> None:
        order_id = event.order_id
        log.info("Order PAID — beginning execution", extra={"order_id": order_id})

        if order_id in self._active_orders:
            log.warning("Duplicate order_paid event — ignoring",
                        extra={"order_id": order_id})
            return

        task = asyncio.create_task(self._execute_and_deliver(order_id))
        self._active_orders[order_id] = task
        task.add_done_callback(lambda t: self._active_orders.pop(order_id, None))

    def _on_order_completed(self, event: Event) -> None:
        log.info("Order completed and USDC settled 💰",
                 extra={"order_id": event.order_id})

    def _on_order_rejected(self, event: Event) -> None:
        self._active_orders.pop(event.order_id, None)
        log.info("Order rejected", extra={"order_id": event.order_id})

    def _on_order_expired(self, event: Event) -> None:
        order_id = event.order_id
        log.warning("Order expired — requester auto-refunded",
                    extra={"order_id": order_id})
        task = self._active_orders.pop(order_id, None)
        if task:
            task.cancel()

    # ── Core Execution ────────────────────────────────────────────────────

    async def _handle_accept_negotiation(self, negotiation_id: str) -> None:
        success = await croo_client.accept_negotiation(negotiation_id)
        if not success:
            log.warning("Failed to accept negotiation",
                        extra={"negotiation_id": negotiation_id})

    async def _execute_and_deliver(self, order_id: str) -> None:
        try:
            order = await croo_client.get_order(order_id)
            if not order:
                log.error("Could not fetch order", extra={"order_id": order_id})
                return

            requirements = self._extract_requirements(order)
            service_id   = getattr(order, "service_id", "unknown")

            log.info(
                "Executing task",
                extra={
                    "order_id": order_id,
                    "service_id": service_id,
                    "preview": str(requirements)[:200],
                },
            )

            try:
                result = await asyncio.wait_for(
                    skill_router.execute(
                        service_id=service_id,
                        requirements=requirements,
                        order_id=order_id,
                    ),
                    timeout=settings.TASK_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                log.error("Task timed out", extra={"order_id": order_id})
                await croo_client.reject_order(
                    order_id, "Task execution timed out. Please retry."
                )
                return

            delivered = await croo_client.deliver_order(order_id, result)
            if not delivered:
                log.error("All delivery attempts failed",
                          extra={"order_id": order_id})

        except Exception as e:
            log.error(
                "Unexpected error during execution",
                extra={"order_id": order_id, "error": str(e)},
                exc_info=True,
            )
            try:
                await croo_client.reject_order(order_id, "Internal error. Please retry.")
            except Exception:
                pass

    def _extract_requirements(self, order) -> dict:
        req = {}
        if hasattr(order, "requirements_text") and order.requirements_text:
            req["text"] = order.requirements_text
        if hasattr(order, "requirements_data") and order.requirements_data:
            req.update(order.requirements_data)
        if hasattr(order, "service_name"):
            req["service_name"] = order.service_name
        if hasattr(order, "service_description"):
            req["service_description"] = order.service_description
        return req

    # ── Recovery ─────────────────────────────────────────────────────────

    async def _recover_pending_orders(self) -> None:
        orders = await croo_client.list_active_orders()
        if not orders:
            return

        log.info("Recovering paid orders from previous session",
                 extra={"count": len(orders)})
        for order in orders:
            order_id = getattr(order, "order_id", getattr(order, "id", None))
            if order_id and order_id not in self._active_orders:
                task = asyncio.create_task(self._execute_and_deliver(order_id))
                self._active_orders[order_id] = task
                task.add_done_callback(
                    lambda t, oid=order_id: self._active_orders.pop(oid, None)
                )

    # ── Health ────────────────────────────────────────────────────────────

    @property
    def active_order_count(self) -> int:
        return len(self._active_orders)

    @property
    def is_running(self) -> bool:
        return self._running


# Singleton
velora_provider = VeloraProvider()
