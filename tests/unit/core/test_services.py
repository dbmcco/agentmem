# ABOUTME: Tests for the core MemoryService.
# ABOUTME: Verifies ingest and retrieve operations with in-memory adapters.
"""Tests for the core MemoryService — ingest and retrieve."""

from agentmem.adapters.embeddings import HashEmbeddingProvider
from agentmem.adapters.events import LocalEventBus
from agentmem.adapters.storage import MemoryEvidenceStore, MemoryVectorStore
from agentmem.core.models import EvidenceKind, RetrievalQuery
from agentmem.core.services import MemoryService


def _make_service() -> tuple[MemoryService, LocalEventBus]:
    events = LocalEventBus()
    svc = MemoryService(
        evidence_store=MemoryEvidenceStore(),
        vector_store=MemoryVectorStore(),
        embedding_provider=HashEmbeddingProvider(),
        event_bus=events,
    )
    return svc, events


async def test_ingest_stores_evidence():
    svc, events = _make_service()
    ev = await svc.ingest("t1", "The sky is blue", EvidenceKind.FACT)
    assert ev.tenant_id == "t1"
    assert ev.content == "The sky is blue"
    assert ev.kind == EvidenceKind.FACT
    assert len(events.history) == 1
    assert events.history[0][0] == "evidence.ingested"


async def test_retrieve_returns_ingested_evidence():
    svc, _ = _make_service()
    await svc.ingest("t1", "Python is a programming language", EvidenceKind.FACT)
    await svc.ingest("t1", "The weather is sunny today", EvidenceKind.OBSERVATION)

    results = await svc.retrieve(
        RetrievalQuery(tenant_id="t1", text="programming", top_k=5)
    )
    assert len(results) == 2
    assert all(r.score is not None for r in results)


async def test_retrieve_filters_by_kind():
    svc, _ = _make_service()
    await svc.ingest("t1", "I like coffee", EvidenceKind.PREFERENCE)
    await svc.ingest("t1", "Water boils at 100C", EvidenceKind.FACT)

    results = await svc.retrieve(
        RetrievalQuery(
            tenant_id="t1", text="coffee", top_k=10, kind_filter=EvidenceKind.PREFERENCE
        )
    )
    assert all(r.evidence.kind == EvidenceKind.PREFERENCE for r in results)


async def test_retrieve_isolates_tenants():
    svc, _ = _make_service()
    await svc.ingest("t1", "Tenant one data", EvidenceKind.FACT)
    await svc.ingest("t2", "Tenant two data", EvidenceKind.FACT)

    results = await svc.retrieve(
        RetrievalQuery(tenant_id="t1", text="data", top_k=10)
    )
    assert all(r.evidence.tenant_id == "t1" for r in results)


async def test_delete_removes_evidence():
    svc, events = _make_service()
    ev = await svc.ingest("t1", "To be deleted", EvidenceKind.OBSERVATION)
    deleted = await svc.delete("t1", str(ev.id))
    assert deleted is True

    results = await svc.retrieve(
        RetrievalQuery(tenant_id="t1", text="deleted", top_k=10)
    )
    assert len(results) == 0
    assert events.history[-1][0] == "evidence.deleted"


async def test_list_evidence():
    svc, _ = _make_service()
    await svc.ingest("t1", "First", EvidenceKind.FACT)
    await svc.ingest("t1", "Second", EvidenceKind.FACT)

    items = await svc.list_evidence("t1")
    assert len(items) == 2


async def test_get_evidence():
    svc, _ = _make_service()
    ev = await svc.ingest("t1", "Specific evidence", EvidenceKind.FACT)
    fetched = await svc.get("t1", str(ev.id))
    assert fetched is not None
    assert fetched.content == "Specific evidence"
