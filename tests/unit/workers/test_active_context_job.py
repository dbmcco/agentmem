# ABOUTME: Tests for ActiveContextJob — the contract verification file.
# ABOUTME: Verifies handle() calls router, upserts context, ingests evidence, and heartbeats.
"""Tests for ActiveContextJob (wg-contract verification target)."""
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock

import pytest

from agentmem.core.models import EventRecord, ContextSection, EvidenceRecord
from agentmem.workers.coordinator import JobContext
from agentmem.workers.jobs.active_context import ActiveContextJob


@pytest.fixture
def mock_context():
    """Create a mock JobContext for testing ActiveContextJob."""
    context = Mock(spec=JobContext)
    context.event_router = Mock()
    context.active_context_store = Mock()
    context.active_context_store.upsert = AsyncMock()
    context.evidence_ledger = Mock()
    context.evidence_ledger.ingest = AsyncMock()
    context.heartbeat = AsyncMock()
    context.config = {'default_tenant': 'default'}
    return context


@pytest.fixture
def mock_event():
    """Create a mock EventRecord for testing."""
    return EventRecord(
        event_type='test.event',
        payload={'key': 'value'},
        occurred_at=datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc),
        dedupe_key='dedupe-123',
        tenant_id='tenant-1',
        source_event_id='src-evt-1',
    )


class TestActiveContextJobAttributes:
    """Verify job metadata."""

    def test_name(self):
        job = ActiveContextJob()
        assert job.name == 'active_context'

    def test_trigger_source(self):
        job = ActiveContextJob()
        assert job.trigger.source == 'pg_listen'

    def test_heartbeat_interval(self):
        job = ActiveContextJob()
        assert job.heartbeat_interval_seconds == 30.0


class TestActiveContextJobHandle:
    """Verify handle() fulfils the spec contract."""

    async def test_calls_router_format(self, mock_context, mock_event):
        """handle() must call context.event_router.format(event)."""
        job = ActiveContextJob()
        mock_context.event_router.format.return_value = 'formatted'
        mock_context.event_router.section_for.return_value = 'section'

        await job.handle(mock_event, mock_context)

        mock_context.event_router.format.assert_called_once_with(mock_event)

    async def test_calls_router_section_for(self, mock_context, mock_event):
        """handle() must call context.event_router.section_for(event)."""
        job = ActiveContextJob()
        mock_context.event_router.format.return_value = 'formatted'
        mock_context.event_router.section_for.return_value = 'section'

        await job.handle(mock_event, mock_context)

        mock_context.event_router.section_for.assert_called_once_with(mock_event)

    async def test_upserts_context_section(self, mock_context, mock_event):
        """handle() must call active_context_store.upsert() with a ContextSection."""
        job = ActiveContextJob()
        mock_context.event_router.format.return_value = 'formatted content'
        mock_context.event_router.section_for.return_value = 'my_section'

        await job.handle(mock_event, mock_context)

        mock_context.active_context_store.upsert.assert_called_once()
        cs = mock_context.active_context_store.upsert.call_args[0][0]
        assert isinstance(cs, ContextSection)
        assert cs.tenant_id == 'tenant-1'
        assert cs.section == 'my_section'
        assert cs.content == 'formatted content'

    async def test_skips_upsert_when_section_is_none(self, mock_context, mock_event):
        """handle() must skip upsert when section_for returns None."""
        job = ActiveContextJob()
        mock_context.event_router.format.return_value = 'formatted'
        mock_context.event_router.section_for.return_value = None

        await job.handle(mock_event, mock_context)

        mock_context.active_context_store.upsert.assert_not_called()

    async def test_ingests_evidence(self, mock_context, mock_event):
        """handle() must call evidence_ledger.ingest() with an EvidenceRecord."""
        job = ActiveContextJob()
        mock_context.event_router.format.return_value = 'formatted content'
        mock_context.event_router.section_for.return_value = 'section'

        await job.handle(mock_event, mock_context)

        mock_context.evidence_ledger.ingest.assert_called_once()
        record = mock_context.evidence_ledger.ingest.call_args[0][0]
        assert isinstance(record, EvidenceRecord)
        assert record.tenant_id == 'tenant-1'
        assert record.event_type == 'test.event'
        assert record.content == 'formatted content'
        assert record.dedupe_key == 'dedupe-123'
        assert record.source_event_id == 'src-evt-1'
        assert record.metadata == {'key': 'value'}

    async def test_ingests_evidence_even_when_no_section(self, mock_context, mock_event):
        """Evidence ingestion happens regardless of whether section is None."""
        job = ActiveContextJob()
        mock_context.event_router.format.return_value = 'formatted'
        mock_context.event_router.section_for.return_value = None

        await job.handle(mock_event, mock_context)

        mock_context.evidence_ledger.ingest.assert_called_once()

    async def test_calls_heartbeat(self, mock_context, mock_event):
        """handle() must call context.heartbeat()."""
        job = ActiveContextJob()
        mock_context.event_router.format.return_value = 'formatted'
        mock_context.event_router.section_for.return_value = 'section'

        await job.handle(mock_event, mock_context)

        mock_context.heartbeat.assert_called_once()

    async def test_uses_default_tenant_when_event_has_none(self, mock_context):
        """When event.tenant_id is None, fallback to 'default'."""
        event = EventRecord(
            event_type='test.event',
            payload={},
            occurred_at=datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc),
            dedupe_key='dedupe-no-tenant',
            tenant_id=None,
            source_event_id=None,
        )
        job = ActiveContextJob()
        mock_context.event_router.format.return_value = 'content'
        mock_context.event_router.section_for.return_value = 'section'

        await job.handle(event, mock_context)

        cs = mock_context.active_context_store.upsert.call_args[0][0]
        assert cs.tenant_id == 'default'

        record = mock_context.evidence_ledger.ingest.call_args[0][0]
        assert record.tenant_id == 'default'
        assert record.source_event_id == ''
