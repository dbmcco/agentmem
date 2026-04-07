# ABOUTME: Tests for admin API routes (service-level test location).
# ABOUTME: Test reindex, retention, stats endpoints with proper JobResult returns.
"""Tests for admin API routes."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentmem.core.models import JobResult
from agentmem.service.api.admin import router


@pytest.fixture
def mock_coordinator():
    return AsyncMock()


@pytest.fixture
def mock_storage_adapter():
    return AsyncMock()


@pytest.fixture
def mock_config():
    config = Mock()
    config.admin.token = ""
    return config


@pytest.fixture
def test_app(mock_coordinator, mock_storage_adapter, mock_config):
    app = FastAPI()
    app.include_router(router)
    app.state.coordinator = mock_coordinator
    app.state.storage_adapter = mock_storage_adapter
    app.state.config = mock_config
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


class TestAdminReindex:

    def test_reindex_triggers_reindex_job(self, client, mock_coordinator):
        mock_coordinator.run_now.return_value = JobResult(
            success=True, items_processed=150,
        )
        response = client.post("/admin/reindex?tenant_id=test-tenant&dry_run=false")

        assert response.status_code == 200
        data = response.json()
        assert data["items_indexed"] == 150
        assert data["dry_run"] is False
        mock_coordinator.run_now.assert_called_once()


class TestAdminRetention:

    def test_retention_triggers_retention_job(self, client, mock_coordinator):
        mock_coordinator.run_now.return_value = JobResult(
            success=True, items_processed=42,
        )
        response = client.post("/admin/retention?tenant_id=test-tenant&evidence_days=90&dry_run=true")

        assert response.status_code == 200
        data = response.json()
        assert data["items_deleted"] == 42
        assert data["dry_run"] is True
        mock_coordinator.run_now.assert_called_once()


class TestAdminStats:

    def test_stats_returns_counts(self, client, mock_storage_adapter):
        mock_storage_adapter.count_evidence.return_value = 100
        mock_storage_adapter.count_facets.return_value = 50
        mock_storage_adapter.count_triplets.return_value = 25
        mock_storage_adapter.count_digests.return_value = 10
        mock_storage_adapter.count_vectors.return_value = 75

        response = client.get("/admin/stats/test-tenant")

        assert response.status_code == 200
        data = response.json()
        assert data["evidence_count"] == 100
        assert data["facet_count"] == 50
        assert data["triplet_count"] == 25
        assert data["digest_count"] == 10
        assert data["vector_count"] == 75
        assert data["tenant_id"] == "test-tenant"
