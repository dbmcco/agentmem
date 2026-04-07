# ABOUTME: Tests for DigestGenerationJob — scheduled digest generation.
# ABOUTME: Covers daily/weekly/monthly calendar logic, tenant iteration, and result structure.
"""Tests for DigestGenerationJob scheduling and calendar logic."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agentmem.core.models import JobResult
from agentmem.workers.coordinator import JobContext
from agentmem.workers.jobs.digest import DigestGenerationJob
from agentmem.workers.triggers import CronTrigger


@pytest.fixture
def mock_context():
    """Create a mock JobContext with digest_engine stub."""
    ctx = Mock(spec=JobContext)
    ctx.digest_engine = Mock()
    ctx.digest_engine.generate = AsyncMock()
    ctx.config = {"tenants": ["default"]}
    return ctx


def _utc_now_for_date(d: date) -> datetime:
    """Return a UTC datetime at 23:59 on the given date (typical cron fire time)."""
    return datetime(d.year, d.month, d.day, 23, 59, 0, tzinfo=timezone.utc)


# ── Initialisation ─────────────────────────────────────────────────────────


class TestDigestJobInit:
    def test_defaults(self):
        job = DigestGenerationJob()
        assert job._types == ["daily", "weekly", "monthly"]
        assert job._timezone_name == "UTC"
        assert job.name == "digest_generation"
        assert isinstance(job.trigger, CronTrigger)
        assert job.trigger.schedule == "59 23 * * *"
        assert job.depends_on == []

    def test_custom_types(self):
        job = DigestGenerationJob(types=["daily"])
        assert job._types == ["daily"]

    def test_custom_timezone(self):
        job = DigestGenerationJob(timezone_name="America/New_York")
        assert job._timezone_name == "America/New_York"


# ── Daily digest: always generated ─────────────────────────────────────────


class TestDailyDigest:
    """Daily digest should be generated on every run, regardless of weekday."""

    @pytest.mark.parametrize("weekday_offset", range(7))
    async def test_daily_generated_every_day_of_week(self, mock_context, weekday_offset):
        """Daily digest fires on Mon-Sun."""
        # 2026-04-06 is a Monday; offset 0-6 covers Mon-Sun
        target = date(2026, 4, 6) + timedelta(days=weekday_offset)
        now = _utc_now_for_date(target)

        job = DigestGenerationJob(types=["daily"])
        with patch("agentmem.workers.jobs.digest.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await job.run(mock_context)

        assert result.success is True
        assert result.items_processed == 1
        mock_context.digest_engine.generate.assert_called_once()
        call_args = mock_context.digest_engine.generate.call_args[0]
        assert call_args[0] == "default"  # tenant_id
        assert call_args[1] == "daily"  # digest_type

    async def test_daily_period_boundaries(self, mock_context):
        """Daily period should span midnight-to-midnight."""
        target = date(2026, 4, 7)
        now = _utc_now_for_date(target)

        job = DigestGenerationJob(types=["daily"])
        with patch("agentmem.workers.jobs.digest.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            await job.run(mock_context)

        call_args = mock_context.digest_engine.generate.call_args[0]
        period_start = call_args[2]
        period_end = call_args[3]
        assert period_start == datetime(2026, 4, 7, 0, 0, 0, tzinfo=timezone.utc)
        assert period_end == datetime(2026, 4, 7, 23, 59, 59, tzinfo=timezone.utc)


# ── Weekly digest: only on Monday ──────────────────────────────────────────


class TestWeeklyDigest:
    """Weekly digest should only fire on Monday (weekday() == 0)."""

    async def test_weekly_generated_on_monday(self, mock_context):
        """2026-04-06 is a Monday — weekly digest should fire."""
        monday = date(2026, 4, 6)
        assert monday.weekday() == 0
        now = _utc_now_for_date(monday)

        job = DigestGenerationJob(types=["weekly"])
        with patch("agentmem.workers.jobs.digest.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await job.run(mock_context)

        assert result.items_processed == 1
        call_args = mock_context.digest_engine.generate.call_args[0]
        assert call_args[1] == "weekly"

    @pytest.mark.parametrize("day_offset", [1, 2, 3, 4, 5, 6])
    async def test_weekly_skipped_on_non_monday(self, mock_context, day_offset):
        """Tue–Sun should NOT generate a weekly digest."""
        non_monday = date(2026, 4, 6) + timedelta(days=day_offset)
        assert non_monday.weekday() != 0
        now = _utc_now_for_date(non_monday)

        job = DigestGenerationJob(types=["weekly"])
        with patch("agentmem.workers.jobs.digest.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await job.run(mock_context)

        assert result.items_processed == 0
        mock_context.digest_engine.generate.assert_not_called()

    async def test_weekly_period_spans_full_week(self, mock_context):
        """Weekly period should span Mon 00:00 – Sun 23:59:59."""
        monday = date(2026, 4, 6)
        now = _utc_now_for_date(monday)

        job = DigestGenerationJob(types=["weekly"])
        with patch("agentmem.workers.jobs.digest.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            await job.run(mock_context)

        call_args = mock_context.digest_engine.generate.call_args[0]
        period_start = call_args[2]
        period_end = call_args[3]
        assert period_start == datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc)
        assert period_end == datetime(2026, 4, 12, 23, 59, 59, tzinfo=timezone.utc)


# ── Monthly digest: only on 1st ────────────────────────────────────────────


class TestMonthlyDigest:
    """Monthly digest should only fire on the 1st of the month."""

    async def test_monthly_generated_on_first(self, mock_context):
        """2026-04-01 — monthly digest should fire."""
        first = date(2026, 4, 1)
        now = _utc_now_for_date(first)

        job = DigestGenerationJob(types=["monthly"])
        with patch("agentmem.workers.jobs.digest.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await job.run(mock_context)

        assert result.items_processed == 1
        call_args = mock_context.digest_engine.generate.call_args[0]
        assert call_args[1] == "monthly"

    @pytest.mark.parametrize("day", [2, 10, 15, 28])
    async def test_monthly_skipped_on_non_first(self, mock_context, day):
        """Days other than the 1st should NOT generate a monthly digest."""
        non_first = date(2026, 4, day)
        now = _utc_now_for_date(non_first)

        job = DigestGenerationJob(types=["monthly"])
        with patch("agentmem.workers.jobs.digest.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await job.run(mock_context)

        assert result.items_processed == 0
        mock_context.digest_engine.generate.assert_not_called()

    async def test_monthly_period_spans_full_month(self, mock_context):
        """Monthly period should span 1st 00:00 – last-day 23:59:59."""
        first = date(2026, 4, 1)
        now = _utc_now_for_date(first)

        job = DigestGenerationJob(types=["monthly"])
        with patch("agentmem.workers.jobs.digest.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            await job.run(mock_context)

        call_args = mock_context.digest_engine.generate.call_args[0]
        period_start = call_args[2]
        period_end = call_args[3]
        assert period_start == datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert period_end == datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc)


# ── Combined run and result structure ──────────────────────────────────────


class TestCombinedRun:
    """Test multiple digest types in a single run and result structure."""

    async def test_all_types_on_monday_first(self, mock_context):
        """2026-06-01 is a Monday AND 1st — all three types should fire."""
        target = date(2026, 6, 1)
        assert target.weekday() == 0  # Monday
        assert target.day == 1
        now = _utc_now_for_date(target)

        job = DigestGenerationJob()
        with patch("agentmem.workers.jobs.digest.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await job.run(mock_context)

        assert result.success is True
        assert result.items_processed == 3  # daily + weekly + monthly
        assert mock_context.digest_engine.generate.call_count == 3

    async def test_result_is_job_result(self, mock_context):
        """Return type is JobResult with expected fields."""
        now = _utc_now_for_date(date(2026, 4, 7))
        job = DigestGenerationJob(types=["daily"])
        with patch("agentmem.workers.jobs.digest.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await job.run(mock_context)

        assert isinstance(result, JobResult)
        assert hasattr(result, "success")
        assert hasattr(result, "items_processed")
        assert hasattr(result, "errors")
        assert hasattr(result, "metadata")

    async def test_multiple_tenants(self, mock_context):
        """Digest generation iterates over all configured tenants."""
        mock_context.config = {"tenants": ["alpha", "beta", "gamma"]}
        now = _utc_now_for_date(date(2026, 4, 7))

        job = DigestGenerationJob(types=["daily"])
        with patch("agentmem.workers.jobs.digest.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await job.run(mock_context)

        assert result.items_processed == 3  # 1 daily * 3 tenants
        assert mock_context.digest_engine.generate.call_count == 3
        tenant_ids = [
            call[0][0] for call in mock_context.digest_engine.generate.call_args_list
        ]
        assert tenant_ids == ["alpha", "beta", "gamma"]

    async def test_empty_types_produces_zero(self, mock_context):
        """If no types are configured, nothing is generated."""
        job = DigestGenerationJob(types=[])
        result = await job.run(mock_context)

        assert result.success is True
        assert result.items_processed == 0
        mock_context.digest_engine.generate.assert_not_called()
