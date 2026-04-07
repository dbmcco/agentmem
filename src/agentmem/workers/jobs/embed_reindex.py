# ABOUTME: EmbedReindexJob — batch embedding backfill. Replaces scripts/nightly_embed.py.
# ABOUTME: Finds evidence/facet/digest rows with no VectorStore entry; embeds in batches.
"""EmbedReindexJob: scheduled batch embedding reindex."""
from __future__ import annotations

from agentmem.core.models import JobResult
from agentmem.workers.coordinator import JobContext, ScheduledJob
from agentmem.workers.triggers import CronTrigger


class EmbedReindexJob(ScheduledJob):
    """Batch-embed evidence, facet, and digest rows that have no VectorStore entry.

    Runs on a schedule to keep vector search current.

    Config keys (from context.config["workers"]["embed_reindex"]):
      trigger:    cron string, default "cron:0 2 * * *"
      batch_size: int, default 100
      tenants:    list[str], default [] (empty = all tenants)

    Flow:
      1. For each source_table in ["evidence", "facets", "digests"]:
         a. Call storage_adapter.reindex(source_table, tenant_id) to get orphaned row IDs
         b. For each ID (in batches of batch_size):
            - Fetch content from source table
            - Call embedding_service.embed_and_store(source_table, id, content, tenant_id)
            - Skip rows where embed returns None (log warning, continue)
      2. Return JobResult with items_processed count
    """

    name = "embed_reindex"
    trigger = CronTrigger(schedule="0 2 * * *")
    depends_on: list[str] = []

    def __init__(self, batch_size: int = 100, tenants: list[str] | None = None) -> None:
        self._batch_size = batch_size
        self._tenants = tenants or []

    async def run(self, context: JobContext) -> JobResult:
        """Execute the embedding reindex job.

        Delegates to EmbeddingService.reindex() which calls VectorStore.reindex()
        to find orphaned rows and embed them in batches.
        """
        count = 0
        errors: list[str] = []
        # None means "all tenants" — VectorStore.reindex accepts None for tenant_id
        tenants: list[str | None] = self._tenants if self._tenants else [None]

        for source_table in ['evidence', 'facets', 'digests']:
            for tenant_id in tenants:
                try:
                    processed = await context.embedding_service.reindex(
                        source_table, tenant_id, self._batch_size
                    )
                    count += processed
                except Exception as e:
                    errors.append(f"{source_table}/{tenant_id}: {e}")

        return JobResult(success=True, items_processed=count, errors=errors)
