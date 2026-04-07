# ABOUTME: Tests for RetentionJob — configurable data pruning.
# ABOUTME: Covers dry_run counting, DELETE with correct WHERE, tenant filtering, orphaned vectors.
"""Tests for RetentionJob."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest

from agentmem.core.models import JobResult
from agentmem.workers.coordinator import JobContext
from agentmem.workers.jobs.retention import RetentionJob


@pytest.fixture
def mock_context():
    """Create a mock JobContext for testing RetentionJob."""
    context = Mock(spec=JobContext)
    context.embedding_service = Mock()
    context.digest_engine = Mock()
    context.active_context_store = Mock()
    context.event_router = Mock()
    context.config = {"tenants": ["default"]}
    context.evidence_ledger = Mock()
    context.evidence_ledger.ingest = AsyncMock()
    context.heartbeat = AsyncMock()
    context.storage_adapter = None
    return context


def _make_pool(conn_mock):
    """Build a mock pool whose connection() yields *conn_mock*."""

    @asynccontextmanager
    async def fake_connection():
        yield conn_mock

    pool = Mock()
    pool.connection = fake_connection
    return pool


# ── Init defaults / custom ──────────────────────────────────────────────

class TestRetentionJobInit:
    def test_defaults(self):
        job = RetentionJob()
        assert job._evidence_days == 180
        assert job._digest_days == 365
        assert job._graph_days == 365
        assert job._cleanup_orphaned_vectors is True
        assert job._dry_run is False
        assert job._tenants == []

    def test_custom_values(self):
        job = RetentionJob(
            evidence_days=90,
            digest_days=180,
            graph_days=180,
            cleanup_orphaned_vectors=False,
            dry_run=True,
            tenants=["t1"],
        )
        assert job._evidence_days == 90
        assert job._digest_days == 180
        assert job._graph_days == 180
        assert job._cleanup_orphaned_vectors is False
        assert job._dry_run is True
        assert job._tenants == ["t1"]

    def test_class_attributes(self):
        assert RetentionJob.name == "retention"
        assert RetentionJob.depends_on == []


# ── No storage adapter fallback ──────────────────────────────────────────

class TestRetentionJobNoStorage:
    async def test_returns_zero_when_adapter_is_none(self, mock_context):
        mock_context.storage_adapter = None
        result = await RetentionJob().run(mock_context)

        assert result.success is True
        assert result.items_processed == 0
        assert any("storage_adapter" in e for e in result.errors)

    async def test_returns_zero_when_adapter_has_no_pool(self, mock_context):
        mock_context.storage_adapter = Mock(spec=[])  # no _pool
        result = await RetentionJob().run(mock_context)

        assert result.success is True
        assert result.items_processed == 0


# ── Dry-run mode ─────────────────────────────────────────────────────────

class TestRetentionJobDryRun:
    async def test_dry_run_returns_counts_without_deleting(self, mock_context):
        """dry_run=True uses SELECT COUNT(*) for all tables, never DELETE."""
        mock_row = AsyncMock()
        mock_row.fetchone = AsyncMock(return_value=(42,))
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_row)

        mock_adapter = Mock()
        mock_adapter._pool = _make_pool(mock_conn)
        mock_context.storage_adapter = mock_adapter

        job = RetentionJob(dry_run=True, cleanup_orphaned_vectors=False)
        result = await job.run(mock_context)

        assert result.success is True
        # 3 tables * 42 each = 126
        assert result.items_processed == 126
        assert result.metadata["dry_run"] is True
        assert result.metadata["evidence"] == 42
        assert result.metadata["digests"] == 42
        assert result.metadata["knowledge_graph"] == 42

        # Every SQL must be SELECT COUNT, not DELETE
        for call in mock_conn.execute.call_args_list:
            assert "SELECT COUNT" in call[0][0]
            assert "DELETE" not in call[0][0]

    async def test_dry_run_with_orphaned_vectors(self, mock_context):
        """dry_run counts orphaned vectors too."""
        mock_row = AsyncMock()
        mock_row.fetchone = AsyncMock(return_value=(10,))
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_row)

        mock_adapter = Mock()
        mock_adapter._pool = _make_pool(mock_conn)
        mock_context.storage_adapter = mock_adapter

        job = RetentionJob(dry_run=True, cleanup_orphaned_vectors=True)
        result = await job.run(mock_context)

        # 3 tables + orphaned_vectors, all 10
        assert result.items_processed == 40
        assert result.metadata["orphaned_vectors"] == 10


# ── DELETE mode ──────────────────────────────────────────────────────────

class TestRetentionJobDelete:
    async def test_deletes_from_all_three_tables(self, mock_context):
        """Without dry_run, executes DELETE against evidence, digests, knowledge_graph."""
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 5
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)

        mock_adapter = Mock()
        mock_adapter._pool = _make_pool(mock_conn)
        mock_context.storage_adapter = mock_adapter

        job = RetentionJob(cleanup_orphaned_vectors=False)
        result = await job.run(mock_context)

        assert result.success is True
        assert result.items_processed == 15  # 3 * 5
        assert result.metadata["evidence"] == 5
        assert result.metadata["digests"] == 5
        assert result.metadata["knowledge_graph"] == 5
        assert result.metadata["dry_run"] is False
        assert mock_conn.execute.call_count == 3

        # Verify DELETE with correct WHERE columns
        calls = [c[0][0] for c in mock_conn.execute.call_args_list]
        assert "DELETE FROM evidence WHERE occurred_at < %s" in calls[0]
        assert "DELETE FROM digests WHERE period_end < %s" in calls[1]
        assert "DELETE FROM knowledge_graph WHERE updated_at < %s" in calls[2]

    async def test_cleans_orphaned_vectors(self, mock_context):
        """cleanup_orphaned_vectors=True deletes orphaned embedding rows."""
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 3
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)

        mock_adapter = Mock()
        mock_adapter._pool = _make_pool(mock_conn)
        mock_context.storage_adapter = mock_adapter

        job = RetentionJob(cleanup_orphaned_vectors=True)
        result = await job.run(mock_context)

        # 3 tables + orphaned_vectors, all 3 each = 12
        assert result.items_processed == 12
        assert result.metadata["orphaned_vectors"] == 3
        # 4 total execute calls
        assert mock_conn.execute.call_count == 4
        last_sql = mock_conn.execute.call_args_list[3][0][0]
        assert "DELETE FROM embeddings" in last_sql
        assert "source_id NOT IN (SELECT id FROM evidence)" in last_sql

    async def test_skips_orphaned_vectors_when_disabled(self, mock_context):
        """cleanup_orphaned_vectors=False skips the embeddings cleanup."""
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 1
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)

        mock_adapter = Mock()
        mock_adapter._pool = _make_pool(mock_conn)
        mock_context.storage_adapter = mock_adapter

        job = RetentionJob(cleanup_orphaned_vectors=False)
        result = await job.run(mock_context)

        assert result.metadata["orphaned_vectors"] == 0
        assert mock_conn.execute.call_count == 3  # only the 3 table DELETEs


# ── Tenant filtering ─────────────────────────────────────────────────────

class TestRetentionJobTenantFiltering:
    async def test_tenant_clause_appended_to_sql(self, mock_context):
        """When tenants are specified, SQL includes AND tenant_id IN (...)."""
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 2
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)

        mock_adapter = Mock()
        mock_adapter._pool = _make_pool(mock_conn)
        mock_context.storage_adapter = mock_adapter

        job = RetentionJob(tenants=["t1", "t2"], cleanup_orphaned_vectors=False)
        result = await job.run(mock_context)

        assert result.success is True
        for call in mock_conn.execute.call_args_list:
            sql = call[0][0]
            assert "AND tenant_id IN (%s, %s)" in sql
            params = call[0][1]
            # First param is cutoff, then tenant IDs
            assert params[1] == "t1"
            assert params[2] == "t2"

    async def test_no_tenant_clause_when_empty(self, mock_context):
        """When tenants is empty, SQL has no tenant_id filter."""
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 0
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)

        mock_adapter = Mock()
        mock_adapter._pool = _make_pool(mock_conn)
        mock_context.storage_adapter = mock_adapter

        job = RetentionJob(cleanup_orphaned_vectors=False)
        await job.run(mock_context)

        for call in mock_conn.execute.call_args_list:
            sql = call[0][0]
            assert "tenant_id" not in sql


# ── Error handling ───────────────────────────────────────────────────────

class TestRetentionJobErrors:
    async def test_collects_per_table_errors(self, mock_context):
        """Errors on one table don't stop other tables from being processed."""
        call_count = 0

        async def failing_execute(sql, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("connection lost")
            mock_cursor = AsyncMock()
            mock_cursor.rowcount = 1
            return mock_cursor

        mock_conn = AsyncMock()
        mock_conn.execute = failing_execute

        mock_adapter = Mock()
        mock_adapter._pool = _make_pool(mock_conn)
        mock_context.storage_adapter = mock_adapter

        job = RetentionJob(cleanup_orphaned_vectors=False)
        result = await job.run(mock_context)

        assert result.success is True
        assert len(result.errors) == 1
        assert "evidence" in result.errors[0]
        # Other two tables still processed
        assert result.items_processed == 2
