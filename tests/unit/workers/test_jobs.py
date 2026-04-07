# ABOUTME: Tests for all worker job implementations.
# ABOUTME: Covers EmbedReindexJob, DigestGenerationJob, RetentionJob, and ActiveContextJob.
"""Tests for worker job implementations."""
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock
from dataclasses import dataclass

import pytest

from agentmem.core.models import JobResult, EventRecord, ContextSection
from agentmem.workers.coordinator import JobContext
from agentmem.workers.jobs.embed_reindex import EmbedReindexJob
from agentmem.workers.jobs.digest import DigestGenerationJob
from agentmem.workers.jobs.retention import RetentionJob
from agentmem.workers.jobs.active_context import ActiveContextJob


@pytest.fixture
def mock_context():
    """Create a mock JobContext for testing jobs."""
    context = Mock(spec=JobContext)
    context.embedding_service = Mock()
    context.digest_engine = Mock()
    context.active_context_store = Mock()
    context.event_router = Mock()
    context.config = {'tenants': ['default']}
    context.evidence_ledger = Mock()
    context.evidence_ledger.ingest = AsyncMock()
    context.heartbeat = AsyncMock()
    return context


@pytest.fixture
def mock_event():
    """Create a mock EventRecord for testing."""
    return EventRecord(
        event_type='test.event',
        payload={'content': 'test content'},
        occurred_at=datetime.now(timezone.utc),
        dedupe_key='test-dedupe',
        tenant_id='default',
        source_event_id='test-123'
    )


class TestEmbedReindexJob:
    """Tests for EmbedReindexJob."""

    def test_init_with_defaults(self):
        """Test EmbedReindexJob initializes with default values."""
        job = EmbedReindexJob()
        assert job._batch_size == 100
        assert job._tenants == []

    def test_init_with_custom_values(self):
        """Test EmbedReindexJob initializes with custom values."""
        job = EmbedReindexJob(batch_size=50, tenants=['tenant1', 'tenant2'])
        assert job._batch_size == 50
        assert job._tenants == ['tenant1', 'tenant2']

    async def test_run_calls_reindex_for_all_tables(self, mock_context):
        """Test run calls embedding_service.reindex for evidence, facets, and digests."""
        job = EmbedReindexJob()
        mock_context.embedding_service.reindex = AsyncMock(return_value=10)

        result = await job.run(mock_context)

        assert isinstance(result, JobResult)
        assert result.success is True
        # 3 tables * 1 tenant (None=all) * 10 items each = 30
        assert result.items_processed == 30
        assert mock_context.embedding_service.reindex.call_count == 3
        calls = mock_context.embedding_service.reindex.call_args_list
        assert calls[0][0] == ('evidence', None, 100)
        assert calls[1][0] == ('facets', None, 100)
        assert calls[2][0] == ('digests', None, 100)

    async def test_run_with_specific_tenants(self, mock_context):
        """Test run iterates per-tenant when tenants are configured."""
        job = EmbedReindexJob(batch_size=50, tenants=['t1', 't2'])
        mock_context.embedding_service.reindex = AsyncMock(return_value=5)

        result = await job.run(mock_context)

        assert result.success is True
        # 3 tables * 2 tenants * 5 items = 30
        assert result.items_processed == 30
        assert mock_context.embedding_service.reindex.call_count == 6

    async def test_run_collects_errors(self, mock_context):
        """Test run captures errors per table/tenant without failing."""
        job = EmbedReindexJob()
        mock_context.embedding_service.reindex = AsyncMock(side_effect=RuntimeError("db down"))

        result = await job.run(mock_context)

        assert result.success is True
        assert result.items_processed == 0
        assert len(result.errors) == 3


class TestDigestGenerationJob:
    """Tests for DigestGenerationJob."""

    def test_init_with_defaults(self):
        """Test DigestGenerationJob initializes with default values."""
        job = DigestGenerationJob()
        assert job._types == ['daily', 'weekly', 'monthly']
        assert job._timezone_name == 'UTC'

    def test_init_with_custom_values(self):
        """Test DigestGenerationJob initializes with custom values."""
        job = DigestGenerationJob(types=['daily'], timezone_name='America/New_York')
        assert job._types == ['daily']
        assert job._timezone_name == 'America/New_York'

    async def test_run_returns_job_result(self, mock_context):
        """Test DigestGenerationJob.run returns a JobResult."""
        job = DigestGenerationJob()
        mock_context.digest_engine.generate = AsyncMock()

        result = await job.run(mock_context)

        assert isinstance(result, JobResult)
        assert result.success is True
        assert result.items_processed >= 0

    async def test_run_generates_daily_digest(self, mock_context):
        """Test run generates daily digest with correct period boundaries."""
        job = DigestGenerationJob(types=['daily'])
        mock_context.digest_engine.generate = AsyncMock()

        result = await job.run(mock_context)

        # Should have called generate for daily digest
        assert mock_context.digest_engine.generate.call_count >= 1
        call_args = mock_context.digest_engine.generate.call_args_list[0][0]
        assert call_args[1] == 'daily'  # digest type
        assert result.items_processed >= 1

    async def test_run_generates_all_digest_types_when_configured(self, mock_context):
        """Test run processes all digest types when configured."""
        job = DigestGenerationJob(types=['daily', 'weekly', 'monthly'])
        mock_context.digest_engine.generate = AsyncMock()

        result = await job.run(mock_context)

        # Should have generated at least daily digest
        assert result.items_processed >= 1
        assert result.success is True


