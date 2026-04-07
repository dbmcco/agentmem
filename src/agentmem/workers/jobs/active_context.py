# ABOUTME: ActiveContextJob — continuous event-driven context section maintenance.
# ABOUTME: Replaces paia-memory's ActiveStateBuilder + hardcoded LISTEN/NOTIFY handler.
"""ActiveContextJob: continuous event-driven active context updater."""
from __future__ import annotations

from agentmem.core.models import EventRecord, JobResult
from agentmem.workers.coordinator import JobContext, ContinuousJob
from agentmem.workers.triggers import ContinuousTrigger


class ActiveContextJob(ContinuousJob):
    """Update named active context sections as events arrive.

    Trigger: ContinuousTrigger(source="pg_listen") or whichever source is configured.
    heartbeat_interval_seconds: 30.0 (coordinator restarts if no heartbeat within window).

    For each incoming EventRecord:
      1. Call context.event_router.format(event) → content string
      2. Call context.event_router.section_for(event) → section name (or None)
      3. If section is not None: upsert ContextSection to context.active_context_store
      4. Call context.heartbeat() to keep coordinator watchdog happy

    Reconnect: handled by WorkerCoordinator._run_continuous (exponential backoff).
    Dead-letter: after 5 consecutive failures, coordinator publishes "job:dead" event.
    """

    name = "active_context"
    trigger = ContinuousTrigger(source="pg_listen")
    heartbeat_interval_seconds = 30.0

    async def handle(self, event: EventRecord, context: JobContext) -> None:
        """Process one event: format content, update active context section, ingest evidence.

        Must call context.heartbeat() to signal liveness.
        """
        content = context.event_router.format(event)
        section = context.event_router.section_for(event)
        tenant_id = event.tenant_id or 'default'

        if section is not None:
            from agentmem.core.models import ContextSection
            cs = ContextSection(
                tenant_id=tenant_id,
                section=section,
                content=content,
            )
            await context.active_context_store.upsert(cs)

        # Also ingest as evidence
        from agentmem.core.models import EvidenceRecord as ER
        from datetime import datetime, timezone
        record = ER(
            tenant_id=tenant_id,
            event_type=event.event_type,
            content=content,
            occurred_at=event.occurred_at or datetime.now(timezone.utc),
            source_event_id=event.source_event_id or '',
            dedupe_key=event.dedupe_key,
            metadata=event.payload,
        )
        await context.evidence_ledger.ingest(record)

        await context.heartbeat()
