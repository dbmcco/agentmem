# ABOUTME: EvidenceLedger domain service — append-only evidence ingestion and retrieval.
# ABOUTME: Wraps EvidenceStoreAdapter and EmbeddingAdapter; auto-embeds on ingest.

from __future__ import annotations

from .models import EvidenceRecord, InsertResult, EvidenceFilters, VectorRecord
from .protocols import EvidenceStoreAdapter, VectorStoreAdapter, EmbeddingAdapter


class EvidenceLedger:
    def __init__(
        self,
        store: EvidenceStoreAdapter,
        vector_store: VectorStoreAdapter | None = None,
        embedding: EmbeddingAdapter | None = None,
    ) -> None:
        self._store = store
        self._vector_store = vector_store
        self._embedding = embedding

    async def ingest(self, record: EvidenceRecord) -> InsertResult:
        # 1. Use pre-computed embedding if provided
        embedding = record.embedding

        # 2. Auto-embed if service available and no pre-computed embedding
        if embedding is None and self._embedding:
            embedding = await self._embedding.embed(record.content)

        # 3. Insert evidence (dedupe on dedupe_key)
        result = await self._store.insert(record)

        # 4. Store embedding in VectorStore (if we have one and insert succeeded)
        if not result.deduplicated and embedding and self._vector_store and result.id:
            await self._vector_store.store(VectorRecord(
                tenant_id=record.tenant_id,
                source_table='evidence',
                source_id=result.id,
                model_id=self._embedding.model_id if self._embedding else 'provided',
                embedding=embedding,
                collection='evidence',
            ))

        return result

    async def query(self, filters: EvidenceFilters) -> list[EvidenceRecord]:
        return await self._store.query(filters)