class TestRetentionJob:
    """Tests for RetentionJob."""

    def test_init_with_defaults(self):
        """Test RetentionJob initializes with default values."""
        job = RetentionJob()
        assert job._evidence_days == 180
        assert job._digest_days == 365
        assert job._graph_days == 365
        assert job._cleanup_orphaned_vectors is True
        assert job._dry_run is False
        assert job._tenants == []

    def test_init_with_custom_values(self):
        """Test RetentionJob initializes with custom values."""
        job = RetentionJob(
            evidence_days=90,
            digest_days=180,
            graph_days=180,
            cleanup_orphaned_vectors=False,
            dry_run=True,
            tenants=['tenant1']
        )
        assert job._evidence_days == 90
        assert job._digest_days == 180
        assert job._graph_days == 180
        assert job._cleanup_orphaned_vectors is False
        assert job._dry_run is True
        assert job._tenants == ['tenant1']

    async def test_run_without_storage_adapter(self, mock_context):
        """Test run returns 0 with warning when storage_adapter is None."""
        mock_context.storage_adapter = None
        job = RetentionJob()
        result = await job.run(mock_context)

        assert isinstance(result, JobResult)
        assert result.success is True
        assert result.items_processed == 0
        assert len(result.errors) == 1
        assert "storage_adapter" in result.errors[0]

    async def test_run_without_pool_on_adapter(self, mock_context):
        """Test run returns 0 when storage_adapter has no _pool."""
        mock_context.storage_adapter = Mock(spec=[])  # no _pool attribute
        job = RetentionJob()
        result = await job.run(mock_context)

        assert result.success is True
        assert result.items_processed == 0

    def _make_pool_mock(self, conn_mock):
        """Helper to create a mock pool with async context manager for connection()."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_connection():
            yield conn_mock

        pool = Mock()
        pool.connection = fake_connection
        return pool

    async def test_run_deletes_stale_rows(self, mock_context):
        """Test run executes DELETE statements against all three tables."""
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 5
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)

        mock_adapter = Mock()
        mock_adapter._pool = self._make_pool_mock(mock_conn)
        mock_context.storage_adapter = mock_adapter

        job = RetentionJob(cleanup_orphaned_vectors=False)
        result = await job.run(mock_context)

        assert result.success is True
        # 3 tables * 5 rows each = 15
        assert result.items_processed == 15
        assert mock_conn.execute.call_count == 3

    async def test_run_dry_run_counts_without_deleting(self, mock_context):
        """Test dry_run mode uses SELECT COUNT instead of DELETE."""
        mock_row = AsyncMock()
        mock_row.fetchone = AsyncMock(return_value=(42,))
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_row)

        mock_adapter = Mock()
        mock_adapter._pool = self._make_pool_mock(mock_conn)
        mock_context.storage_adapter = mock_adapter

        job = RetentionJob(dry_run=True, cleanup_orphaned_vectors=False)
        result = await job.run(mock_context)

        assert result.success is True
        # 3 tables * 42 rows each = 126
        assert result.items_processed == 126
        # Verify SELECT COUNT was used, not DELETE
        for call in mock_conn.execute.call_args_list:
            assert "SELECT COUNT" in call[0][0]


class TestActiveContextJob:
    """Tests for ActiveContextJob."""

    def test_job_attributes(self):
        """Test ActiveContextJob has correct attributes."""
        job = ActiveContextJob()
        assert job.name == "active_context"
        assert hasattr(job.trigger, 'source')
        assert job.heartbeat_interval_seconds == 30.0

    async def test_handle_processes_event_and_heartbeats(self, mock_context, mock_event):
        """Test handle processes event and calls heartbeat."""
        job = ActiveContextJob()
        mock_context.event_router.format.return_value = "formatted content"
        mock_context.event_router.section_for.return_value = "test_section"
        mock_context.active_context_store.upsert = AsyncMock()

        await job.handle(mock_event, mock_context)

        # Should have formatted the event
        mock_context.event_router.format.assert_called_once_with(mock_event)

        # Should have gotten section name
        mock_context.event_router.section_for.assert_called_once_with(mock_event)

        # Should have upserted context section
        mock_context.active_context_store.upsert.assert_called_once()
        upsert_arg = mock_context.active_context_store.upsert.call_args[0][0]
        assert isinstance(upsert_arg, ContextSection)
        assert upsert_arg.tenant_id == 'default'
        assert upsert_arg.section == 'test_section'
        assert upsert_arg.content == 'formatted content'

        # Should have called heartbeat
        mock_context.heartbeat.assert_called_once()

    async def test_handle_skips_upsert_when_no_section(self, mock_context, mock_event):
        """Test handle skips upsert when section_for returns None."""
        job = ActiveContextJob()
        mock_context.event_router.format.return_value = "formatted content"
        mock_context.event_router.section_for.return_value = None
        mock_context.active_context_store.upsert = AsyncMock()

        await job.handle(mock_event, mock_context)

        # Should have formatted the event
        mock_context.event_router.format.assert_called_once_with(mock_event)

        # Should have gotten section name
        mock_context.event_router.section_for.assert_called_once_with(mock_event)

        # Should NOT have upserted context section
        mock_context.active_context_store.upsert.assert_not_called()

        # Should still have called heartbeat
        mock_context.heartbeat.assert_called_once()