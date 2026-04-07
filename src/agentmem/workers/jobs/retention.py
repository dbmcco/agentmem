# ABOUTME: Retention background job for evidence lifecycle management.
# ABOUTME: Removes evidence older than a configurable threshold.
"""Retention job — removes evidence older than a configurable threshold."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from agentmem.core.protocols import EvidenceStore, VectorStore


def make_retention_job(
    evidence_store: EvidenceStore,
    vector_store: VectorStore,
    tenant_id: str,
    max_age: timedelta = timedelta(days=90),
) -> Callable[[], Awaitable[None]]:
    async def run() -> None:
        cutoff = datetime.now(UTC) - max_age
        evidences = await evidence_store.list(tenant_id, limit=10000)
        for ev in evidences:
            if ev.created_at < cutoff:
                await vector_store.delete(ev.id)
                await evidence_store.delete(tenant_id, ev.id)

    return run
