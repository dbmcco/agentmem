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
    extra_tenants: str | None = Query(None, description='Comma-separated additional tenant IDs'),
) -> list[SemanticResult]:
    from agentmem.core.models import VectorFilters

    # Get embedding service from request.app.state
    embedding_service = request.app.state.embedding_service

    # Parse extra_tenants into list
    extra_ids = [t.strip() for t in extra_tenants.split(',') if t.strip()] if extra_tenants else []

    # Build VectorFilters from query params
    filters = VectorFilters(
        tenant_id=tenant_id,
        source_table=source_table,
        limit=limit,
        extra_tenant_ids=extra_ids,
    )

    # Delegate to embedding_service.search() which embeds query and searches
    results = await embedding_service.search(query, filters)

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
    extra_tenants: str | None = Query(None, description='Comma-separated additional tenant IDs'),
) -> list[FacetItem]:
    # Get facet_store from request.app.state
    facet_store = request.app.state.facet_store

    # Handle extra_tenants parameter
    if extra_tenants:
        all_tenant_ids = [tenant_id] + [t.strip() for t in extra_tenants.split(',') if t.strip()]
        records = await facet_store.list_multi(all_tenant_ids, prefix=prefix, layer=layer)
    else:
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

    # Get digest_engine from request.app.state
    digest_engine = request.app.state.digest_engine

    # Build DigestFilters from query params
    filters = DigestFilters(
        tenant_id=tenant_id,
        digest_type=type,
        limit=limit,
    )

    # Call digest_engine.list()
    records = await digest_engine.list(filters)

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
    # Get active_context_store from request.app.state
    active_context_store = request.app.state.active_context_store

    # Call active_context_store.get_all()
    sections = await active_context_store.get_all(tenant_id, max_age_seconds)

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


# ── Conversation turns ────────────────────────────────────────────────────────

class TurnItem(BaseModel):
    turn_id: str | None
    content: str
    occurred_at: datetime
    source_event_id: str | None
    user_message: str | None
    agent_response: str | None
    conversation_id: str | None
    channel_id: str | None
    origin_platform: str | None


def _extract_turn_parts(record) -> tuple[str | None, str | None]:
    """Extract user message and agent response from EvidenceRecord."""
    meta = record.metadata or {}
    user_message = meta.get('user_message') or None
    agent_response = meta.get('agent_response') or None
    if user_message or agent_response:
        return user_message, agent_response

    # fallback: parse content string
    content = record.content
    # Fallback: parse legacy content string format "User said: ... \nAgent: ..."
    import re as _re
    m = _re.match(r'^User said: (.*?)(?:\n\S.*?: (.*))?$', content, _re.DOTALL)
    if m:
        return m.group(1).strip() or None, (m.group(2) or "").strip() or None
    return None, None


@router.get('/turns', response_model=list[TurnItem])
async def retrieve_turns(
    request: Request,
    tenant_id: str = Query(...),
    limit: int = Query(12, le=500),
    conversation_id: str | None = Query(None),
    channel_id: str | None = Query(None),
) -> list[TurnItem]:
    """Retrieve conversation turns with optional conversation/channel filtering."""
    from agentmem.core.models import EvidenceFilters

    # Get evidence_ledger from request.app.state
    evidence_ledger = request.app.state.evidence_ledger

    # Build metadata_contains filter for conversation_id if provided
    metadata_contains = None
    if conversation_id:
        metadata_contains = {'conversation_id': conversation_id}

    # Build EvidenceFilters
    filters = EvidenceFilters(
        tenant_id=tenant_id,
        event_type='conversation.turn',
        limit=limit,
        channel_id=channel_id,
        metadata_contains=metadata_contains,
    )

    # Call evidence_ledger.query()
    records = await evidence_ledger.query(filters)

    # Map each EvidenceRecord to TurnItem
    turn_items = []
    for record in records:
        user_message, agent_response = _extract_turn_parts(record)

        # Extract conversation_id and origin_platform from metadata
        meta = record.metadata or {}
        conv_id = meta.get('conversation_id')
        platform = meta.get('origin_platform')

        turn_item = TurnItem(
            turn_id=record.source_event_id,
            content=record.content,
            occurred_at=record.occurred_at,
            source_event_id=record.source_event_id,
            user_message=user_message,
            agent_response=agent_response,
            conversation_id=conv_id,
            channel_id=record.channel_id,
            origin_platform=platform,
        )
        turn_items.append(turn_item)

    return turn_items


# ── Rolling summary ───────────────────────────────────────────────────────────

class TimeRange(BaseModel):
    start: datetime | None
    end: datetime | None


class SummaryOut(BaseModel):
    summary: str
    turn_count: int
    time_range: TimeRange


