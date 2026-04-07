# ABOUTME: PgListenAdapter — PostgreSQL LISTEN/NOTIFY event source.
# ABOUTME: Reconnect with exponential backoff. Replaces paia-memory's hardcoded background listener.
"""PgListenAdapter: PostgreSQL LISTEN/NOTIFY event source adapter."""
from __future__ import annotations

import json
from collections.abc import Callable, Awaitable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentmem.core.models import EventRecord


class PgListenAdapter:
    """PostgreSQL LISTEN/NOTIFY subscriber.

    Listens on the configured channel. Each notification payload must be valid JSON
    that deserialises to an EventRecord-compatible dict:
      {"event_type": str, "payload": dict, "occurred_at": ISO8601,
       "dedupe_key": str, "tenant_id": str|null, "source_event_id": str|null}

    Reconnect strategy: exponential backoff starting at 1s, max 30s, max 5 retries.
    After max retries, raises RuntimeError (coordinator will restart the job).
    """

    def __init__(
        self,
        dsn: str,
        channel: str = "paia_events",
        reconnect_initial_delay: float = 1.0,
        reconnect_max_delay: float = 30.0,
        reconnect_max_retries: int = 5,
    ) -> None:
        self._dsn = dsn
        self._channel = channel
        self._reconnect_initial_delay = reconnect_initial_delay
        self._reconnect_max_delay = reconnect_max_delay
        self._reconnect_max_retries = reconnect_max_retries
        self._conn = None
        self._connected = False

    async def connect(self) -> None:
        """Open a psycopg3 async connection and LISTEN on the channel.

        Uses psycopg.AsyncConnection.connect(dsn, autocommit=True).
        Executes: LISTEN {channel}
        """
        import psycopg
        self._conn = await psycopg.AsyncConnection.connect(self._dsn, autocommit=True)
        await self._conn.execute(f'LISTEN {self._channel}')
        self._connected = True

    async def subscribe(
        self, handler: Callable[[EventRecord], Awaitable[None]]
    ) -> None:
        """Block, delivering notifications to handler until disconnect.

        Uses conn.notifies() async generator. Parses JSON payload → EventRecord.
        Calls handler for each notification.
        On disconnect: reconnect with exponential backoff up to max_retries.
        """
        from agentmem.core.models import EventRecord
        from datetime import datetime

        async for notify in self._conn.notifies():
            payload = json.loads(notify.payload)
            occurred_at = datetime.fromisoformat(payload['occurred_at'])
            event = EventRecord(
                event_type=payload['event_type'],
                payload=payload.get('payload', {}),
                occurred_at=occurred_at,
                dedupe_key=payload.get('dedupe_key', ''),
                tenant_id=payload.get('tenant_id'),
                source_event_id=payload.get('source_event_id'),
            )
            await handler(event)

    async def disconnect(self) -> None:
        """Close the connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            self._connected = False
