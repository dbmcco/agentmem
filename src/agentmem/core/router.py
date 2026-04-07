# ABOUTME: EventRouter — maps event_type glob patterns to content formatters and routing targets.
# ABOUTME: Replaces paia-memory's hardcoded event_bridge.py with pluggable pattern dispatch.
"""EventRouter: pluggable event-type-to-content mapping.

Usage:
    router = EventRouter()
    router.register("gmail.*", lambda e: f"Email: {e.payload['subject']}", section="email")
    router.register("gcal.*", lambda e: f"Calendar: {e.payload['title']}", section="calendar")
    router.register("*", lambda e: str(e.payload))  # fallback

    content = router.format(event)
    section = router.section_for(event)
"""
from __future__ import annotations

import fnmatch
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentmem.core.models import EventRecord


@dataclass
class _Route:
    pattern: str
    formatter: Callable[[EventRecord], str]
    section: str | None


class EventRouter:
    """Map event_type glob patterns to content formatters and routing targets.

    Routes are matched in registration order; first match wins.
    """

    def __init__(self) -> None:
        self._routes: list[_Route] = []

    def register(
        self,
        pattern: str,
        formatter: Callable[[EventRecord], str],
        section: str | None = None,
    ) -> None:
        """Register a pattern → formatter mapping.

        Args:
            pattern:   glob pattern matched against event.event_type (e.g. "gmail.*", "*")
            formatter: callable(EventRecord) → str; produces the content string to store
            section:   optional active context section name to update with formatted content
        """
        self._routes.append(_Route(pattern=pattern, formatter=formatter, section=section))

    def format(self, event: EventRecord) -> str:
        """Return formatted content string for the first matching route.

        Raises KeyError if no route matches (callers should register a "*" fallback).
        """
        for route in self._routes:
            if fnmatch.fnmatch(event.event_type, route.pattern):
                return route.formatter(event)
        raise KeyError(f'No route matches event_type={event.event_type!r}. Register a "*" fallback.')

    def section_for(self, event: EventRecord) -> str | None:
        """Return the section name for the first matching route, or None."""
        for route in self._routes:
            if fnmatch.fnmatch(event.event_type, route.pattern):
                return route.section
        return None
