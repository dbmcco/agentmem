# ABOUTME: Shared pytest fixtures for agentmem test suite.
# ABOUTME: Provides InMemoryStorageAdapter and HashEmbeddingAdapter for unit tests (no Postgres needed).
"""Shared test fixtures.

Unit tests use InMemoryStorageAdapter (no Postgres required).
Integration tests use a real Postgres instance (see tests/integration/conftest.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agentmem.adapters.embeddings.hash import HashEmbeddingAdapter
from agentmem.core.models import ContextSection, EvidenceRecord, FacetRecord, Triplet


class InMemoryStorageAdapter:
    """In-memory storage adapter for unit tests.

    Implements all six store protocols using plain dicts and lists.
    No external services required. Thread-unsafe (single-threaded tests only).
    """

    def __init__(self) -> None:
        self.evidence: list[dict] = []
        self.facets: dict[tuple[str, str], dict] = {}    # (tenant_id, key) → row
        self.graph: list[dict] = []
        self.digests: list[dict] = []
        self.context: dict[tuple[str, str], dict] = {}   # (tenant_id, section) → row
        self.vectors: dict[tuple[str, int, str], dict] = {}  # (source_table, source_id, model_id)
        self._next_id = 1

    def _new_id(self) -> int:
        id_ = self._next_id
        self._next_id += 1
        return id_

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def migrate(self) -> None:
        pass

    # ── EvidenceStore ─────────────────────────────────────────────────────────

    async def insert(self, record: EvidenceRecord):
        from agentmem.core.models import InsertResult
        existing = next(
            (r for r in self.evidence if r["dedupe_key"] == record.dedupe_key), None
        )
        if existing:
            return InsertResult(id=existing["id"], dedupe_key=record.dedupe_key, deduplicated=True)
        id_ = self._new_id()
        row = {
            "id": id_, "tenant_id": record.tenant_id, "event_type": record.event_type,
            "content": record.content, "occurred_at": record.occurred_at,
            "source_event_id": record.source_event_id, "dedupe_key": record.dedupe_key,
            "metadata": record.metadata, "channel_id": record.channel_id,
        }
        self.evidence.append(row)
        return InsertResult(id=id_, dedupe_key=record.dedupe_key, deduplicated=False)

    async def query(self, filters):
        rows = [r for r in self.evidence if r["tenant_id"] == filters.tenant_id]
        if filters.event_type:
            rows = [r for r in rows if r["event_type"] == filters.event_type]
        if filters.since:
            rows = [r for r in rows if r["occurred_at"] >= filters.since]
        if filters.channel_id:
            rows = [r for r in rows if r.get("channel_id") == filters.channel_id]
        rows = sorted(rows, key=lambda r: r["occurred_at"], reverse=True)[: filters.limit]
        return [
            EvidenceRecord(
                tenant_id=r["tenant_id"], event_type=r["event_type"], content=r["content"],
                occurred_at=r["occurred_at"], source_event_id=r["source_event_id"],
                dedupe_key=r["dedupe_key"], metadata=r["metadata"],
                channel_id=r["channel_id"], id=r["id"],
            )
            for r in rows
        ]

    # ── FacetStoreProtocol ────────────────────────────────────────────────────

    async def set(self, record: FacetRecord):
        key = (record.tenant_id, record.key)
        id_ = self.facets.get(key, {}).get("id") or self._new_id()
        row = {
            "id": id_, "tenant_id": record.tenant_id, "key": record.key,
            "value": record.value, "confidence": record.confidence, "layer": record.layer,
        }
        self.facets[key] = row
        return FacetRecord(
            tenant_id=row["tenant_id"], key=row["key"], value=row["value"],
            confidence=row["confidence"], layer=row["layer"], id=row["id"],
        )

    async def get(self, tenant_id: str, key: str):
        row = self.facets.get((tenant_id, key))
        if not row:
            return None
        return FacetRecord(
            tenant_id=row["tenant_id"], key=row["key"], value=row["value"],
            confidence=row["confidence"], layer=row["layer"], id=row["id"],
        )

    async def _list_facets(self, tenant_id: str, prefix, layer):
        rows = [r for (t, _), r in self.facets.items() if t == tenant_id]
        if prefix:
            rows = [r for r in rows if r["key"].startswith(prefix)]
        if layer:
            rows = [r for r in rows if r["layer"] == layer]
        return [
            FacetRecord(tenant_id=r["tenant_id"], key=r["key"], value=r["value"],
                        confidence=r["confidence"], layer=r["layer"], id=r["id"])
            for r in rows
        ]

    async def list_multi(self, tenant_ids: list[str], prefix, layer):
        rows = [r for (t, _), r in self.facets.items() if t in tenant_ids]
        if prefix:
            rows = [r for r in rows if r["key"].startswith(prefix)]
        if layer:
            rows = [r for r in rows if r["layer"] == layer]
        return [
            FacetRecord(tenant_id=r["tenant_id"], key=r["key"], value=r["value"],
                        confidence=r["confidence"], layer=r["layer"], id=r["id"])
            for r in rows
        ]

    async def _delete_facet(self, tenant_id: str, key: str):
        k = (tenant_id, key)
        if k in self.facets:
            del self.facets[k]
            return True
        return False

    # ── GraphStoreProtocol ────────────────────────────────────────────────────

    async def add(self, triplet: Triplet):
        key = (triplet.tenant_id, triplet.subject, triplet.predicate, triplet.object)
        existing = next(
            (r for r in self.graph
             if (r["tenant_id"], r["subject"], r["predicate"], r["object"]) == key),
            None,
        )
        if existing:
            existing.update({"confidence": triplet.confidence, "source": triplet.source})
            return Triplet(**existing)
        id_ = self._new_id()
        row = {
            "id": id_, "tenant_id": triplet.tenant_id, "subject": triplet.subject,
            "predicate": triplet.predicate, "object": triplet.object,
            "confidence": triplet.confidence, "source": triplet.source,
        }
        self.graph.append(row)
        return Triplet(**row)

    async def query_subject(self, tenant_id: str, subject: str):
        return [Triplet(**r) for r in self.graph
                if r["tenant_id"] == tenant_id and r["subject"] == subject]

    async def query_object(self, tenant_id: str, object_: str):
        return [Triplet(**r) for r in self.graph
                if r["tenant_id"] == tenant_id and r["object"] == object_]

    async def query_predicate(self, tenant_id: str, predicate: str):
        return [Triplet(**r) for r in self.graph
                if r["tenant_id"] == tenant_id and r["predicate"] == predicate]

    # ── DigestStoreProtocol ───────────────────────────────────────────────────

    async def _upsert_digest(self, digest):
        from agentmem.core.models import Digest
        existing = next(
            (r for r in self.digests
             if r["tenant_id"] == digest.tenant_id
             and r["digest_type"] == digest.digest_type
             and r["period_start"] == digest.period_start),
            None,
        )
        if existing:
            existing["content"] = digest.content
            return Digest(**existing)
        id_ = self._new_id()
        row = {
            "id": id_, "tenant_id": digest.tenant_id, "digest_type": digest.digest_type,
            "period_start": digest.period_start, "period_end": digest.period_end,
            "content": digest.content,
        }
        self.digests.append(row)
        return Digest(**row)

    async def _list_digests(self, filters):
        from agentmem.core.models import Digest
        rows = [r for r in self.digests if r["tenant_id"] == filters.tenant_id]
        if filters.digest_type:
            rows = [r for r in rows if r["digest_type"] == filters.digest_type]
        return [Digest(**r) for r in rows[: filters.limit]]

    # ── ActiveContextStoreProtocol ────────────────────────────────────────────

    async def _upsert_context(self, section: ContextSection):
        key = (section.tenant_id, section.section)
        id_ = self.context.get(key, {}).get("id") or self._new_id()
        row = {
            "id": id_, "tenant_id": section.tenant_id, "section": section.section,
            "content": section.content, "updated_at": datetime.now(timezone.utc),
        }
        self.context[key] = row
        return ContextSection(**row)

    async def get_all(self, tenant_id: str, max_age_seconds):
        rows = [r for (t, _), r in self.context.items() if t == tenant_id]
        if max_age_seconds is not None:
            now = datetime.now(timezone.utc)
            rows = [r for r in rows if (now - r["updated_at"]).total_seconds() <= max_age_seconds]
        return [ContextSection(**r) for r in rows]

    async def _delete_context(self, tenant_id: str, section: str):
        k = (tenant_id, section)
        if k in self.context:
            del self.context[k]
            return True
        return False

    # ── Dispatch methods (same pattern as PostgresStorageAdapter) ─────────

    async def upsert(self, obj):
        from agentmem.core.models import Digest
        if isinstance(obj, Digest):
            return await self._upsert_digest(obj)
        if isinstance(obj, ContextSection):
            return await self._upsert_context(obj)
        raise TypeError(f"upsert() expects Digest or ContextSection, got {type(obj).__name__}")

    async def list(self, *args, **kwargs):
        from agentmem.core.models import DigestFilters
        if args and isinstance(args[0], DigestFilters):
            return await self._list_digests(args[0])
        return await self._list_facets(*args, **kwargs)

    async def delete(self, tenant_id: str, key_or_section: str):
        k = (tenant_id, key_or_section)
        if k in self.facets:
            del self.facets[k]
            return True
        if k in self.context:
            del self.context[k]
            return True
        return False

    # ── VectorStore ───────────────────────────────────────────────────────────

    async def store(self, record):
        key = (record.source_table, record.source_id, record.model_id)
        self.vectors[key] = {
            "id": self.vectors.get(key, {}).get("id") or self._new_id(),
            "tenant_id": record.tenant_id, "source_table": record.source_table,
            "source_id": record.source_id, "model_id": record.model_id,
            "embedding": record.embedding, "collection": record.collection,
        }

    async def search(self, query, filters):
        import math
        from agentmem.core.models import VectorResult

        def cosine(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(x * x for x in b))
            return dot / (na * nb) if na and nb else 0.0

        results = []
        for (st, sid, mid), r in self.vectors.items():
            if (r["tenant_id"] != filters.tenant_id
                    and r["tenant_id"] not in filters.extra_tenant_ids):
                continue
            if filters.source_table and st != filters.source_table:
                continue
            score = cosine(query, r["embedding"])
            results.append(VectorResult(
                source_table=st, source_id=sid,
                tenant_id=r["tenant_id"], content="", score=score,
            ))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[: filters.limit]

    async def reindex(self, source_table, tenant_id, limit=100):
        return 0

    async def find_unembedded(self, source_table, tenant_id, model_id, limit=100):
        """Find records that don't have embeddings for the given model.

        Returns list of (source_id, content) pairs.
        """
        results = []

        if source_table == "evidence":
            records = self.evidence
            content_field = "content"
        elif source_table == "facets":
            records = list(self.facets.values())
            content_field = "value"
        else:
            raise ValueError(f"Invalid source_table: {source_table}")

        for record in records:
            # Filter by tenant_id if specified
            if tenant_id and record.get("tenant_id") != tenant_id:
                continue

            # Check if this record has an embedding for this model
            vector_key = (source_table, record["id"], model_id)
            if vector_key not in self.vectors:
                content = record.get(content_field, "") or ""
                tenant_id = record.get("tenant_id", "")
                results.append((record["id"], content, tenant_id))

                if len(results) >= limit:
                    break

        return results


# ── Pytest fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def mem_adapter() -> InMemoryStorageAdapter:
    """Fresh in-memory storage adapter for each test."""
    return InMemoryStorageAdapter()


@pytest.fixture
def hash_adapter() -> HashEmbeddingAdapter:
    """Hash embedding adapter (128-dim, deterministic, no external services)."""
    return HashEmbeddingAdapter(dimensions=128)
