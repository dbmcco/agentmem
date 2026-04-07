# ABOUTME: ActiveContextStore domain service.
# ABOUTME: Named sections of live working context. Upserted by ActiveContextJob from event stream.
"""ActiveContextStore: domain service for live named context sections."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentmem.core.models import ContextSection
    from agentmem.core.protocols import ActiveContextStoreProtocol


class ActiveContextStore:
    """Manages named sections of live active context.

    Sections are upserted by ActiveContextJob as events arrive.
    Consumers (agents) read via get_all() to build context window.
    max_age_seconds filter lets callers exclude stale sections.
    """

    def __init__(self, store: ActiveContextStoreProtocol) -> None:
        self._store = store

    async def upsert(self, section: ContextSection) -> ContextSection:
        """Upsert a named context section. Returns stored section (with updated_at populated)."""
        return await self._store.upsert(section)

    async def get_all(
        self,
        tenant_id: str,
        max_age_seconds: float | None = None,
    ) -> list[ContextSection]:
        """Return all context sections for tenant.

        If max_age_seconds is set, only sections updated within that window are returned.
        Age is measured as seconds since section.updated_at.
        """
        return await self._store.get_all(tenant_id, max_age_seconds)

    async def delete(self, tenant_id: str, section: str) -> bool:
        """Delete a named section. Returns True if deleted, False if not found."""
        return await self._store.delete(tenant_id, section)
