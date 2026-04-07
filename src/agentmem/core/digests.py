# ABOUTME: DigestEngine domain service.
# ABOUTME: Progressive time-windowed summaries (daily/weekly/monthly). Upsert semantics.
"""DigestEngine: domain service for time-windowed memory digests."""
from __future__ import annotations

from datetime import datetime, date, timezone, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentmem.core.models import Digest, DigestFilters, EvidenceFilters, EvidenceRecord
    from agentmem.core.protocols import DigestStoreProtocol, EvidenceStore


class DigestEngine:
    """Generates and stores progressive time-windowed digests.

    Digest content is deterministic (concatenated evidence summaries in v1).
    LLM-generated summaries are out of scope for v1.

    Period boundaries (UTC):
      daily   = midnight-to-midnight of trigger date
      weekly  = Monday 00:00 – Sunday 23:59
      monthly = 1st 00:00 – last day 23:59

    Upsert semantics: re-running same period overwrites existing digest.
    """

    def __init__(
        self,
        store: DigestStoreProtocol,
        evidence_store: EvidenceStore,
    ) -> None:
        self._store = store
        self._evidence_store = evidence_store

    async def generate(
        self,
        tenant_id: str,
        digest_type: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Digest:
        """Generate (or regenerate) a digest for the given period.

        Queries evidence in [period_start, period_end], formats content,
        upserts to DigestStore. Returns the stored Digest.
        """
        from agentmem.core.models import EvidenceFilters, Digest
        filters = EvidenceFilters(tenant_id=tenant_id, since=period_start, limit=1000)
        records = await self._evidence_store.query(filters)
        # filter to period_end
        records = [r for r in records if r.occurred_at <= period_end]
        content = chr(10).join(f'[{r.event_type}] {r.content}' for r in records)
        digest = Digest(
            tenant_id=tenant_id,
            digest_type=digest_type,
            period_start=period_start,
            period_end=period_end,
            content=content
        )
        return await self._store.upsert(digest)

    async def list(self, filters: DigestFilters) -> list[Digest]:
        """List stored digests matching filters."""
        return await self._store.list(filters)

    async def generate_daily(self, tenant_id: str, day: date) -> Digest:
        """Generate a daily digest for the given date.

        Content format: "Daily summary for YYYY-MM-DD\\n  event_type: N events"
        """
        # Set up period boundaries for the full day (UTC)
        period_start = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
        period_end = datetime.combine(day, datetime.max.time()).replace(tzinfo=timezone.utc)

        # Query evidence for this day
        from agentmem.core.models import EvidenceFilters
        filters = EvidenceFilters(tenant_id=tenant_id, since=period_start, limit=1000)
        records = await self._evidence_store.query(filters)

        # Filter to period_end
        records = [r for r in records if r.occurred_at <= period_end]

        # Group by event type and count
        event_counts: dict[str, int] = {}
        for record in records:
            event_counts[record.event_type] = event_counts.get(record.event_type, 0) + 1

        # Format content
        content = f"Daily summary for {day.isoformat()}"
        if event_counts:
            for event_type in sorted(event_counts.keys()):
                content += f"\n  {event_type}: {event_counts[event_type]} events"

        # Create and store digest
        from agentmem.core.models import Digest
        digest = Digest(
            tenant_id=tenant_id,
            digest_type="daily",
            period_start=period_start,
            period_end=period_end,
            content=content
        )
        return await self._store.upsert(digest)

    async def generate_weekly(self, tenant_id: str, week_start: date) -> Digest:
        """Generate a weekly digest for the week starting on the given date.

        Week runs Monday to Sunday. Content aggregates daily digests.
        """
        # Ensure week_start is Monday and calculate week_end (Sunday)
        days_since_monday = week_start.weekday()  # Monday = 0
        actual_week_start = week_start - timedelta(days=days_since_monday)
        week_end = actual_week_start + timedelta(days=6)  # Sunday

        period_start = datetime.combine(actual_week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
        period_end = datetime.combine(week_end, datetime.max.time()).replace(tzinfo=timezone.utc)

        # Query daily digests for this week
        from agentmem.core.models import DigestFilters
        filters = DigestFilters(
            tenant_id=tenant_id,
            digest_type="daily",
            period_start=period_start,
            period_end=period_end,
            limit=7
        )
        daily_digests = await self._store.list(filters)

        # Combine daily digest content
        content = f"Weekly summary for week of {actual_week_start.isoformat()}"
        for digest in sorted(daily_digests, key=lambda d: d.period_start):
            content += f"\n{digest.content}"

        # Create and store weekly digest
        from agentmem.core.models import Digest
        digest = Digest(
            tenant_id=tenant_id,
            digest_type="weekly",
            period_start=period_start,
            period_end=period_end,
            content=content
        )
        return await self._store.upsert(digest)
