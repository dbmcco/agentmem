# ABOUTME: FastAPI route handlers for agentmem REST API.
# ABOUTME: Defines ingest, retrieval, and admin endpoints.
"""FastAPI routes for agentmem service — Ingest, Retrieval, Admin."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agentmem.core.models import EvidenceKind, RetrievalQuery
from agentmem.core.services import MemoryService

router = APIRouter(prefix="/api/v1")


class IngestRequest(BaseModel):
    tenant_id: str
    content: str
    kind: str = "observation"
    metadata: dict[str, Any] = {}


class IngestResponse(BaseModel):
    id: str
    tenant_id: str
    kind: str
    created_at: str


class RetrieveRequest(BaseModel):
    tenant_id: str
    text: str
    top_k: int = 10
    kind_filter: str | None = None


class RetrieveResultItem(BaseModel):
    id: str
    content: str
    kind: str
    score: float


# Dependency — injected by the app factory
_service: MemoryService | None = None


def set_service(service: MemoryService) -> None:
    global _service
    _service = service


def get_service() -> MemoryService:
    if _service is None:
        raise RuntimeError("MemoryService not initialized")
    return _service


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    req: IngestRequest, svc: MemoryService = Depends(get_service)
) -> IngestResponse:
    evidence = await svc.ingest(
        tenant_id=req.tenant_id,
        content=req.content,
        kind=EvidenceKind(req.kind),
        metadata=req.metadata,
    )
    return IngestResponse(
        id=str(evidence.id),
        tenant_id=evidence.tenant_id,
        kind=evidence.kind.value,
        created_at=evidence.created_at.isoformat(),
    )


@router.post("/retrieve", response_model=list[RetrieveResultItem])
async def retrieve(
    req: RetrieveRequest, svc: MemoryService = Depends(get_service)
) -> list[RetrieveResultItem]:
    kind_filter = EvidenceKind(req.kind_filter) if req.kind_filter else None
    query = RetrievalQuery(
        tenant_id=req.tenant_id,
        text=req.text,
        top_k=req.top_k,
        kind_filter=kind_filter,
    )
    results = await svc.retrieve(query)
    return [
        RetrieveResultItem(
            id=str(r.evidence.id),
            content=r.evidence.content,
            kind=r.evidence.kind.value,
            score=r.score,
        )
        for r in results
    ]


@router.get("/evidence/{tenant_id}")
async def list_evidence(
    tenant_id: str,
    limit: int = 100,
    svc: MemoryService = Depends(get_service),
) -> list[dict[str, Any]]:
    evidences = await svc.list_evidence(tenant_id, limit=limit)
    return [
        {
            "id": str(e.id),
            "content": e.content,
            "kind": e.kind.value,
            "created_at": e.created_at.isoformat(),
        }
        for e in evidences
    ]


@router.delete("/evidence/{tenant_id}/{evidence_id}")
async def delete_evidence(
    tenant_id: str,
    evidence_id: str,
    svc: MemoryService = Depends(get_service),
) -> dict[str, bool]:
    deleted = await svc.delete(tenant_id, evidence_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return {"deleted": True}
