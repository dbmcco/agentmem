# ABOUTME: DigestGenerationJob — nightly progressive digest generation.
# ABOUTME: Replaces the unscheduled DigestEngine.generate_*() calls in paia-memory.
"""DigestGenerationJob: scheduled digest generation."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from agentmem.core.models import JobResult
from agentmem.workers.coordinator import JobContext, ScheduledJob
from agentmem.workers.triggers import CronTrigger


class DigestGenerationJob(ScheduledJob):
    """Generate daily/weekly/monthly digests on schedule.

    Config keys (from context.config["workers"]["digest"]):
      trigger:   cron string, default "cron:59 23 * * *"
      types:     list[str], default ["daily", "weekly", "monthly"]
      timezone:  str, default "UTC"

    Period boundaries (UTC):
      daily   = midnight-to-midnight of trigger date
      weekly  = Monday 00:00 – Sunday 23:59 (only generated on Monday trigger)
      monthly = 1st 00:00 – last day 23:59 (only generated on 1st trigger)

    Idempotent: re-running same period overwrites existing digest (upsert semantics).

    Order of execution: daily first, then weekly (if applicable), then monthly.
    """

    name = "digest_generation"
    trigger = CronTrigger(schedule="59 23 * * *")
    depends_on: list[str] = []

    def __init__(
        self,
        types: list[str] | None = None,
        timezone_name: str = "UTC",
    ) -> None:
        self._types = types if types is not None else ['daily', 'weekly', 'monthly']
        self._timezone_name = timezone_name

    async def run(self, context: JobContext) -> JobResult:
        """Generate digests for all configured types.

        Uses context.digest_engine.generate().
        Returns JobResult with items_processed = number of digests generated.
        """
        now = datetime.now(timezone.utc)
        today = now.date()
        count = 0

        # Get all tenants from config or default
        tenants = context.config.get('tenants', ['default'])

        if 'daily' in self._types:
            period_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
            period_end = period_start + timedelta(days=1) - timedelta(seconds=1)
            for tenant_id in tenants:
                await context.digest_engine.generate(tenant_id, 'daily', period_start, period_end)
                count += 1

        if 'weekly' in self._types and today.weekday() == 0:  # Monday
            start_of_week = today - timedelta(days=today.weekday())
            period_start = datetime(start_of_week.year, start_of_week.month, start_of_week.day, tzinfo=timezone.utc)
            period_end = period_start + timedelta(days=7) - timedelta(seconds=1)
            for tenant_id in tenants:
                await context.digest_engine.generate(tenant_id, 'weekly', period_start, period_end)
                count += 1

        if 'monthly' in self._types and today.day == 1:
            import calendar
            period_start = datetime(today.year, today.month, 1, tzinfo=timezone.utc)
            last_day = calendar.monthrange(today.year, today.month)[1]
            period_end = datetime(today.year, today.month, last_day, 23, 59, 59, tzinfo=timezone.utc)
            for tenant_id in tenants:
                await context.digest_engine.generate(tenant_id, 'monthly', period_start, period_end)
                count += 1

        return JobResult(success=True, items_processed=count)
