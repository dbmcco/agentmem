# ABOUTME: ActiveContextStore domain service — named section working memory.
# ABOUTME: Layer 2 operating picture updated by event-driven ActiveContextJob.

from agentmem.core.models import ContextSection
from agentmem.core.protocols import ActiveContextStoreAdapter


class ActiveContextStore:
    def __init__(self, store: ActiveContextStoreAdapter) -> None:
        self._store = store

    async def upsert(self, tenant_id: str, section: str, content: str) -> ContextSection:
        return await self._store.upsert(ContextSection(tenant_id=tenant_id, section=section, content=content))

    async def get_all(self, tenant_id: str, max_age_seconds: float | None = None) -> list[ContextSection]:
        return await self._store.get_all(tenant_id, max_age_seconds)

    async def delete(self, tenant_id: str, section: str) -> bool:
        return await self._store.delete(tenant_id, section)