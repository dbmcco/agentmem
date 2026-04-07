# ABOUTME: EmbeddingService domain service.
# ABOUTME: Compute embeddings and store to VectorStore. Used by ingest and reindex jobs.
"""EmbeddingService: orchestrates embedding generation and vector storage."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentmem.core.models import VectorFilters, VectorRecord, VectorResult
    from agentmem.core.protocols import EmbeddingAdapter, VectorStore


class EmbeddingService:
    """Generates embeddings and manages the vector store.

    embed_and_store: computes embedding for content, writes VectorRecord to store.
    Returns None (and logs warning) if EmbeddingAdapter returns None (service unavailable).

    search: embeds query text then calls VectorStore.search.
    """

    def __init__(self, adapter: EmbeddingAdapter, store: VectorStore) -> None:
        self._adapter = adapter
        self._store = store

    @property
    def model_id(self) -> str:
        """Current embedding model identifier."""
        return self._adapter.model_id

    @property
    def dimensions(self) -> int:
        """Embedding vector dimensions."""
        return self._adapter.dimensions

    async def embed_and_store(
        self,
        source_table: str,   # "evidence" | "facets"
        source_id: int,
        content: str,
        tenant_id: str,
        collection: str = "default",
    ) -> VectorRecord | None:
        """Embed content and store as VectorRecord.

        Returns None if adapter returns None (service unavailable). Caller decides whether to
        skip silently (batch reindex) or raise (strict ingest mode).
        """
        embedding = await self._adapter.embed(content)
        if embedding is None:
            return None
        from agentmem.core.models import VectorRecord
        record = VectorRecord(
            tenant_id=tenant_id,
            source_table=source_table,
            source_id=source_id,
            model_id=self._adapter.model_id,
            embedding=embedding,
            collection=collection
        )
        await self._store.store(record)
        return record

    async def search(
        self,
        query: str,
        filters: VectorFilters,
    ) -> list[VectorResult]:
        """Embed query and search the vector store.

        Returns empty list if embed returns None.
        """
        embedding = await self._adapter.embed(query)
        if embedding is None:
            return []
        return await self._store.search(embedding, filters)

    async def embed(self, text: str) -> list[float] | None:
        """Embed text using the adapter. Returns None if service unavailable."""
        return await self._adapter.embed(text)

    async def store(self, record: VectorRecord) -> None:
        """Store a vector record."""
        await self._store.store(record)

    async def reindex(
        self,
        source_table: str,
        tenant_id: str | None = None,
        limit: int = 100
    ) -> int:
        """Reindex vectors by actually embedding and storing unembedded records.

        Returns number of vectors successfully processed (embedded and stored).
        """
        # Find records that need embedding for this model
        unembedded = await self._store.find_unembedded(
            source_table, tenant_id, self._adapter.model_id, limit
        )

        count = 0
        for source_id, content, record_tenant_id in unembedded:
            # Use embed_and_store to handle embedding and storage
            result = await self.embed_and_store(
                source_table, source_id, content, record_tenant_id
            )
            if result is not None:  # Only count successful embeddings
                count += 1

        return count
