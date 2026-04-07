# ABOUTME: Core domain models for agentmem.
# ABOUTME: Defines Evidence, Facet, VectorEntry, RetrievalQuery, and related data structures.
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
