# ABOUTME: FacetStore domain service.
# ABOUTME: Key-value structured memory. Accepts protocol-typed adapters only.
"""FacetStore: domain service for structured facet (key-value) memory."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentmem.core.models import FacetRecord
    from agentmem.core.protocols import FacetStoreProtocol


class FacetStore:
    """Manages structured key-value memory (facets).

    Facets represent long-lived identity signals (user preferences, learned facts).
    They are NOT deleted by RetentionJob.
    """

    def __init__(self, store: FacetStoreProtocol) -> None:
        self._store = store

    async def set(self, record: FacetRecord) -> FacetRecord:
        """Upsert a facet record. Returns the stored record (with id populated)."""
        return await self._store.set(record)

    async def get(self, tenant_id: str, key: str) -> FacetRecord | None:
        """Return facet by key, or None if not found."""
        return await self._store.get(tenant_id, key)

    async def list(
        self,
        tenant_id: str,
        prefix: str | None = None,
        layer: str | None = None,
    ) -> list[FacetRecord]:
        """List facets for tenant, optionally filtered by key prefix and layer."""
        return await self._store.list(tenant_id, prefix, layer)

    async def list_multi(
        self,
        tenant_ids: list[str],
        prefix: str | None = None,
        layer: str | None = None,
    ) -> list[FacetRecord]:
        """List facets across multiple tenants (multi-tenant blending)."""
        return await self._store.list_multi(tenant_ids, prefix, layer)

    async def delete(self, tenant_id: str, key: str) -> bool:
        """Delete a facet by key. Returns True if deleted, False if not found."""
        return await self._store.delete(tenant_id, key)
