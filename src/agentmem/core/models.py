# ABOUTME: Core domain models for agentmem.
# ABOUTME: All dataclasses exactly as specified in the design doc. Zero external dependencies.
"""Core domain models — zero external dependencies.

Class names, field names, and types are authoritative. Do not rename or add fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class EvidenceRecord:
    tenant_id: str
    event_type: str
    content: str
    occurred_at: datetime
    source_event_id: str
    dedupe_key: str
    # Optional pre-computed embedding; written to VectorStore, NOT stored on the evidence row
    embedding: list[float] | None = None
    metadata: dict[str, Any] | None = None
    channel_id: str | None = None
    id: int | None = None  # set after DB insert


@dataclass
class InsertResult:
    id: int | None        # None if deduplicated
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
class FacetRecord:
    tenant_id: str
    key: str
    value: str
    confidence: float = 1.0   # 0.0–1.0
    layer: str = "searchable"
    id: int | None = None     # set after DB insert


@dataclass
class Triplet:
    tenant_id: str
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source: str | None = None
    id: int | None = None     # set after DB insert


@dataclass
class Digest:
    tenant_id: str
    digest_type: str        # "daily" | "weekly" | "monthly" | custom
    period_start: datetime
    period_end: datetime
    content: str
    id: int | None = None   # set after DB insert


@dataclass
class DigestFilters:
    tenant_id: str
    digest_type: str | None = None       # None = all types
    period_start: datetime | None = None  # inclusive lower bound
    period_end: datetime | None = None    # inclusive upper bound
    limit: int = 50


@dataclass
class ContextSection:
    tenant_id: str
    section: str
    content: str
    updated_at: datetime | None = None
    id: int | None = None  # set after DB insert


@dataclass
class VectorRecord:
    tenant_id: str
    source_table: str     # "evidence" | "facets"
    source_id: int
    model_id: str
    embedding: list[float]
    collection: str = "default"  # groups vectors for scoped search
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
    score: float          # 0.0–1.0, higher = more similar


@dataclass
class EventRecord:
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    dedupe_key: str
    tenant_id: str | None = None
    source_event_id: str | None = None


@dataclass
class JobResult:
    success: bool
    items_processed: int = 0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobStatus:
    name: str
    trigger_type: str       # "cron" | "continuous" | "event" | "on_demand"
    last_run: datetime | None
    last_result: JobResult | None
    error_count: int
    heartbeat_age_seconds: float | None  # None for non-continuous jobs
    state: str              # "running" | "idle" | "stale" | "dead"
