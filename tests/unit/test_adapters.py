# ABOUTME: Tests for in-memory adapter implementations.
# ABOUTME: Verifies storage, embedding, and event bus adapters work correctly.
"""Tests for in-memory adapters."""

from uuid import uuid4

from agentmem.adapters.embeddings import HashEmbeddingProvider
from agentmem.adapters.events import LocalEventBus
from agentmem.adapters.storage import (
    MemoryEvidenceStore,
    MemoryFacetStore,
    MemoryJobStore,
    MemoryVectorStore,
)
from agentmem.core.models import Evidence, EvidenceKind, Facet, JobState, VectorEntry


async def test_evidence_store_crud():
    store = MemoryEvidenceStore()
    ev = Evidence(tenant_id="t1", content="test", kind=EvidenceKind.FACT)
    await store.put(ev)

    fetched = await store.get("t1", ev.id)
    assert fetched is not None
    assert fetched.content == "test"

    items = await store.list("t1")
    assert len(items) == 1

    deleted = await store.delete("t1", ev.id)
    assert deleted is True
    assert await store.get("t1", ev.id) is None


async def test_facet_store_crud():
    store = MemoryFacetStore()
    facet = Facet(tenant_id="t1", key="name", value="Alice")
    await store.put(facet)

    fetched = await store.get("t1", "name")
    assert fetched is not None
    assert fetched.value == "Alice"

    items = await store.list("t1")
    assert len(items) == 1

    deleted = await store.delete("t1", "name")
    assert deleted is True


async def test_vector_store_search():
    store = MemoryVectorStore()
    ref_id = uuid4()
    entry = VectorEntry(
        id=uuid4(),
        ref_id=ref_id,
        ref_type="evidence",
        embedding=[1.0, 0.0, 0.0],
        tenant_id="t1",
    )
    await store.upsert(entry)

    results = await store.search("t1", [1.0, 0.0, 0.0], top_k=5)
    assert len(results) == 1
    assert results[0][0] == ref_id
    assert results[0][1] > 0.99  # cosine similarity ~1.0


async def test_vector_store_tenant_isolation():
    store = MemoryVectorStore()
    await store.upsert(
        VectorEntry(id=uuid4(), ref_id=uuid4(), ref_type="evidence",
                     embedding=[1.0], tenant_id="t1")
    )
    await store.upsert(
        VectorEntry(id=uuid4(), ref_id=uuid4(), ref_type="evidence",
                     embedding=[1.0], tenant_id="t2")
    )
    results = await store.search("t1", [1.0], top_k=10)
    assert len(results) == 1


async def test_hash_embedding_deterministic():
    provider = HashEmbeddingProvider(dimensions=32)
    a = await provider.embed("hello world")
    b = await provider.embed("hello world")
    assert a == b
    assert len(a) == 32
    assert provider.dimensions == 32


async def test_hash_embedding_different_inputs():
    provider = HashEmbeddingProvider()
    a = await provider.embed("hello")
    b = await provider.embed("world")
    assert a != b


async def test_local_event_bus():
    bus = LocalEventBus()
    received: list[dict] = []

    async def handler(payload: dict) -> None:
        received.append(payload)

    await bus.subscribe("test.topic", handler)
    await bus.publish("test.topic", {"key": "value"})
    assert len(received) == 1
    assert received[0]["key"] == "value"
    assert len(bus.history) == 1


async def test_job_store():
    store = MemoryJobStore()
    state = JobState(name="test_job", status="idle")
    await store.put_state(state)

    fetched = await store.get_state("test_job")
    assert fetched is not None
    assert fetched.status == "idle"

    states = await store.list_states()
    assert len(states) == 1
