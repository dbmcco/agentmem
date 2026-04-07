# ABOUTME: Embedding reindex background job.
# ABOUTME: Re-embeds evidence that may be missing vector entries after provider changes.
"""Embed reindex job — re-embeds evidence that may be missing vector entries."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

from agentmem.core.models import VectorEntry
from agentmem.core.protocols import EmbeddingProvider, EvidenceStore, VectorStore


def make_embed_reindex_job(
    evidence_store: EvidenceStore,
    vector_store: VectorStore,
    embedding_provider: EmbeddingProvider,
    tenant_id: str,
) -> Callable[[], Awaitable[None]]:
    async def run() -> None:
        evidences = await evidence_store.list(tenant_id, limit=1000)
        for ev in evidences:
            embedding = await embedding_provider.embed(ev.content)
            entry = VectorEntry(
                id=uuid4(),
                ref_id=ev.id,
                ref_type="evidence",
                embedding=embedding,
                tenant_id=tenant_id,
            )
            await vector_store.upsert(entry)

    return run
