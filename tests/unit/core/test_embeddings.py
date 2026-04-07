# ABOUTME: Tests for EmbeddingService domain service.
# ABOUTME: Verifies delegation to EmbeddingAdapter and VectorStoreAdapter.

import pytest
from unittest.mock import AsyncMock, Mock

from agentmem.core.embeddings import EmbeddingService
from agentmem.core.models import VectorRecord, VectorFilters, VectorResult


class TestEmbeddingService:

    @pytest.fixture
    def embedding_adapter(self):
        return AsyncMock()

    @pytest.fixture
    def vector_store_adapter(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, embedding_adapter, vector_store_adapter):
        return EmbeddingService(embedding_adapter, vector_store_adapter)


    async def test_embed_delegates_to_embedding_adapter(self, service, embedding_adapter):
        # Given
        embedding_adapter.embed.return_value = [0.1, 0.2, 0.3]

        # When
        result = await service.embed("test text")

        # Then
        embedding_adapter.embed.assert_called_once_with("test text")
        assert result == [0.1, 0.2, 0.3]


    async def test_embed_returns_none_when_adapter_returns_none(self, service, embedding_adapter):
        # Given
        embedding_adapter.embed.return_value = None

        # When
        result = await service.embed("test text")

        # Then
        assert result is None


    async def test_store_delegates_to_vector_store(self, service, vector_store_adapter):
        # Given
        record = VectorRecord(
            tenant_id="test-tenant",
            source_table="evidence",
            source_id=123,
            model_id="hash-64d",
            embedding=[0.1, 0.2, 0.3]
        )

        # When
        await service.store(record)

        # Then
        vector_store_adapter.store.assert_called_once_with(record)


    async def test_search_embeds_query_then_searches_vector_store(self, service, embedding_adapter, vector_store_adapter):
        # Given
        query_embedding = [0.1, 0.2, 0.3]
        embedding_adapter.embed.return_value = query_embedding

        filters = VectorFilters(tenant_id="test-tenant", limit=5)
        expected_results = [
            VectorResult(
                source_table="evidence",
                source_id=123,
                tenant_id="test-tenant",
                content="test content",
                score=0.95
            )
        ]
        vector_store_adapter.search.return_value = expected_results

        # When
        results = await service.search("test query", filters)

        # Then
        embedding_adapter.embed.assert_called_once_with("test query")
        vector_store_adapter.search.assert_called_once_with(query_embedding, filters)
        assert results == expected_results


    async def test_search_returns_empty_when_embed_returns_none(self, service, embedding_adapter, vector_store_adapter):
        # Given
        embedding_adapter.embed.return_value = None
        filters = VectorFilters(tenant_id="test-tenant")

        # When
        results = await service.search("test query", filters)

        # Then
        embedding_adapter.embed.assert_called_once_with("test query")
        vector_store_adapter.search.assert_not_called()
        assert results == []


    async def test_reindex_delegates_to_vector_store(self, service, vector_store_adapter):
        # Given
        vector_store_adapter.reindex.return_value = 42

        # When
        result = await service.reindex("evidence", "test-tenant", 50)

        # Then
        vector_store_adapter.reindex.assert_called_once_with("evidence", "test-tenant", 50)
        assert result == 42


    async def test_reindex_uses_default_values(self, service, vector_store_adapter):
        # Given
        vector_store_adapter.reindex.return_value = 100

        # When
        result = await service.reindex("evidence")

        # Then
        vector_store_adapter.reindex.assert_called_once_with("evidence", None, 100)
        assert result == 100
