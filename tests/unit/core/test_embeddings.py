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


    async def test_reindex_finds_unembedded_and_embeds_them(self, service, embedding_adapter, vector_store_adapter):
        # Given
        embedding_adapter.model_id = "test-model"
        vector_store_adapter.find_unembedded.return_value = [
            (123, "test content 1", "test-tenant"),
            (456, "test content 2", "test-tenant"),
        ]
        embedding_adapter.embed.side_effect = [[0.1, 0.2], [0.3, 0.4]]

        # When
        result = await service.reindex("evidence", "test-tenant", 50)

        # Then
        vector_store_adapter.find_unembedded.assert_called_once_with("evidence", "test-tenant", "test-model", 50)
        assert embedding_adapter.embed.call_count == 2
        embedding_adapter.embed.assert_any_call("test content 1")
        embedding_adapter.embed.assert_any_call("test content 2")
        assert vector_store_adapter.store.call_count == 2
        assert result == 2


    async def test_reindex_uses_default_values(self, service, embedding_adapter, vector_store_adapter):
        # Given
        embedding_adapter.model_id = "test-model"
        vector_store_adapter.find_unembedded.return_value = []

        # When
        result = await service.reindex("evidence")

        # Then
        vector_store_adapter.find_unembedded.assert_called_once_with("evidence", None, "test-model", 100)
        assert result == 0


    async def test_reindex_skips_failed_embeddings(self, service, embedding_adapter, vector_store_adapter):
        # Given
        embedding_adapter.model_id = "test-model"
        vector_store_adapter.find_unembedded.return_value = [
            (123, "test content 1", "test-tenant"),
            (456, "test content 2", "test-tenant"),
            (789, "test content 3", "test-tenant"),
        ]
        # Second embedding fails (returns None)
        embedding_adapter.embed.side_effect = [[0.1, 0.2], None, [0.5, 0.6]]

        # When
        result = await service.reindex("evidence", "test-tenant")

        # Then
        assert embedding_adapter.embed.call_count == 3
        assert vector_store_adapter.store.call_count == 2  # Only 2 successful embeddings stored
        assert result == 2  # Only count successful embeddings


    async def test_reindex_digests(self, service, embedding_adapter, vector_store_adapter):
        # Given
        embedding_adapter.model_id = "test-model"
        vector_store_adapter.find_unembedded.return_value = [
            (123, "digest content 1", "test-tenant"),
            (456, "digest content 2", "test-tenant"),
        ]
        embedding_adapter.embed.side_effect = [[0.1, 0.2], [0.3, 0.4]]

        # When
        result = await service.reindex("digests", "test-tenant", 50)

        # Then
        vector_store_adapter.find_unembedded.assert_called_once_with("digests", "test-tenant", "test-model", 50)
        assert embedding_adapter.embed.call_count == 2
        embedding_adapter.embed.assert_any_call("digest content 1")
        embedding_adapter.embed.assert_any_call("digest content 2")
        assert vector_store_adapter.store.call_count == 2
        assert result == 2

    async def test_digest_embedding_end_to_end_workflow(self, service, embedding_adapter, vector_store_adapter):
        """Test complete workflow: digest -> find_unembedded -> embed -> search."""
        # Given: A digest exists and embedding/vector services are set up
        embedding_adapter.model_id = "test-model"

        # Step 1: Digest shows up in find_unembedded
        digest_content = "This digest contains important historical information"
        vector_store_adapter.find_unembedded.return_value = [
            (123, digest_content, "test-tenant"),
        ]
        embedding_adapter.embed.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]

        # Step 2: Reindex embeds the digest
        result = await service.reindex("digests", "test-tenant", 10)
        assert result == 1

        # Verify embedding was stored with correct VectorRecord
        vector_store_adapter.store.assert_called_once()
        stored_record = vector_store_adapter.store.call_args[0][0]
        assert stored_record.source_table == "digests"
        assert stored_record.source_id == 123
        assert stored_record.embedding == [0.1, 0.2, 0.3, 0.4, 0.5]
        assert stored_record.tenant_id == "test-tenant"

        # Step 3: Semantic search can find the digest
        from agentmem.core.models import VectorResult, VectorFilters

        # Mock the search to return our digest
        search_results = [
            VectorResult(
                source_table="digests",
                source_id=123,
                tenant_id="test-tenant",
                content=digest_content,
                score=0.95
            )
        ]
        vector_store_adapter.search.return_value = search_results
        embedding_adapter.embed.return_value = [0.1, 0.2, 0.3, 0.4, 0.5]  # query embedding

        # When: Searching for content related to the digest
        filters = VectorFilters(tenant_id="test-tenant", limit=10)
        found_results = await service.search("historical information", filters)

        # Then: The digest should be found
        assert len(found_results) == 1
        assert found_results[0].source_table == "digests"
        assert found_results[0].source_id == 123
        assert found_results[0].content == digest_content
        assert found_results[0].score == 0.95
