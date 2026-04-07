# ABOUTME: Retrieval API routes — GET evidence, semantic search, facets, graph, digests, context.
# ABOUTME: JSON responses. All routes require tenant_id.
"""Retrieval API routes."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/retrieve", tags=["retrieval"])


# ── Evidence ──────────────────────────────────────────────────────────────────

class EvidenceItem(BaseModel):
    id: int | None
    tenant_id: str
    event_type: str
    content: str
    occurred_at: datetime
    dedupe_key: str
    channel_id: str | None
    metadata: dict[str, Any] | None


@router.get("/evidence", response_model=list[EvidenceItem])
async def retrieve_evidence(
    request: Request,
    tenant_id: str = Query(...),
    event_type: str | None = Query(None),
    since: datetime | None = Query(None),
    limit: int = Query(50, le=500),
) -> list[EvidenceItem]:
    from agentmem.core.models import EvidenceFilters

    # Get evidence_ledger from request.app.state
    evidence_ledger = request.app.state.evidence_ledger

    # Build EvidenceFilters from query params
    filters = EvidenceFilters(
        tenant_id=tenant_id,
        event_type=event_type,
        since=since,
        limit=limit,
    )

    # Call evidence_ledger.query()
    records = await evidence_ledger.query(filters)

    # Return as list of EvidenceItem
    return [
        EvidenceItem(
            id=record.id,
            tenant_id=record.tenant_id,
            event_type=record.event_type,
            content=record.content,
            occurred_at=record.occurred_at,
            dedupe_key=record.dedupe_key,
            channel_id=record.channel_id,
            metadata=record.metadata,
        )
        for record in records
    ]


# ── Semantic search ───────────────────────────────────────────────────────────

class SemanticResult(BaseModel):
    source_table: str
    source_id: int
    tenant_id: str
    content: str
    score: float


@router.get("/semantic", response_model=list[SemanticResult])
async def retrieve_semantic(
    request: Request,
    tenant_id: str = Query(...),
    query: str = Query(...),
    source_table: str | None = Query(None),
    limit: int = Query(10, le=100),
) -> list[SemanticResult]:
    from agentmem.core.models import VectorFilters

    # Get services from request.app.state
    embedding_adapter = request.app.state.embedding_adapter
    vector_store = request.app.state.vector_store

    # Embed the query string
    query_vector = await embedding_adapter.embed(query)

    # Build VectorFilters from query params
    filters = VectorFilters(
        tenant_id=tenant_id,
        source_table=source_table,
        limit=limit,
    )

    # Call vector_store.search()
    results = await vector_store.search(query_vector, filters)

    # Return as list of SemanticResult
    return [
        SemanticResult(
            source_table=result.source_table,
            source_id=result.source_id,
            tenant_id=result.tenant_id,
            content=result.content,
            score=result.score,
        )
        for result in results
    ]


# ── Facets ────────────────────────────────────────────────────────────────────

class FacetItem(BaseModel):
    id: int | None
    tenant_id: str
    key: str
    value: str
    confidence: float
    layer: str


@router.get("/facets", response_model=list[FacetItem])
async def retrieve_facets(
    request: Request,
    tenant_id: str = Query(...),
    prefix: str | None = Query(None),
    layer: str | None = Query(None),
) -> list[FacetItem]:
    # Get facet_store from request.app.state
    facet_store = request.app.state.facet_store

    # Call facet_store.list()
    records = await facet_store.list(tenant_id, prefix, layer)

    # Return as list of FacetItem
    return [
        FacetItem(
            id=record.id,
            tenant_id=record.tenant_id,
            key=record.key,
            value=record.value,
            confidence=record.confidence,
            layer=record.layer,
        )
        for record in records
    ]


@router.get("/facets/{key}", response_model=FacetItem | None)
async def retrieve_facet(
    request: Request,
    key: str,
    tenant_id: str = Query(...),
) -> FacetItem | None:
    # Get facet_store from request.app.state
    facet_store = request.app.state.facet_store

    # Call facet_store.get()
    record = await facet_store.get(tenant_id, key)

    if record is None:
        return None

    # Return as FacetItem
    return FacetItem(
        id=record.id,
        tenant_id=record.tenant_id,
        key=record.key,
        value=record.value,
        confidence=record.confidence,
        layer=record.layer,
    )


# ── Graph ─────────────────────────────────────────────────────────────────────

class GraphItem(BaseModel):
    id: int | None
    tenant_id: str
    subject: str
    predicate: str
    object: str
    confidence: float
    source: str | None


@router.get("/graph", response_model=list[GraphItem])
async def retrieve_graph(
    request: Request,
    tenant_id: str = Query(...),
    subject: str | None = Query(None),
    predicate: str | None = Query(None),
    object: str | None = Query(None),
) -> list[GraphItem]:
    # Get graph_store from request.app.state
    graph_store = request.app.state.graph_store

    # Route to appropriate query method based on which param is provided
    if subject is not None:
        records = await graph_store.query_subject(tenant_id, subject)
    elif predicate is not None:
        records = await graph_store.query_predicate(tenant_id, predicate)
    elif object is not None:
        records = await graph_store.query_object(tenant_id, object)
    else:
        # If no specific query param, return empty list or could return all
        records = []

    # Return as list of GraphItem
    return [
        GraphItem(
            id=record.id,
            tenant_id=record.tenant_id,
            subject=record.subject,
            predicate=record.predicate,
            object=record.object,
            confidence=record.confidence,
            source=record.source,
        )
        for record in records
    ]


# ── Digests ───────────────────────────────────────────────────────────────────

class DigestItem(BaseModel):
    id: int | None
    tenant_id: str
    digest_type: str
    period_start: datetime
    period_end: datetime
    content: str


@router.get("/digests", response_model=list[DigestItem])
async def retrieve_digests(
    request: Request,
    tenant_id: str = Query(...),
    type: str | None = Query(None),
    limit: int = Query(50, le=500),
) -> list[DigestItem]:
    from agentmem.core.models import DigestFilters

    # Get digest_service from request.app.state
    digest_service = request.app.state.digest_service

    # Build DigestFilters from query params
    filters = DigestFilters(
        tenant_id=tenant_id,
        digest_type=type,
        limit=limit,
    )

    # Call digest_service.list()
    records = await digest_service.list(filters)

    # Return as list of DigestItem
    return [
        DigestItem(
            id=record.id,
            tenant_id=record.tenant_id,
            digest_type=record.digest_type,
            period_start=record.period_start,
            period_end=record.period_end,
            content=record.content,
        )
        for record in records
    ]


# ── Active context ────────────────────────────────────────────────────────────

class ContextSectionItem(BaseModel):
    tenant_id: str
    section: str
    content: str
    updated_at: datetime | None


@router.get("/context", response_model=list[ContextSectionItem])
async def retrieve_context(
    request: Request,
    tenant_id: str = Query(...),
    max_age_seconds: float | None = Query(None),
) -> list[ContextSectionItem]:
    # Get context_service from request.app.state
    context_service = request.app.state.context_service

    # Call context_service.get_all()
    sections = await context_service.get_all(tenant_id, max_age_seconds)

    # Return as list of ContextSectionItem
    return [
        ContextSectionItem(
            tenant_id=section.tenant_id,
            section=section.section,
            content=section.content,
            updated_at=section.updated_at,
        )
        for section in sections
    ]
