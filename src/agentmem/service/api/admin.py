# ABOUTME: Admin API routes — reindex, retention, stats, worker status/run.
# ABOUTME: Token-protected if admin.token is set in config.
"""Admin API routes."""
from __future__ import annotations

import dataclasses
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["admin"])

workers_router = APIRouter(prefix="/workers", tags=["workers"])


def _check_token(request: Request, x_agentmem_admin_token: str | None = Header(None)) -> None:
    """Validate admin token if configured. No-op if token is empty (dev mode)."""
    config = request.app.state.config

    # If no token configured, allow access (dev mode)
    if not config.admin.token:
        return

    # If token is configured, validate it
    if x_agentmem_admin_token != config.admin.token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


# ── Admin ─────────────────────────────────────────────────────────────────────

class ReindexResponse(BaseModel):
    items_indexed: int
    dry_run: bool


class RetentionResponse(BaseModel):
    items_deleted: int
    dry_run: bool


class StatsResponse(BaseModel):
    evidence_count: int
    facet_count: int
    triplet_count: int
    digest_count: int
    vector_count: int
    tenant_id: str


class DigestRequest(BaseModel):
    tenant_id: str
    digest_type: str
    date: datetime


@router.post("/reindex", response_model=ReindexResponse)
async def trigger_reindex(
    request: Request,
    tenant_id: str | None = None,
    dry_run: bool = False,
    _: None = Depends(_check_token),
) -> ReindexResponse:
    """Trigger on-demand embedding reindex job."""
    # Get coordinator from request.app.state
    coordinator = request.app.state.coordinator

    # Trigger reindex job
    result = await coordinator.run_now("embed_reindex", tenant_id=tenant_id, dry_run=dry_run)

    return ReindexResponse(
        items_indexed=result.items_processed,
        dry_run=dry_run,
    )


@router.post("/retention", response_model=RetentionResponse)
async def trigger_retention(
    request: Request,
    tenant_id: str | None = None,
    evidence_days: int = 180,
    dry_run: bool = False,
    _: None = Depends(_check_token),
) -> RetentionResponse:
    """Trigger on-demand retention job."""
    # Get coordinator from request.app.state
    coordinator = request.app.state.coordinator

    # Trigger retention job
    result = await coordinator.run_now("retention", tenant_id=tenant_id, evidence_days=evidence_days, dry_run=dry_run)

    return RetentionResponse(
        items_deleted=result.items_processed,
        dry_run=dry_run,
    )


class StatusResponse(BaseModel):
    status: str
    auth: str


@router.get("/status", response_model=StatusResponse)
async def admin_status(request: Request) -> StatusResponse:
    """Return service readiness and auth mode."""
    config = request.app.state.config
    return StatusResponse(
        status="ready",
        auth="token" if config.admin.token else "open",
    )


@router.get("/stats/{tenant_id}", response_model=StatsResponse)
async def get_stats(
    request: Request,
    tenant_id: str,
    _: None = Depends(_check_token),
) -> StatsResponse:
    """Return row counts per table for tenant."""
    storage_adapter = request.app.state.storage_adapter

    # Query counts for each table
    evidence_count = await storage_adapter.count_evidence(tenant_id)
    facet_count = await storage_adapter.count_facets(tenant_id)
    triplet_count = await storage_adapter.count_triplets(tenant_id)
    digest_count = await storage_adapter.count_digests(tenant_id)
    vector_count = await storage_adapter.count_vectors(tenant_id)

    return StatsResponse(
        evidence_count=evidence_count,
        facet_count=facet_count,
        triplet_count=triplet_count,
        digest_count=digest_count,
        vector_count=vector_count,
        tenant_id=tenant_id,
    )


@router.post("/digest/generate", response_model=dict)
async def generate_digest(
    body: DigestRequest,
    request: Request,
    _: None = Depends(_check_token),
) -> dict:
    """Trigger on-demand digest generation."""
    # Get coordinator from request.app.state
    coordinator = request.app.state.coordinator

    # Trigger digest job
    result = await coordinator.run_now(
        "digest_generation",
        tenant_id=body.tenant_id,
        digest_type=body.digest_type,
        date=body.date,
    )

    return {"status": "ok", "result": result}


# ── Workers ───────────────────────────────────────────────────────────────────

class JobStatusResponse(BaseModel):
    name: str
    trigger_type: str
    last_run: str | None
    error_count: int
    heartbeat_age_seconds: float | None
    state: str


@workers_router.get("/status", response_model=list[JobStatusResponse])
async def workers_status(request: Request) -> list[JobStatusResponse]:
    """Return status for all registered worker jobs."""
    # Get coordinator from request.app.state
    coordinator = request.app.state.coordinator

    # Call coordinator.status()
    job_statuses = await coordinator.status()

    # Convert to response list
    return [
        JobStatusResponse(
            name=status.name,
            trigger_type=status.trigger_type,
            last_run=status.last_run.isoformat() if status.last_run else None,
            error_count=status.error_count,
            heartbeat_age_seconds=status.heartbeat_age_seconds,
            state=status.state,
        )
        for status in job_statuses
    ]


@workers_router.post("/run/{job_name}", response_model=dict)
async def workers_run(
    request: Request,
    job_name: str,
    tenant_id: str | None = None,
    _: None = Depends(_check_token),
) -> dict:
    """Trigger an on-demand job run by name."""
    # Get coordinator from request.app.state
    coordinator = request.app.state.coordinator

    # Call coordinator.run_now()
    result = await coordinator.run_now(job_name, tenant_id=tenant_id)

    return dataclasses.asdict(result)
