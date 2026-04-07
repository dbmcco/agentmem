# ABOUTME: Tests for EvidenceLedger domain service.
# ABOUTME: Verifies evidence ingestion, deduplication, and auto-embedding functionality.

import pytest
from unittest.mock import AsyncMock

from agentmem.core.models import EvidenceRecord, InsertResult, EvidenceFilters, VectorRecord
from agentmem.core.evidence import EvidenceLedger


class TestEvidenceLedger:

    @pytest.fixture
    def evidence_store(self):
        return AsyncMock()

    @pytest.fixture
    def vector_store(self):
        return AsyncMock()

    @pytest.fixture
    def embedding_adapter(self):
        adapter = AsyncMock()
        adapter.model_id = 'test-model'
        return adapter

    @pytest.fixture
    def evidence_record(self):
        return EvidenceRecord(
            tenant_id="test-tenant",
            event_type="test_event",
            content="Test content",
            occurred_at="2023-01-01T00:00:00",
            source_event_id="source-123",
            dedupe_key="dedupe-123"
        )

    async def test_ingest_with_no_embedding_service_stores_record(self, evidence_store):
        # Given
        ledger = EvidenceLedger(evidence_store)
        evidence_store.insert.return_value = InsertResult(id=1, dedupe_key="dedupe-123", deduplicated=False)

        evidence = EvidenceRecord(
            tenant_id="test-tenant",
            event_type="test_event",
            content="Test content",
            occurred_at="2023-01-01T00:00:00",
            source_event_id="source-123",
            dedupe_key="dedupe-123"
        )

        # When
        result = await ledger.ingest(evidence)

        # Then
        evidence_store.insert.assert_called_once_with(evidence)
        assert result.id == 1
        assert result.deduplicated is False

    async def test_ingest_deduplication_returns_deduplicated_true(self, evidence_store):
        # Given
        ledger = EvidenceLedger(evidence_store)
        evidence_store.insert.return_value = InsertResult(id=None, dedupe_key="dedupe-123", deduplicated=True)

        evidence = EvidenceRecord(
            tenant_id="test-tenant",
            event_type="test_event",
            content="Test content",
            occurred_at="2023-01-01T00:00:00",
            source_event_id="source-123",
            dedupe_key="dedupe-123"
        )

        # When
        result = await ledger.ingest(evidence)

        # Then
        assert result.deduplicated is True
        assert result.id is None

    async def test_ingest_with_embedding_service_calls_embed_and_stores_vector(self, evidence_store, vector_store, embedding_adapter):
        # Given
        ledger = EvidenceLedger(evidence_store, vector_store, embedding_adapter)
        evidence_store.insert.return_value = InsertResult(id=1, dedupe_key="dedupe-123", deduplicated=False)
        embedding_adapter.embed.return_value = [0.1, 0.2, 0.3]

        evidence = EvidenceRecord(
            tenant_id="test-tenant",
            event_type="test_event",
            content="Test content",
            occurred_at="2023-01-01T00:00:00",
            source_event_id="source-123",
            dedupe_key="dedupe-123"
        )

        # When
        result = await ledger.ingest(evidence)

        # Then
        embedding_adapter.embed.assert_called_once_with("Test content")
        vector_store.store.assert_called_once_with(VectorRecord(
            tenant_id="test-tenant",
            source_table='evidence',
            source_id=1,
            model_id='test-model',
            embedding=[0.1, 0.2, 0.3],
            collection='evidence'
        ))

    async def test_ingest_with_precomputed_embedding_skips_embed(self, evidence_store, vector_store, embedding_adapter):
        # Given
        ledger = EvidenceLedger(evidence_store, vector_store, embedding_adapter)
        evidence_store.insert.return_value = InsertResult(id=1, dedupe_key="dedupe-123", deduplicated=False)

        evidence = EvidenceRecord(
            tenant_id="test-tenant",
            event_type="test_event",
            content="Test content",
            occurred_at="2023-01-01T00:00:00",
            source_event_id="source-123",
            dedupe_key="dedupe-123",
            embedding=[0.5, 0.6, 0.7]  # Pre-computed
        )

        # When
        result = await ledger.ingest(evidence)

        # Then
        embedding_adapter.embed.assert_not_called()
        vector_store.store.assert_called_once_with(VectorRecord(
            tenant_id="test-tenant",
            source_table='evidence',
            source_id=1,
            model_id='provided',
            embedding=[0.5, 0.6, 0.7],
            collection='evidence'
        ))

    async def test_ingest_with_embedding_returning_none_stores_evidence_no_vector(self, evidence_store, vector_store, embedding_adapter):
        # Given
        ledger = EvidenceLedger(evidence_store, vector_store, embedding_adapter)
        evidence_store.insert.return_value = InsertResult(id=1, dedupe_key="dedupe-123", deduplicated=False)
        embedding_adapter.embed.return_value = None

        evidence = EvidenceRecord(
            tenant_id="test-tenant",
            event_type="test_event",
            content="Test content",
            occurred_at="2023-01-01T00:00:00",
            source_event_id="source-123",
            dedupe_key="dedupe-123"
        )

        # When
        result = await ledger.ingest(evidence)

        # Then
        embedding_adapter.embed.assert_called_once_with("Test content")
        evidence_store.insert.assert_called_once_with(evidence)
        vector_store.store.assert_not_called()
        assert result.id == 1

    async def test_query_with_tenant_id_only_delegates_to_store(self, evidence_store):
        # Given
        ledger = EvidenceLedger(evidence_store)
        filters = EvidenceFilters(tenant_id="test-tenant")
        expected_records = [
            EvidenceRecord(
                tenant_id="test-tenant",
                event_type="event1",
                content="Content 1",
                occurred_at="2023-01-01T00:00:00",
                source_event_id="source-1",
                dedupe_key="dedupe-1"
            )
        ]
        evidence_store.query.return_value = expected_records

        # When
        result = await ledger.query(filters)

        # Then
        evidence_store.query.assert_called_once_with(filters)
        assert result == expected_records

    async def test_query_with_event_type_filter_delegates_to_store(self, evidence_store):
        # Given
        ledger = EvidenceLedger(evidence_store)
        filters = EvidenceFilters(tenant_id="test-tenant", event_type="specific_event")
        expected_records = []
        evidence_store.query.return_value = expected_records

        # When
        result = await ledger.query(filters)

        # Then
        evidence_store.query.assert_called_once_with(filters)
        assert result == expected_records

    async def test_query_with_since_filter_delegates_to_store(self, evidence_store):
        # Given
        ledger = EvidenceLedger(evidence_store)
        filters = EvidenceFilters(tenant_id="test-tenant", since="2023-01-01T00:00:00")
        evidence_store.query.return_value = []

        # When
        result = await ledger.query(filters)

        # Then
        evidence_store.query.assert_called_once_with(filters)

    async def test_query_with_limit_delegates_to_store(self, evidence_store):
        # Given
        ledger = EvidenceLedger(evidence_store)
        filters = EvidenceFilters(tenant_id="test-tenant", limit=10)
        evidence_store.query.return_value = []

        # When
        result = await ledger.query(filters)

        # Then
        evidence_store.query.assert_called_once_with(filters)