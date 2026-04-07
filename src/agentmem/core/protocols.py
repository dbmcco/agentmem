# ABOUTME: Abstract protocol interfaces for agentmem.
# ABOUTME: All concrete adapters implement these. Domain services depend only on these — never on concrete types.
"""Core protocol interfaces — zero concrete dependencies.

All adapters must implement the relevant protocol(s).
Domain services accept protocol-typed adapters at construction — no concrete imports.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Awaitable, Protocol, runtime_checkable

if TYPE_CHECKING:
    from agentmem.core.models import (
        ContextSection,
        DigestFilters,
        Digest,
        EvidenceFilters,
        EvidenceRecord,
        FacetRecord,
        InsertResult,
        Triplet,
        VectorFilters,
        VectorRecord,
        VectorResult,
        EventRecord,
    )


@runtime_checkable
class StorageAdapter(Protocol):
    """Lifecycle management for a storage backend."""

    async def initialize(self) -> None: ...
    async def close(self) -> None: ...
    async def migrate(self) -> None: ...  # idempotent schema creation


@runtime_checkable
class EvidenceStore(Protocol):
    async def insert(self, record: EvidenceRecord) -> InsertResult: ...
    async def query(self, filters: EvidenceFilters) -> list[EvidenceRecord]: ...


@runtime_checkable
class FacetStoreProtocol(Protocol):
    async def set(self, record: FacetRecord) -> FacetRecord: ...
    async def get(self, tenant_id: str, key: str) -> FacetRecord | None: ...
    async def list(
        self,
        tenant_id: str,
        prefix: str | None,
        layer: str | None,
    ) -> list[FacetRecord]: ...
    async def list_multi(
        self,
        tenant_ids: list[str],
        prefix: str | None,
        layer: str | None,
    ) -> list[FacetRecord]: ...
    async def delete(self, tenant_id: str, key: str) -> bool: ...


@runtime_checkable
class GraphStoreProtocol(Protocol):
    async def add(self, triplet: Triplet) -> Triplet: ...
    async def query_subject(self, tenant_id: str, subject: str) -> list[Triplet]: ...
    async def query_object(self, tenant_id: str, object_: str) -> list[Triplet]: ...
    async def query_predicate(
        self, tenant_id: str, predicate: str
    ) -> list[Triplet]: ...


@runtime_checkable
class DigestStoreProtocol(Protocol):
    async def upsert(self, digest: Digest) -> Digest: ...
    async def list(self, filters: DigestFilters) -> list[Digest]: ...


@runtime_checkable
class ActiveContextStoreProtocol(Protocol):
    async def upsert(self, section: ContextSection) -> ContextSection: ...
    async def get_all(
        self,
        tenant_id: str,
        max_age_seconds: float | None,
    ) -> list[ContextSection]: ...
    async def delete(self, tenant_id: str, section: str) -> bool: ...


@runtime_checkable
class VectorStore(Protocol):
    async def store(self, record: VectorRecord) -> None: ...
    async def search(
        self, query: list[float], filters: VectorFilters
    ) -> list[VectorResult]: ...
    async def reindex(
        self,
        source_table: str,      # "evidence" | "facets"
        tenant_id: str | None,  # if None, reindex all tenants
        limit: int = 100,       # maximum number of items to reindex
    ) -> int: ...

    async def find_unembedded(
        self,
        source_table: str,      # "evidence" | "facets"
        tenant_id: str | None,  # if None, find all tenants
        model_id: str,          # embedding model ID to check against
        limit: int = 100,       # maximum number of items to return
    ) -> list[tuple[int, str, str]]: ...  # list of (source_id, content, tenant_id) tuples


@runtime_checkable
class EmbeddingAdapter(Protocol):
    dimensions: int
    model_id: str

    async def embed(self, text: str) -> list[float] | None:
        """Return None if service unavailable. Callers must handle None."""
        ...

    async def close(self) -> None: ...


@runtime_checkable
class EventSourceAdapter(Protocol):
    async def connect(self) -> None: ...
    async def subscribe(
        self, handler: Callable[[EventRecord], Awaitable[None]]
    ) -> None: ...
    async def disconnect(self) -> None: ...