@router.get("/summary", response_model=SummaryOut)
async def retrieve_summary(
    request: Request,
    tenant_id: str = Query(...),
    turn_count: int = Query(40, le=500),
    verbatim_count: int = Query(12, ge=0, le=500),
    conversation_id: str | None = Query(None),
    channel_id: str | None = Query(None),
) -> SummaryOut:
    """Rolling summary of older turns, compressing everything beyond verbatim_count.

    Fetches up to turn_count turns (newest-first), skips the most recent
    verbatim_count (those are injected verbatim via /turns), and compresses
    the remainder into a date-grouped text block for prompt injection.
    """
    from collections import defaultdict
    from agentmem.core.models import EvidenceFilters

    metadata_contains = {"conversation_id": conversation_id} if conversation_id else None
    filters = EvidenceFilters(
        tenant_id=tenant_id,
        event_type="conversation.turn",
        limit=turn_count,
        channel_id=channel_id,
        metadata_contains=metadata_contains,
    )
    records = await request.app.state.evidence_ledger.query(filters)

    to_summarize = records[verbatim_count:]
    if not to_summarize:
        return SummaryOut(summary="", turn_count=0, time_range=TimeRange(start=None, end=None))

    by_date: dict[str, list[str]] = defaultdict(list)
    for record in reversed(to_summarize):
        date_key = record.occurred_at.strftime("%-d %b") if record.occurred_at else "?"
        user_msg, agent_resp = _extract_turn_parts(record)
        if user_msg or agent_resp:
            pieces = []
            if user_msg:
                pieces.append(f"User: {user_msg}")
            if agent_resp:
                pieces.append(f"Agent: {agent_resp}")
            content = " | ".join(pieces)
        else:
            content = record.content.replace("\n", " ").strip()
        by_date[date_key].append(content[:80])

    lines = [f"[{date}] {'; '.join(entries)}" for date, entries in by_date.items()]
    summary_text = "\n".join(lines)

    times = [r.occurred_at for r in to_summarize if r.occurred_at]
    return SummaryOut(
        summary=summary_text,
        turn_count=len(to_summarize),
        time_range=TimeRange(start=min(times) if times else None, end=max(times) if times else None),
    )


# ── Poetic echoes ─────────────────────────────────────────────────────────────

class EchoesRequest(BaseModel):
    tenant_id: str
    query: str | None = None
    turn_count: int = 0  # 0 = always refresh; >=3 = refresh on every 3rd turn


class EchoesOut(BaseModel):
    echoes: str
    triplets: list[list[str]]
    refreshed: bool


@router.post("/echoes", response_model=EchoesOut)
async def retrieve_echoes(request: Request, payload: EchoesRequest) -> EchoesOut:
    """Generate poetic echo triplets from recent evidence and knowledge graph.

    Extracts proper nouns from recent memory and knowledge graph edges,
    groups them into word/word/word triplets for non-literal context seeding.
    Refreshes when turn_count == 0 or turn_count >= 3.
    """
    import re
    from agentmem.core.models import EvidenceFilters

    should_refresh = payload.turn_count == 0 or payload.turn_count >= 3
    if not should_refresh:
        return EchoesOut(echoes="", triplets=[], refreshed=False)

    # Fetch recent evidence
    filters = EvidenceFilters(tenant_id=payload.tenant_id, limit=5)
    evidence_rows = await request.app.state.evidence_ledger.query(filters)

    # Fetch graph triplets
    graph_store = request.app.state.graph_store
    query_words = set((payload.query or "").lower().split()) if payload.query else set()
    raw_triplets: list[Any] = []
    if payload.query:
        # Score by word overlap with query
        for word in list(query_words)[:3]:
            try:
                raw_triplets.extend(await graph_store.query_subject(payload.tenant_id, word))
            except Exception:
                pass
    if not raw_triplets:
        # Fall back to predicate scan — get a broad sample
        for pred in ["knows", "likes", "works_on", "prefers", "has"]:
            try:
                raw_triplets.extend(await graph_store.query_predicate(payload.tenant_id, pred))
            except Exception:
                pass

    # Filter triplets by query word overlap if query provided
    scored_triplets = raw_triplets
    if query_words and raw_triplets:
        scored_triplets = [
            t for t in raw_triplets
            if query_words & set(f"{t.subject} {t.predicate} {t.object}".lower().split())
        ]
    scored_triplets = scored_triplets[:20]

    # Extract proper noun candidates from evidence
    candidates: list[str] = []
    for ev in evidence_rows:
        candidates.extend(re.findall(r"\b[A-Z][a-z]+\b", ev.content))

    # Add triplet terms
    for t in scored_triplets[:5]:
        candidates.extend([
            t.subject,
            t.predicate.replace("_", " "),
            t.object.replace("_", " "),
        ])

    # Deduplicate preserving order, drop short words
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if c.lower() not in seen and len(c) > 2:
            seen.add(c.lower())
            unique.append(c)

    if not unique:
        return EchoesOut(echoes="", triplets=[], refreshed=True)

    # Pad to multiple of 3
    while len(unique) % 3 != 0:
        unique.append("memory")

    # Build triplet groups (max 4 = 12 words)
    groups: list[list[str]] = []
    for i in range(0, min(len(unique), 12), 3):
        groups.append(unique[i:i + 3])

    # Format echoes block
    lines = ["[Echoes]", ""]
    for i, group in enumerate(groups):
        lines.append("/".join(group))
        if i < len(groups) - 1:
            lines.append("***")
    lines.extend(["", "[Depth beneath]"])

    return EchoesOut(echoes="\n".join(lines), triplets=groups, refreshed=True)
