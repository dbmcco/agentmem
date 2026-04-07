# ABOUTME: Webhook event source adapter for receiving HTTP push events.
# ABOUTME: Receives events via POST endpoint, optionally exposes a FastAPI router.
"""Webhook event source adapter for receiving HTTP push events."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class WebhookEventSourceAdapter:
    """HTTP webhook event source adapter — receives pushed events via POST endpoint."""

    def __init__(self, path: str = "/webhooks/events") -> None:
        self._path = path
        self._handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None

    async def connect(self) -> None:
        """No-op for HTTP adapter."""

    async def subscribe(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._handler = handler

    async def disconnect(self) -> None:
        self._handler = None

    def as_router(self):
        """Returns a FastAPI router with POST endpoint that calls self._handler."""
        from fastapi import APIRouter, Request
        router = APIRouter()

        @router.post(self._path)
        async def receive(request: Request):
            data = await request.json()
            records = data.get('records', [data])  # support both batch and single
            for record in records:
                event = self._normalize(record)
                if self._handler and event:
                    await self._handler(event)
            return {'status': 'ingested'}

        return router

    def _normalize(self, data: dict[str, Any]):
        """Handle both full EventEnvelope and slim push-delivery format."""
        try:
            # Check for required fields
            event_type = data['event_type']
            payload = data.get('payload', {})

            # Basic validation passed, return data for handler
            return {
                'event_type': event_type,
                'payload': payload,
                'occurred_at': data.get('occurred_at') or data.get('timestamp'),
                'dedupe_key': data.get('dedupe_key') or data.get('event_id', ''),
                'tenant_id': data.get('tenant_id'),
                'source_event_id': data.get('source_event_id') or data.get('event_id'),
            }
        except (KeyError, ValueError):
            return None
