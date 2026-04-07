# ABOUTME: Tests for admin and worker API routes per wg-contract.
# ABOUTME: Covers reindex dry_run, token auth, workers/status, admin/status.
"""Tests for admin API routes."""
from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentmem.core.models import JobResult, JobStatus
from agentmem.service.api.admin import router as admin_router
from agentmem.service.api.admin import workers_router


@pytest.fixture
def mock_coordinator():
    return AsyncMock()


@pytest.fixture
def mock_storage_adapter():
    return AsyncMock()


@pytest.fixture
def _config_open():
    """Config with no admin token (open/dev mode)."""
    config = Mock()
    config.admin.token = ""
    return config


@pytest.fixture
def _config_token():
    """Config with admin token set."""
    config = Mock()
    config.admin.token = "secret-token-123"
    return config


def _make_app(config, coordinator, storage_adapter):
    app = FastAPI()
    app.include_router(admin_router)
    app.include_router(workers_router)
    app.state.config = config
    app.state.coordinator = coordinator
    app.state.storage_adapter = storage_adapter
    return app


@pytest.fixture
def client_open(_config_open, mock_coordinator, mock_storage_adapter):
    app = _make_app(_config_open, mock_coordinator, mock_storage_adapter)
    return TestClient(app)


@pytest.fixture
def client_token(_config_token, mock_coordinator, mock_storage_adapter):
    app = _make_app(_config_token, mock_coordinator, mock_storage_adapter)
    return TestClient(app)


# ── Admin reindex ────────────────────────────────────────────────────────────


class TestAdminReindex:

    def test_reindex_dry_run_returns_candidate_counts(self, client_open, mock_coordinator):
        mock_coordinator.run_now.return_value = JobResult(
            success=True, items_processed=42,
        )
        response = client_open.post("/admin/reindex?dry_run=true")

        assert response.status_code == 200
        data = response.json()
        assert data["items_indexed"] == 42
        assert data["dry_run"] is True

    def test_reindex_with_tenant(self, client_open, mock_coordinator):
        mock_coordinator.run_now.return_value = JobResult(
            success=True, items_processed=10,
        )
        response = client_open.post("/admin/reindex?tenant_id=t1&dry_run=false")

        assert response.status_code == 200
        assert response.json()["items_indexed"] == 10
        assert response.json()["dry_run"] is False


# ── Admin retention ──────────────────────────────────────────────────────────


class TestAdminRetention:

    def test_retention_returns_deleted_count(self, client_open, mock_coordinator):
        mock_coordinator.run_now.return_value = JobResult(
            success=True, items_processed=7,
        )
        response = client_open.post("/admin/retention?dry_run=true")

        assert response.status_code == 200
        data = response.json()
        assert data["items_deleted"] == 7
        assert data["dry_run"] is True


# ── Admin stats ──────────────────────────────────────────────────────────────


class TestAdminStats:

    def test_stats_returns_counts_for_tenant(self, client_open, mock_storage_adapter):
        mock_storage_adapter.count_evidence.return_value = 100
        mock_storage_adapter.count_facets.return_value = 50
        mock_storage_adapter.count_triplets.return_value = 25
        mock_storage_adapter.count_digests.return_value = 10
        mock_storage_adapter.count_vectors.return_value = 75

        response = client_open.get("/admin/stats/test-tenant")

        assert response.status_code == 200
        data = response.json()
        assert data["evidence_count"] == 100
        assert data["facet_count"] == 50
        assert data["triplet_count"] == 25
        assert data["digest_count"] == 10
        assert data["vector_count"] == 75
        assert data["tenant_id"] == "test-tenant"


# ── Admin status ─────────────────────────────────────────────────────────────


class TestAdminStatus:

    def test_status_open_mode(self, client_open):
        response = client_open.get("/admin/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["auth"] == "open"

    def test_status_token_mode(self, client_token):
        response = client_token.get("/admin/status")
        assert response.status_code == 200
        assert response.json()["auth"] == "token"


# ── Token auth ───────────────────────────────────────────────────────────────


class TestTokenAuth:

    def test_token_required_when_configured(self, client_token, mock_coordinator):
        """Without the correct header, 401 is returned."""
        response = client_token.post("/admin/reindex?dry_run=true")
        assert response.status_code == 401

    def test_wrong_token_rejected(self, client_token, mock_coordinator):
        response = client_token.post(
            "/admin/reindex?dry_run=true",
            headers={"x-agentmem-admin-token": "wrong"},
        )
        assert response.status_code == 401

    def test_correct_token_accepted(self, client_token, mock_coordinator):
        mock_coordinator.run_now.return_value = JobResult(
            success=True, items_processed=0,
        )
        response = client_token.post(
            "/admin/reindex?dry_run=true",
            headers={"x-agentmem-admin-token": "secret-token-123"},
        )
        assert response.status_code == 200


# ── Workers status ───────────────────────────────────────────────────────────


class TestWorkersStatus:

    def test_workers_status_returns_list(self, client_open, mock_coordinator):
        mock_coordinator.status.return_value = [
            JobStatus(
                name="embed_reindex",
                trigger_type="cron",
                last_run=None,
                last_result=None,
                error_count=0,
                heartbeat_age_seconds=None,
                state="idle",
            ),
        ]
        response = client_open.get("/workers/status")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "embed_reindex"
        assert data[0]["state"] == "idle"


# ── Workers run ──────────────────────────────────────────────────────────────


class TestWorkersRun:

    def test_workers_run_triggers_job(self, client_open, mock_coordinator):
        mock_coordinator.run_now.return_value = JobResult(
            success=True, items_processed=5,
        )
        response = client_open.post("/workers/run/embed_reindex")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["items_processed"] == 5
