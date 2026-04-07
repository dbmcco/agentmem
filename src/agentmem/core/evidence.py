# ABOUTME: EvidenceLedger domain service.
# ABOUTME: Accepts protocol-typed adapters only — no concrete imports. Handles dedup and optional embedding.
"""EvidenceLedger: domain service for evidence ingestion and retrieval."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentmem.core.models import (
        EvidenceFilters,
        EvidenceRecord,
        InsertResult,
    )
    from agentmem.core.protocols import EvidenceStore, VectorStore, EmbeddingAdapter
    from agentmem.core.embeddings import EmbeddingService


class EvidenceLedger:
    """Manages evidence ingestion (with dedup) and retrieval.

    Ingest flow:
      1. Insert record into EvidenceStore (returns InsertResult with deduplicated flag).
      2. If not deduplicated AND embedding provided on record → store to VectorStore immediately.
      3. If not deduplicated AND no embedding → EmbeddingService computes and stores asynchronously
         (or caller can defer to EmbedReindexJob).

    The embedding field on EvidenceRecord is NEVER stored on the evidence row itself.
    It is only routed to VectorStore.
    """

    def __init__(
        self,
        store: EvidenceStore,
        vector_store: VectorStore | None = None,
        embedding_service: EmbeddingService | EmbeddingAdapter | None = None,
    ) -> None:
        self._store = store
        self._vector_store = vector_store
        self._embedding_service = embedding_service

    async def ingest(self, record: EvidenceRecord) -> InsertResult:
        """Insert evidence record. Handles dedup, routes embedding to VectorStore.

        Returns InsertResult with deduplicated=True if dedupe_key already exists.
        """
        result = await self._store.insert(record)

        # Only process embeddings if record was not deduplicated and we have a vector store
        if not result.deduplicated and self._vector_store is not None:
            from agentmem.core.models import VectorRecord

            embedding = None
            model_id = None

            if record.embedding is not None:
                # Use precomputed embedding
                embedding = record.embedding
                model_id = "provided"
            elif self._embedding_service is not None:
                # Generate new embedding
                embedding = await self._embedding_service.embed(record.content)
                if embedding is not None:
                    model_id = self._embedding_service.model_id

            # Store vector if we have an embedding
            if embedding is not None and model_id is not None:
                vr = VectorRecord(
                    tenant_id=record.tenant_id,
                    source_table='evidence',
                    source_id=result.id,
                    model_id=model_id,
                    embedding=embedding,
                    collection='evidence'
                )
                await self._vector_store.store(vr)

        return result

    async def query(self, filters: EvidenceFilters) -> list[EvidenceRecord]:
        """Query evidence records matching filters."""
        return await self._store.query(filters)
