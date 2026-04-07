# ABOUTME: Core domain models for agentmem.
# ABOUTME: Defines Evidence, Facet, VectorEntry, RetrievalQuery, RetrievalResult, and JobState.
"""Core domain models for agentmem — zero external dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class EvidenceKind(str, Enum):
    OBSERVATION = "observation"
    FACT = "fact"
    PREFERENCE = "preference"
    INTERACTION = "interaction"


@dataclass
class Evidence:
    tenant_id: str
    content: str
    kind: EvidenceKind
    id: UUID = field(default_factory=uuid4)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Facet:
    tenant_id: str
    key: str
    value: str
    source_ids: list[UUID] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class VectorEntry:
    id: UUID
    ref_id: UUID
    ref_type: str  # "evidence" or "facet"
    embedding: list[float]
    tenant_id: str


@dataclass
class RetrievalQuery:
    tenant_id: str
    text: str
    top_k: int = 10
    kind_filter: EvidenceKind | None = None


@dataclass
class RetrievalResult:
    evidence: Evidence
    score: float


@dataclass
class JobState:
    name: str
    last_run: datetime | None = None
    next_run: datetime | None = None
    status: str = "idle"  # idle, running, failed
    error: str | None = None


@dataclass
class ContextSection:
    tenant_id: str
    section: str
    content: str
    updated_at: datetime | None = None
    id: int | None = None


@dataclass
class EvidenceRecord:
    tenant_id: str
    event_type: str
    content: str
    occurred_at: datetime
    source_event_id: str
    dedupe_key: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] | None = None
    channel_id: str | None = None
    id: int | None = None


@dataclass
class InsertResult:
    id: int | None
    dedupe_key: str
    deduplicated: bool


@dataclass
class EvidenceFilters:
    tenant_id: str
    event_type: str | None = None
    since: datetime | None = None
    channel_id: str | None = None
    metadata_contains: dict[str, Any] | None = None
    limit: int = 50


@dataclass
class Digest:
    tenant_id: str
    digest_type: str
    period_start: datetime
    period_end: datetime
    content: str
    id: int | None = None


@dataclass
class DigestFilters:
    tenant_id: str
    digest_type: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    limit: int = 50


@dataclass
class FacetRecord:
    tenant_id: str
    key: str
    value: str
    confidence: float = 1.0
    layer: str = "searchable"
    id: int | None = None


@dataclass
class Triplet:
    tenant_id: str
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source: str | None = None
    id: int | None = None


@dataclass
class VectorRecord:
    tenant_id: str
    source_table: str
    source_id: int
    model_id: str
    embedding: list[float]
    collection: str = "default"
    id: int | None = None


@dataclass
class VectorFilters:
    tenant_id: str
    source_table: str | None = None
    collection: str | None = None
    channel_id: str | None = None
    extra_tenant_ids: list[str] = field(default_factory=list)
    limit: int = 10


@dataclass
class VectorResult:
    source_table: str
    source_id: int
    tenant_id: str
    content: str
    score: float


@dataclass
class EventRecord:
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    dedupe_key: str
    tenant_id: str | None = None
    source_event_id: str | None = None
