# ABOUTME: PostgreSQL LISTEN/NOTIFY event source adapter for continuous event consumption.
# ABOUTME: Auto-reconnects with exponential backoff on connection loss.
"""PostgreSQL LISTEN/NOTIFY event adapter — requires agentmem[postgres]."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any


class PostgresListenAdapter:
    """PostgreSQL LISTEN/NOTIFY event adapter with auto-reconnect."""

    def __init__(
        self,
        dsn: str,
        channel: str = "agentmem_events",
        poll_interval: float = 1.0,
        max_backoff: float = 30.0,
    ) -> None:
        self._dsn = dsn
        self._channel = channel
        self._poll_interval = poll_interval
        self._max_backoff = max_backoff
        self._handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        self._running = True

    async def subscribe(
        self, handler: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        self._handler = handler
        self._task = asyncio.create_task(self._listen_loop())

    async def disconnect(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _listen_loop(self) -> None:
        try:
            import psycopg
        except ImportError as e:
            raise ImportError(
                "PostgresListenAdapter requires agentmem[postgres]"
            ) from e

        backoff = 1.0
        while self._running:
            try:
                async with await psycopg.AsyncConnection.connect(
                    self._dsn, autocommit=True
                ) as conn:
                    await conn.execute(f"LISTEN {self._channel}")
                    backoff = 1.0
                    async for notify in conn.notifies(timeout=self._poll_interval):
                        if not self._running:
                            break
                        payload = self._parse(notify.payload)
                        if payload and self._handler:
                            await self._handler(payload)
            except psycopg.OperationalError:
                if not self._running:
                    break
                await asyncio.sleep(min(backoff, self._max_backoff))
                backoff = min(backoff * 2, self._max_backoff)

    def _parse(self, payload: str) -> dict[str, Any] | None:
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None
