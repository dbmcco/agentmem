# ABOUTME: In-memory storage adapters for testing and zero-dependency mode.
# ABOUTME: Implements EvidenceStore, FacetStore, VectorStore, and JobStore in memory.
"""In-memory storage adapters — zero external dependencies.

Suitable for testing and the zero-external-services deployment mode.
"""

from __future__ import annotations

import math
from uuid import UUID

from agentmem.core.models import Evidence, Facet, JobState, VectorEntry


class MemoryEvidenceStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[UUID, Evidence]] = {}

    async def put(self, evidence: Evidence) -> None:
        self._data.setdefault(evidence.tenant_id, {})[evidence.id] = evidence

    async def get(self, tenant_id: str, evidence_id: UUID) -> Evidence | None:
        return self._data.get(tenant_id, {}).get(evidence_id)

    async def list(self, tenant_id: str, limit: int = 100) -> list[Evidence]:
        items = list(self._data.get(tenant_id, {}).values())
        items.sort(key=lambda e: e.created_at, reverse=True)
        return items[:limit]

    async def delete(self, tenant_id: str, evidence_id: UUID) -> bool:
        tenant = self._data.get(tenant_id, {})
        if evidence_id in tenant:
            del tenant[evidence_id]
            return True
        return False


class MemoryFacetStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Facet]] = {}

    async def put(self, facet: Facet) -> None:
        self._data.setdefault(facet.tenant_id, {})[facet.key] = facet

    async def get(self, tenant_id: str, key: str) -> Facet | None:
        return self._data.get(tenant_id, {}).get(key)

    async def list(self, tenant_id: str) -> list[Facet]:
        return list(self._data.get(tenant_id, {}).values())

    async def delete(self, tenant_id: str, key: str) -> bool:
        tenant = self._data.get(tenant_id, {})
        if key in tenant:
            del tenant[key]
            return True
        return False


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class MemoryVectorStore:
    def __init__(self) -> None:
        self._entries: dict[UUID, VectorEntry] = {}

    async def upsert(self, entry: VectorEntry) -> None:
        self._entries[entry.id] = entry

    async def search(
        self, tenant_id: str, embedding: list[float], top_k: int = 10
    ) -> list[tuple[UUID, float]]:
        scored: list[tuple[UUID, float]] = []
        for entry in self._entries.values():
            if entry.tenant_id != tenant_id:
                continue
            score = _cosine_similarity(embedding, entry.embedding)
            scored.append((entry.ref_id, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def delete(self, ref_id: UUID) -> bool:
        to_remove = [k for k, v in self._entries.items() if v.ref_id == ref_id]
        for k in to_remove:
            del self._entries[k]
        return len(to_remove) > 0


class MemoryJobStore:
    def __init__(self) -> None:
        self._states: dict[str, JobState] = {}

    async def get_state(self, name: str) -> JobState | None:
        return self._states.get(name)

    async def put_state(self, state: JobState) -> None:
        self._states[state.name] = state

    async def list_states(self) -> list[JobState]:
        return list(self._states.values())
