# ABOUTME: Unit tests for core domain services.
# ABOUTME: Tests all 6 core domain services using InMemoryStorageAdapter and HashEmbeddingAdapter.
"""Unit tests for core domain services."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from agentmem.core.models import (
    EvidenceRecord, EvidenceFilters, FacetRecord, Triplet, ContextSection,
    DigestFilters, VectorFilters,
)
from agentmem.core.evidence import EvidenceLedger
from agentmem.core.facets import FacetStore
from agentmem.core.graph import GraphStore
from agentmem.core.digests import DigestEngine
from agentmem.core.active_context import ActiveContextStore
from agentmem.core.embeddings import EmbeddingService


@pytest.mark.asyncio
async def test_evidence_ingest_returns_result(mem_adapter, hash_adapter):
    """Test that evidence ingest returns an InsertResult."""
    evidence = EvidenceLedger(mem_adapter, mem_adapter, None)

    record = EvidenceRecord(
        tenant_id="test-tenant",
        event_type="message",
        content="Hello world",
        occurred_at=datetime.now(timezone.utc),
        source_event_id="msg-123",
        dedupe_key="unique-key-1"
    )

    result = await evidence.ingest(record)
    assert result.dedupe_key == "unique-key-1"
    assert result.deduplicated is False
    assert result.id is not None


@pytest.mark.asyncio
async def test_evidence_ingest_dedup(mem_adapter, hash_adapter):
    """Test that evidence ingest detects duplicates."""
    evidence = EvidenceLedger(mem_adapter, mem_adapter, None)

    record = EvidenceRecord(
        tenant_id="test-tenant",
        event_type="message",
        content="Hello world",
        occurred_at=datetime.now(timezone.utc),
        source_event_id="msg-123",
        dedupe_key="duplicate-key"
    )

    # First ingest
    result1 = await evidence.ingest(record)
    assert result1.deduplicated is False

    # Second ingest with same dedupe_key
    result2 = await evidence.ingest(record)
    assert result2.deduplicated is True
    assert result2.id == result1.id


@pytest.mark.asyncio
async def test_evidence_ingest_stores_precomputed_embedding(mem_adapter, hash_adapter):
    """Test that evidence with precomputed embedding is stored to VectorStore."""
    evidence = EvidenceLedger(mem_adapter, mem_adapter, None)

    embedding = [0.1, 0.2, 0.3, 0.4]  # Mock embedding
    record = EvidenceRecord(
        tenant_id="test-tenant",
        event_type="message",
        content="Hello world",
        occurred_at=datetime.now(timezone.utc),
        source_event_id="msg-123",
        dedupe_key="embed-key-1",
        embedding=embedding
    )

    result = await evidence.ingest(record)
    assert result.deduplicated is False

    # Check that vector record was stored
    # The InMemoryStorageAdapter stores vectors in self.vectors dict
    # Key is (source_table, source_id, model_id)
    vector_key = ("evidence", result.id, "provided")
    assert vector_key in mem_adapter.vectors
    assert mem_adapter.vectors[vector_key]["embedding"] == embedding


@pytest.mark.asyncio
async def test_evidence_query(mem_adapter, hash_adapter):
    """Test evidence query functionality."""
    evidence = EvidenceLedger(mem_adapter, mem_adapter, None)

    # Insert test records
    now = datetime.now(timezone.utc)
    record1 = EvidenceRecord(
        tenant_id="test-tenant",
        event_type="message",
        content="First message",
        occurred_at=now,
        source_event_id="msg-1",
        dedupe_key="key-1"
    )
    record2 = EvidenceRecord(
        tenant_id="test-tenant",
        event_type="action",
        content="Second message",
        occurred_at=now,
        source_event_id="msg-2",
        dedupe_key="key-2"
    )

    await evidence.ingest(record1)
    await evidence.ingest(record2)

    # Query all records
    filters = EvidenceFilters(tenant_id="test-tenant", limit=10)
    results = await evidence.query(filters)
    assert len(results) == 2

    # Query by event type
    filters = EvidenceFilters(tenant_id="test-tenant", event_type="message", limit=10)
    results = await evidence.query(filters)
    assert len(results) == 1
    assert results[0].content == "First message"


@pytest.mark.asyncio
async def test_facet_set_and_get(mem_adapter, hash_adapter):
    """Test facet set and get operations."""
    facets = FacetStore(mem_adapter)

    record = FacetRecord(
        tenant_id="test-tenant",
        key="preference.theme",
        value="dark",
        confidence=0.9,
        layer="user"
    )

    # Set facet
    stored = await facets.set(record)
    assert stored.id is not None
    assert stored.key == "preference.theme"
    assert stored.value == "dark"

    # Get facet
    retrieved = await facets.get("test-tenant", "preference.theme")
    assert retrieved is not None
    assert retrieved.value == "dark"
    assert retrieved.confidence == 0.9

    # Get non-existent facet
    missing = await facets.get("test-tenant", "nonexistent")
    assert missing is None


@pytest.mark.asyncio
async def test_facet_list_prefix_filter(mem_adapter, hash_adapter):
    """Test facet listing with prefix filter."""
    facets = FacetStore(mem_adapter)

    # Set multiple facets with different prefixes
    await facets.set(FacetRecord(
        tenant_id="test-tenant", key="user.name", value="John", confidence=1.0, layer="system"
    ))
    await facets.set(FacetRecord(
        tenant_id="test-tenant", key="user.email", value="john@example.com", confidence=1.0, layer="system"
    ))
    await facets.set(FacetRecord(
        tenant_id="test-tenant", key="config.theme", value="light", confidence=1.0, layer="user"
    ))

    # List all facets
    all_facets = await facets.list("test-tenant")
    assert len(all_facets) == 3

    # List with prefix filter
    user_facets = await facets.list("test-tenant", prefix="user.")
    assert len(user_facets) == 2
    assert all(f.key.startswith("user.") for f in user_facets)

    # List with layer filter
    system_facets = await facets.list("test-tenant", layer="system")
    assert len(system_facets) == 2
    assert all(f.layer == "system" for f in system_facets)


@pytest.mark.asyncio
async def test_facet_delete(mem_adapter, hash_adapter):
    """Test facet deletion."""
    facets = FacetStore(mem_adapter)

    # Set a facet
    await facets.set(FacetRecord(
        tenant_id="test-tenant", key="temp.data", value="delete-me", confidence=1.0, layer="temp"
    ))

    # Verify it exists
    retrieved = await facets.get("test-tenant", "temp.data")
    assert retrieved is not None

    # Delete it
    deleted = await facets.delete("test-tenant", "temp.data")
    assert deleted is True

    # Verify it's gone
    missing = await facets.get("test-tenant", "temp.data")
    assert missing is None

    # Try to delete again
    deleted_again = await facets.delete("test-tenant", "temp.data")
    assert deleted_again is False


@pytest.mark.asyncio
async def test_graph_add_and_query_subject(mem_adapter, hash_adapter):
    """Test graph triplet addition and subject queries."""
    graph = GraphStore(mem_adapter)

    # Add triplets
    triplet1 = Triplet(
        tenant_id="test-tenant",
        subject="John",
        predicate="likes",
        object="coffee",
        confidence=0.8,
        source="user_input"
    )
    triplet2 = Triplet(
        tenant_id="test-tenant",
        subject="John",
        predicate="works_at",
        object="Acme Corp",
        confidence=0.9,
        source="profile"
    )

    stored1 = await graph.add(triplet1)
    stored2 = await graph.add(triplet2)
    assert stored1.id is not None
    assert stored2.id is not None

    # Query by subject
    john_triplets = await graph.query_subject("test-tenant", "John")
    assert len(john_triplets) == 2

    predicates = {t.predicate for t in john_triplets}
    assert "likes" in predicates
    assert "works_at" in predicates


@pytest.mark.asyncio
async def test_digest_generate_and_list(mem_adapter, hash_adapter):
    """Test digest generation and listing."""
    # Setup evidence store with some records
    evidence = EvidenceLedger(mem_adapter, mem_adapter, None)
    digests = DigestEngine(mem_adapter, mem_adapter)

    start_time = datetime.now(timezone.utc)
    end_time = start_time.replace(hour=23, minute=59, second=59)

    # Insert some evidence records
    record1 = EvidenceRecord(
        tenant_id="test-tenant",
        event_type="message",
        content="Morning message",
        occurred_at=start_time,
        source_event_id="msg-1",
        dedupe_key="digest-key-1"
    )
    record2 = EvidenceRecord(
        tenant_id="test-tenant",
        event_type="action",
        content="Afternoon action",
        occurred_at=start_time.replace(hour=14),
        source_event_id="msg-2",
        dedupe_key="digest-key-2"
    )

    await evidence.ingest(record1)
    await evidence.ingest(record2)

    # Generate digest
    digest = await digests.generate(
        tenant_id="test-tenant",
        digest_type="daily",
        period_start=start_time,
        period_end=end_time
    )

    assert digest.tenant_id == "test-tenant"
    assert digest.digest_type == "daily"
    assert "[message] Morning message" in digest.content
    assert "[action] Afternoon action" in digest.content

    # List digests
    filters = DigestFilters(tenant_id="test-tenant", limit=10)
    digest_list = await digests.list(filters)
    assert len(digest_list) == 1
    assert digest_list[0].digest_type == "daily"


@pytest.mark.asyncio
async def test_active_context_upsert_and_get(mem_adapter, hash_adapter):
    """Test active context upsert and retrieval."""
    context_store = ActiveContextStore(mem_adapter)

    section = ContextSection(
        tenant_id="test-tenant",
        section="current_task",
        content="Working on unit tests"
    )

    # Upsert section
    stored = await context_store.upsert(section)
    assert stored.section == "current_task"
    assert stored.content == "Working on unit tests"
    assert stored.updated_at is not None

    # Get all sections
    sections = await context_store.get_all("test-tenant")
    assert len(sections) == 1
    assert sections[0].section == "current_task"

    # Test with max_age_seconds filter
    recent_sections = await context_store.get_all("test-tenant", max_age_seconds=3600)
    assert len(recent_sections) == 1


@pytest.mark.asyncio
async def test_embedding_embed_and_store(mem_adapter, hash_adapter):
    """Test embedding generation and storage."""
    embedding_service = EmbeddingService(hash_adapter, mem_adapter)

    # Test properties
    assert embedding_service.model_id == hash_adapter.model_id
    assert embedding_service.dimensions == hash_adapter.dimensions

    # Embed and store
    record = await embedding_service.embed_and_store(
        source_table="evidence",
        source_id=123,
        content="Test content for embedding",
        tenant_id="test-tenant",
        collection="test"
    )

    assert record is not None
    assert record.source_table == "evidence"
    assert record.source_id == 123
    assert record.tenant_id == "test-tenant"
    assert record.collection == "test"
    assert record.model_id == hash_adapter.model_id
    assert len(record.embedding) == hash_adapter.dimensions


@pytest.mark.asyncio
async def test_embedding_search(mem_adapter, hash_adapter):
    """Test embedding search functionality."""
    embedding_service = EmbeddingService(hash_adapter, mem_adapter)

    # Store some embeddings first
    await embedding_service.embed_and_store(
        source_table="evidence",
        source_id=1,
        content="coffee shop morning",
        tenant_id="test-tenant"
    )
    await embedding_service.embed_and_store(
        source_table="evidence",
        source_id=2,
        content="afternoon tea break",
        tenant_id="test-tenant"
    )

    # Search
    filters = VectorFilters(tenant_id="test-tenant", limit=5)
    results = await embedding_service.search("coffee morning", filters)

    assert len(results) >= 1
    assert all(r.tenant_id == "test-tenant" for r in results)
    assert all(r.source_table == "evidence" for r in results)
    # Results should be sorted by score (highest first)
    if len(results) > 1:
        assert results[0].score >= results[1].score