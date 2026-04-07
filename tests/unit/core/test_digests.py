# ABOUTME: Test suite for DigestEngine domain service.
# ABOUTME: Tests daily, weekly, monthly digest generation and list filtering.

import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from agentmem.core.models import Digest, DigestFilters, EvidenceFilters, EvidenceRecord
from agentmem.core.digests import DigestEngine


class MockDigestStore:
    def __init__(self):
        self._digests: list[Digest] = []

    async def list(self, filters: DigestFilters) -> list[Digest]:
        result = []
        for digest in self._digests:
            if filters.tenant_id != digest.tenant_id:
                continue
            if filters.digest_type and filters.digest_type != digest.digest_type:
                continue
            if filters.period_start and digest.period_start < filters.period_start:
                continue
            if filters.period_end and digest.period_end > filters.period_end:
                continue
            result.append(digest)
        return result[:filters.limit]

    async def upsert(self, digest: Digest) -> Digest:
        # Find existing digest with same period and type
        for i, existing in enumerate(self._digests):
            if (existing.tenant_id == digest.tenant_id and
                existing.digest_type == digest.digest_type and
                existing.period_start == digest.period_start and
                existing.period_end == digest.period_end):
                self._digests[i] = digest
                return digest
        # Add new digest
        digest.id = len(self._digests) + 1
        self._digests.append(digest)
        return digest


class MockEvidenceStore:
    def __init__(self):
        self._evidence: list[EvidenceRecord] = []

    async def list(self, filters: EvidenceFilters) -> list[EvidenceRecord]:
        result = []
        for evidence in self._evidence:
            if filters.tenant_id != evidence.tenant_id:
                continue
            if filters.event_type and filters.event_type != evidence.event_type:
                continue
            if filters.since and evidence.occurred_at < filters.since:
                continue
            if filters.channel_id and filters.channel_id != evidence.channel_id:
                continue
            result.append(evidence)
        return result[:filters.limit]

    def add_evidence(self, evidence: EvidenceRecord):
        self._evidence.append(evidence)

    async def query(self, filters: EvidenceFilters) -> list[EvidenceRecord]:
        return await self.list(filters)


@pytest.mark.asyncio
async def test_generate_daily_with_no_evidence():
    """Test generating daily digest with no evidence produces empty summary."""
    digest_store = MockDigestStore()
    evidence_store = MockEvidenceStore()
    engine = DigestEngine(digest_store, evidence_store)

    day = date(2026, 4, 6)
    result = await engine.generate_daily("tenant1", day)

    assert result.tenant_id == "tenant1"
    assert result.digest_type == "daily"
    assert result.period_start == datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc)
    assert result.period_end == datetime(2026, 4, 6, 23, 59, 59, 999999, tzinfo=timezone.utc)
    assert result.content == "Daily summary for 2026-04-06"


@pytest.mark.asyncio
async def test_generate_daily_with_evidence():
    """Test generating daily digest with evidence counts events by type."""
    digest_store = MockDigestStore()
    evidence_store = MockEvidenceStore()
    engine = DigestEngine(digest_store, evidence_store)

    # Add evidence for April 6, 2026
    day = date(2026, 4, 6)
    evidence_store.add_evidence(EvidenceRecord(
        tenant_id="tenant1",
        event_type="user_action",
        content="User clicked button",
        occurred_at=datetime(2026, 4, 6, 14, 30, 0, tzinfo=timezone.utc),
        source_event_id="evt1",
        dedupe_key="key1"
    ))
    evidence_store.add_evidence(EvidenceRecord(
        tenant_id="tenant1",
        event_type="user_action",
        content="User clicked another button",
        occurred_at=datetime(2026, 4, 6, 15, 0, 0, tzinfo=timezone.utc),
        source_event_id="evt2",
        dedupe_key="key2"
    ))
    evidence_store.add_evidence(EvidenceRecord(
        tenant_id="tenant1",
        event_type="system_event",
        content="System started",
        occurred_at=datetime(2026, 4, 6, 16, 0, 0, tzinfo=timezone.utc),
        source_event_id="evt3",
        dedupe_key="key3"
    ))

    result = await engine.generate_daily("tenant1", day)

    assert result.tenant_id == "tenant1"
    assert result.digest_type == "daily"
    assert result.period_start == datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc)
    assert result.period_end == datetime(2026, 4, 6, 23, 59, 59, 999999, tzinfo=timezone.utc)
    expected_content = "Daily summary for 2026-04-06\n  system_event: 1 events\n  user_action: 2 events"
    assert result.content == expected_content


@pytest.mark.asyncio
async def test_generate_weekly_rolls_up_daily_digests():
    """Test generating weekly digest rolls up daily digests for Monday-Sunday."""
    digest_store = MockDigestStore()
    evidence_store = MockEvidenceStore()
    engine = DigestEngine(digest_store, evidence_store)

    # Week starting Monday April 7, 2026 (need to ensure this is actually a Monday)
    week_start = date(2026, 4, 6)  # Let's assume this is Monday for the test

    # Add a daily digest for Monday
    monday_digest = Digest(
        tenant_id="tenant1",
        digest_type="daily",
        period_start=datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc),
        period_end=datetime(2026, 4, 6, 23, 59, 59, 999999, tzinfo=timezone.utc),
        content="Daily summary for 2026-04-06\n  user_action: 2 events",
        id=1
    )
    digest_store._digests.append(monday_digest)

    # Add a daily digest for Tuesday
    tuesday_digest = Digest(
        tenant_id="tenant1",
        digest_type="daily",
        period_start=datetime(2026, 4, 7, 0, 0, 0, tzinfo=timezone.utc),
        period_end=datetime(2026, 4, 7, 23, 59, 59, 999999, tzinfo=timezone.utc),
        content="Daily summary for 2026-04-07\n  system_event: 1 events",
        id=2
    )
    digest_store._digests.append(tuesday_digest)

    result = await engine.generate_weekly("tenant1", week_start)

    assert result.tenant_id == "tenant1"
    assert result.digest_type == "weekly"
    # Week should start Monday 00:00 and end Sunday 23:59
    assert result.period_start == datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc)
    assert result.period_end == datetime(2026, 4, 12, 23, 59, 59, 999999, tzinfo=timezone.utc)

    expected_content = "Weekly summary for week of 2026-04-06\nDaily summary for 2026-04-06\n  user_action: 2 events\nDaily summary for 2026-04-07\n  system_event: 1 events"
    assert result.content == expected_content