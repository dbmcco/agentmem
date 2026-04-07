# ABOUTME: Core protocol interfaces for agentmem.
# ABOUTME: Abstract contracts that all adapter implementations must satisfy.
"""Core protocols for agentmem — zero concrete dependencies.

All adapters implement these protocols. Domain services accept
protocol-typed adapters at construction time.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from .models import Evidence, Facet, JobState, VectorEntry


@runtime_checkable
class EvidenceStore(Protocol):
    async def put(self, evidence: Evidence) -> None: ...
    async def get(self, tenant_id: str, evidence_id: UUID) -> Evidence | None: ...
    async def list(self, tenant_id: str, limit: int = 100) -> list[Evidence]: ...
    async def delete(self, tenant_id: str, evidence_id: UUID) -> bool: ...


@runtime_checkable
class FacetStore(Protocol):
    async def put(self, facet: Facet) -> None: ...
    async def get(self, tenant_id: str, key: str) -> Facet | None: ...
    async def list(self, tenant_id: str) -> list[Facet]: ...
    async def delete(self, tenant_id: str, key: str) -> bool: ...


@runtime_checkable
class VectorStore(Protocol):
    async def upsert(self, entry: VectorEntry) -> None: ...
    async def search(
        self, tenant_id: str, embedding: list[float], top_k: int = 10
    ) -> list[tuple[UUID, float]]: ...
    async def delete(self, ref_id: UUID) -> bool: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    @property
    def dimensions(self) -> int: ...


@runtime_checkable
class EventBus(Protocol):
    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...
    async def subscribe(
        self, topic: str, handler: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None: ...


@runtime_checkable
class JobStore(Protocol):
    async def get_state(self, name: str) -> JobState | None: ...
    async def put_state(self, state: JobState) -> None: ...
    async def list_states(self) -> list[JobState]: ...
