# ABOUTME: Domain services for agentmem.
# ABOUTME: MemoryService composes protocol-typed adapters into ingest and retrieval operations.
"""Domain services — compose protocol-typed adapters into memory operations."""

from __future__ import annotations

from uuid import uuid4

from .models import (
    Evidence,
    EvidenceKind,
    RetrievalQuery,
    RetrievalResult,
    VectorEntry,
)
from .protocols import EmbeddingProvider, EventBus, EvidenceStore, VectorStore


class MemoryService:
    """Core memory service: ingest evidence and retrieve by semantic similarity."""

    def __init__(
        self,
        evidence_store: EvidenceStore,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
        event_bus: EventBus | None = None,
    ) -> None:
        self._evidence = evidence_store
        self._vectors = vector_store
        self._embeddings = embedding_provider
        self._events = event_bus

    async def ingest(
        self,
        tenant_id: str,
        content: str,
        kind: EvidenceKind,
        metadata: dict | None = None,
    ) -> Evidence:
        evidence = Evidence(
            tenant_id=tenant_id,
            content=content,
            kind=kind,
            metadata=metadata or {},
        )
        await self._evidence.put(evidence)

        embedding = await self._embeddings.embed(content)
        vector_entry = VectorEntry(
            id=uuid4(),
            ref_id=evidence.id,
            ref_type="evidence",
            embedding=embedding,
            tenant_id=tenant_id,
        )
        await self._vectors.upsert(vector_entry)

        if self._events:
            await self._events.publish(
                "evidence.ingested",
                {"tenant_id": tenant_id, "evidence_id": str(evidence.id)},
            )
        return evidence

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        embedding = await self._embeddings.embed(query.text)
        matches = await self._vectors.search(
            query.tenant_id, embedding, top_k=query.top_k
        )

        results: list[RetrievalResult] = []
        for ref_id, score in matches:
            evidence = await self._evidence.get(query.tenant_id, ref_id)
            if evidence is None:
                continue
            if query.kind_filter and evidence.kind != query.kind_filter:
                continue
            results.append(RetrievalResult(evidence=evidence, score=score))
        return results

    async def get(self, tenant_id: str, evidence_id: str) -> Evidence | None:
        from uuid import UUID

        return await self._evidence.get(tenant_id, UUID(evidence_id))

    async def list_evidence(
        self, tenant_id: str, limit: int = 100
    ) -> list[Evidence]:
        return await self._evidence.list(tenant_id, limit=limit)

    async def delete(self, tenant_id: str, evidence_id: str) -> bool:
        from uuid import UUID

        eid = UUID(evidence_id)
        await self._vectors.delete(eid)
        deleted = await self._evidence.delete(tenant_id, eid)
        if deleted and self._events:
            await self._events.publish(
                "evidence.deleted",
                {"tenant_id": tenant_id, "evidence_id": evidence_id},
            )
        return deleted
