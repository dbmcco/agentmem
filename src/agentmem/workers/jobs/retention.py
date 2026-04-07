# ABOUTME: RetentionJob — configurable data pruning. Replaces /admin/retention on-demand.
# ABOUTME: Deletes old evidence/digests/graph. Facets are NOT deleted (long-lived signals).
"""RetentionJob: scheduled data pruning."""
from __future__ import annotations

from agentmem.core.models import JobResult
from agentmem.workers.coordinator import JobContext, ScheduledJob
from agentmem.workers.triggers import CronTrigger


class RetentionJob(ScheduledJob):
    """Delete stale evidence, digests, and graph triplets on schedule.

    Config keys (from context.config["workers"]["retention"]):
      trigger:                  cron string, default "cron:0 3 * * 0" (Sunday 3am)
      evidence_days:            int, default 180
      digest_days:              int, default 365
      graph_days:               int, default 365
      cleanup_orphaned_vectors: bool, default True
      dry_run:                  bool, default False (returns counts, no deletes)
      tenants:                  list[str], default [] (empty = all)

    Cascading note:
      Deleting evidence does NOT cascade to VectorStore.
      Orphaned vectors are cleaned separately when cleanup_orphaned_vectors=True
      (runs after evidence deletion: DELETE FROM embeddings WHERE source_table='evidence'
       AND source_id NOT IN (SELECT id FROM evidence)).

    Facets are NOT deleted by this job (they are long-lived identity signals).
    """

    name = "retention"
    trigger = CronTrigger(schedule="0 3 * * 0")
    depends_on: list[str] = []

    def __init__(
        self,
        evidence_days: int = 180,
        digest_days: int = 365,
        graph_days: int = 365,
        cleanup_orphaned_vectors: bool = True,
        dry_run: bool = False,
        tenants: list[str] | None = None,
    ) -> None:
        self._evidence_days = evidence_days
        self._digest_days = digest_days
        self._graph_days = graph_days
        self._cleanup_orphaned_vectors = cleanup_orphaned_vectors
        self._dry_run = dry_run
        self._tenants = tenants or []

    async def run(self, context: JobContext) -> JobResult:
        """Execute retention deletions.

        Returns JobResult with:
          items_processed = total rows deleted (or would-delete in dry_run)
          metadata = {'evidence': N, 'digests': M, 'knowledge_graph': K,
                      'orphaned_vectors': V, 'dry_run': bool}

        Requires context.storage_adapter with a _pool attribute (PostgresStorageAdapter)
        for direct SQL access. If not available, returns 0 items.
        """
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        errors: list[str] = []
        counts: dict[str, int] = {
            "evidence": 0,
            "digests": 0,
            "knowledge_graph": 0,
            "orphaned_vectors": 0,
        }

        storage_adapter = context.storage_adapter
        if storage_adapter is None or not hasattr(storage_adapter, '_pool'):
            return JobResult(
                success=True, items_processed=0,
                errors=["No storage_adapter with pool available — skipping retention"],
                metadata={**counts, "dry_run": self._dry_run},
            )

        pool = storage_adapter._pool
        evidence_cutoff = now - timedelta(days=self._evidence_days)
        digest_cutoff = now - timedelta(days=self._digest_days)
        graph_cutoff = now - timedelta(days=self._graph_days)

        tenant_clause = ""
        params_base: list = []
        if self._tenants:
            placeholders = ", ".join(["%s"] * len(self._tenants))
            tenant_clause = f" AND tenant_id IN ({placeholders})"
            params_base = list(self._tenants)

        # Table → (cutoff_column, cutoff_value)
        targets = [
            ("evidence", "occurred_at", evidence_cutoff),
            ("digests", "period_end", digest_cutoff),
            ("knowledge_graph", "updated_at", graph_cutoff),
        ]

        async with pool.connection() as conn:
            for table, column, cutoff in targets:
                try:
                    params = [cutoff] + params_base
                    if self._dry_run:
                        sql = f"SELECT COUNT(*) FROM {table} WHERE {column} < %s{tenant_clause}"
                        row = await conn.execute(sql, params)
                        result = await row.fetchone()
                        counts[table] = result[0] if result else 0
                    else:
                        sql = f"DELETE FROM {table} WHERE {column} < %s{tenant_clause}"
                        cur = await conn.execute(sql, params)
                        counts[table] = cur.rowcount
                except Exception as e:
                    errors.append(f"{table}: {e}")

            # Clean up orphaned embedding vectors
            if self._cleanup_orphaned_vectors:
                try:
                    if self._dry_run:
                        sql = (
                            "SELECT COUNT(*) FROM embeddings WHERE source_table = 'evidence' "
                            "AND source_id NOT IN (SELECT id FROM evidence)"
                        )
                        row = await conn.execute(sql)
                        result = await row.fetchone()
                        counts["orphaned_vectors"] = result[0] if result else 0
                    else:
                        sql = (
                            "DELETE FROM embeddings WHERE source_table = 'evidence' "
                            "AND source_id NOT IN (SELECT id FROM evidence)"
                        )
                        cur = await conn.execute(sql)
                        counts["orphaned_vectors"] = cur.rowcount
                except Exception as e:
                    errors.append(f"orphaned_vectors: {e}")

        total = sum(counts.values())
        return JobResult(
            success=True, items_processed=total, errors=errors,
            metadata={**counts, "dry_run": self._dry_run},
        )
