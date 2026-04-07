# ABOUTME: Ingest API routes — POST /ingest/evidence, /ingest/facet, /ingest/triplet.
# ABOUTME: All routes require tenant_id (or use config default in single-tenant mode).
"""Ingest API routes."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/ingest", tags=["ingest"])


class IngestEvidenceRequest(BaseModel):
    tenant_id: str
    event_type: str
    content: str
    occurred_at: datetime
    source_event_id: str
    dedupe_key: str
    metadata: dict[str, Any] | None = None
    channel_id: str | None = None


class IngestEvidenceResponse(BaseModel):
    id: int | None
    dedupe_key: str
    deduplicated: bool


class IngestFacetRequest(BaseModel):
    tenant_id: str
    key: str
    value: str
    confidence: float = 1.0
    layer: str = "searchable"


class IngestFacetResponse(BaseModel):
    id: int | None
    tenant_id: str
    key: str
    value: str
    confidence: float
    layer: str


class IngestTripletRequest(BaseModel):
    tenant_id: str
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source: str | None = None


class IngestTripletResponse(BaseModel):
    id: int | None
    tenant_id: str
    subject: str
    predicate: str
    object: str
    confidence: float
    source: str | None


class ContextSetRequest(BaseModel):
    tenant_id: str
    section: str
    content: str


class ContextSetResponse(BaseModel):
    id: int | None
    tenant_id: str
    section: str
    content: str
    updated_at: datetime | None


class ContextDeleteResponse(BaseModel):
    deleted: bool


@router.post("/evidence", response_model=IngestEvidenceResponse)
async def ingest_evidence(body: IngestEvidenceRequest, request: Request) -> IngestEvidenceResponse:
    """Ingest an evidence record. Returns InsertResult (deduplicated=True if already exists)."""
    from agentmem.core.models import EvidenceRecord

    # Get evidence_ledger from request.app.state
    evidence_ledger = request.app.state.evidence_ledger

    # Build EvidenceRecord from body
    record = EvidenceRecord(
        tenant_id=body.tenant_id,
        event_type=body.event_type,
        content=body.content,
        occurred_at=body.occurred_at,
        source_event_id=body.source_event_id,
        dedupe_key=body.dedupe_key,
        metadata=body.metadata,
        channel_id=body.channel_id,
    )

    # Call ledger.ingest()
    result = await evidence_ledger.ingest(record)

    # Return response
    return IngestEvidenceResponse(
        id=result.id,
        dedupe_key=result.dedupe_key,
        deduplicated=result.deduplicated,
    )


@router.post("/facet", response_model=IngestFacetResponse)
async def ingest_facet(body: IngestFacetRequest, request: Request) -> IngestFacetResponse:
    """Upsert a facet record."""
    from agentmem.core.models import FacetRecord

    # Get facet_store from request.app.state
    facet_store = request.app.state.facet_store

    # Build FacetRecord from body
    record = FacetRecord(
        tenant_id=body.tenant_id,
        key=body.key,
        value=body.value,
        confidence=body.confidence,
        layer=body.layer,
    )

    # Call facet_store.set()
    result = await facet_store.set(record)

    # Return response
    return IngestFacetResponse(
        id=result.id,
        tenant_id=result.tenant_id,
        key=result.key,
        value=result.value,
        confidence=result.confidence,
        layer=result.layer,
    )


@router.post("/triplet", response_model=IngestTripletResponse)
async def ingest_triplet(body: IngestTripletRequest, request: Request) -> IngestTripletResponse:
    """Add a knowledge graph triplet."""
    from agentmem.core.models import Triplet

    # Get graph_store from request.app.state
    graph_store = request.app.state.graph_store

    # Build Triplet from body
    triplet = Triplet(
        tenant_id=body.tenant_id,
        subject=body.subject,
        predicate=body.predicate,
        object=body.object,
        confidence=body.confidence,
        source=body.source,
    )

    # Call graph_store.add()
    result = await graph_store.add(triplet)

    # Return response
    return IngestTripletResponse(
        id=result.id,
        tenant_id=result.tenant_id,
        subject=result.subject,
        predicate=result.predicate,
        object=result.object,
        confidence=result.confidence,
        source=result.source,
    )


@router.post("/context/set", response_model=ContextSetResponse, tags=["context"])
async def context_set(body: ContextSetRequest, request: Request) -> ContextSetResponse:
    """Set or update a context section."""
    from agentmem.core.models import ContextSection

    # Get active_context_store from request.app.state
    active_context_store = request.app.state.active_context_store

    # Build ContextSection from body
    section = ContextSection(
        tenant_id=body.tenant_id,
        section=body.section,
        content=body.content,
    )

    # Call active_context_store.upsert()
    result = await active_context_store.upsert(section)

    # Return response
    return ContextSetResponse(
        id=result.id,
        tenant_id=result.tenant_id,
        section=result.section,
        content=result.content,
        updated_at=result.updated_at,
    )


@router.delete("/context/{tenant_id}/{section}", response_model=ContextDeleteResponse, tags=["context"])
async def context_delete(tenant_id: str, section: str, request: Request) -> ContextDeleteResponse:
    """Delete a context section."""
    # Get active_context_store from request.app.state
    active_context_store = request.app.state.active_context_store

    # Call active_context_store.delete()
    deleted = await active_context_store.delete(tenant_id, section)

    # Return response
    return ContextDeleteResponse(deleted=deleted)


@router.get("/status")
async def ingest_status() -> dict[str, str]:
    """Health check for the ingest surface."""
    return {"status": "ready", "surface": "ingest"}
