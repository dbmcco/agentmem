# ABOUTME: GraphStore domain service.
# ABOUTME: Subject-predicate-object triplet knowledge graph. Accepts protocol-typed adapters only.
"""GraphStore: domain service for knowledge graph triplets."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentmem.core.models import Triplet
    from agentmem.core.protocols import GraphStoreProtocol


class GraphStore:
    """Manages subject-predicate-object triplets (knowledge graph)."""

    def __init__(self, store: GraphStoreProtocol) -> None:
        self._store = store

    async def add(self, triplet: Triplet) -> Triplet:
        """Add a triplet. Upserts on (tenant_id, subject, predicate, object)."""
        return await self._store.add(triplet)

    async def query_subject(self, tenant_id: str, subject: str) -> list[Triplet]:
        """Return all triplets where subject matches."""
        return await self._store.query_subject(tenant_id, subject)

    async def query_object(self, tenant_id: str, object_: str) -> list[Triplet]:
        """Return all triplets where object matches."""
        return await self._store.query_object(tenant_id, object_)

    async def query_predicate(self, tenant_id: str, predicate: str) -> list[Triplet]:
        """Return all triplets with the given predicate."""
        return await self._store.query_predicate(tenant_id, predicate)
