# ABOUTME: Local in-process event bus adapter.
# ABOUTME: Simple pub/sub event distribution without external dependencies.
"""Local in-process event bus — zero external dependencies."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class LocalEventBus:
    """Simple in-process pub/sub event bus."""

    def __init__(self) -> None:
        HandlerT = Callable[[dict[str, Any]], Awaitable[None]]
        self._handlers: dict[str, list[HandlerT]] = {}
        self._history: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self._history.append((topic, payload))
        for handler in self._handlers.get(topic, []):
            await handler(payload)

    async def subscribe(
        self, topic: str, handler: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        self._handlers.setdefault(topic, []).append(handler)

    @property
    def history(self) -> list[tuple[str, dict[str, Any]]]:
        return list(self._history)
