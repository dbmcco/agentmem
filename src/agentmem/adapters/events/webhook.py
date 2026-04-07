# ABOUTME: WebhookAdapter — HTTP push receiver for incoming events.
# ABOUTME: FastAPI router that accepts POST /events, validates payload, calls handler.
"""WebhookAdapter: HTTP webhook event source adapter."""
from __future__ import annotations

from collections.abc import Callable, Awaitable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentmem.core.models import EventRecord


class WebhookAdapter:
    """HTTP webhook event source adapter.

    Provides a FastAPI APIRouter (mount_router()) that receives POST requests.
    Event payload format (JSON body):
      {"event_type": str, "payload": dict, "occurred_at": ISO8601,
       "dedupe_key": str, "tenant_id": str|null, "source_event_id": str|null}

    Usage:
        adapter = WebhookAdapter(mount_path="/webhooks/events")
        await adapter.connect()
        await adapter.subscribe(handler)   # non-blocking; handler called per POST
        app.include_router(adapter.router)
    """

    def __init__(self, mount_path: str = "/webhooks/events") -> None:
        from fastapi import APIRouter, Request
        self._mount_path = mount_path
        self._handler = None
        self._router = APIRouter()

        @self._router.post(mount_path)
        async def receive_event(request: Request):
            from agentmem.core.models import EventRecord
            import json
            from datetime import datetime
            body = await request.json()
            occurred_at = datetime.fromisoformat(body['occurred_at'])
            event = EventRecord(
                event_type=body['event_type'],
                payload=body.get('payload', {}),
                occurred_at=occurred_at,
                dedupe_key=body.get('dedupe_key', ''),
                tenant_id=body.get('tenant_id'),
                source_event_id=body.get('source_event_id'),
            )
            if self._handler:
                await self._handler(event)
            return {'status': 'ok'}

    @property
    def router(self):  # -> fastapi.APIRouter
        """FastAPI router to mount into the service app."""
        return self._router

    async def connect(self) -> None:
        """No-op for webhook (connection is inbound). Required by EventSourceAdapter protocol."""
        pass

    async def subscribe(
        self, handler: Callable[[EventRecord], Awaitable[None]]
    ) -> None:
        """Register the handler called for each incoming webhook POST.

        Non-blocking — the handler is called from the FastAPI route handler.
        """
        self._handler = handler

    async def disconnect(self) -> None:
        """No-op. Required by EventSourceAdapter protocol."""
        pass
