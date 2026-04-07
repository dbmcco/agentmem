# ABOUTME: Tests for ingest API routes per wg-contract.
# ABOUTME: Covers evidence dedup, facet upsert, triplet add, status, and validation.
"""Tests for ingest API routes."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentmem.core.models import FacetRecord, InsertResult, Triplet
from agentmem.service.api.ingest import router as ingest_router


@pytest.fixture
def mock_evidence_ledger():
    return AsyncMock()


@pytest.fixture
def mock_facet_store():
    return AsyncMock()


@pytest.fixture
def mock_graph_store():
    return AsyncMock()


def _make_app(evidence_ledger, facet_store, graph_store):
    app = FastAPI()
    app.include_router(ingest_router)
    app.state.evidence_ledger = evidence_ledger
    app.state.facet_store = facet_store
    app.state.graph_store = graph_store
    return app


@pytest.fixture
def client(mock_evidence_ledger, mock_facet_store, mock_graph_store):
    app = _make_app(mock_evidence_ledger, mock_facet_store, mock_graph_store)
    return TestClient(app)


# ── Evidence ────────────────────────────────────────────────────────────────


class TestIngestEvidence:

    def test_first_evidence_returns_not_deduplicated(
        self, client, mock_evidence_ledger
    ):
        mock_evidence_ledger.ingest.return_value = InsertResult(
            id=1, dedupe_key="dk-1", deduplicated=False
        )

        response = client.post(
            "/ingest/evidence",
            json={
                "tenant_id": "t1",
                "event_type": "message",
                "content": "hello world",
                "occurred_at": "2026-04-07T12:00:00Z",
                "source_event_id": "src-1",
                "dedupe_key": "dk-1",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["dedupe_key"] == "dk-1"
        assert data["deduplicated"] is False

    def test_duplicate_evidence_returns_deduplicated(
        self, client, mock_evidence_ledger
    ):
        mock_evidence_ledger.ingest.return_value = InsertResult(
            id=None, dedupe_key="dk-1", deduplicated=True
        )

        response = client.post(
            "/ingest/evidence",
            json={
                "tenant_id": "t1",
                "event_type": "message",
                "content": "hello world",
                "occurred_at": "2026-04-07T12:00:00Z",
                "source_event_id": "src-1",
                "dedupe_key": "dk-1",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] is None
        assert data["deduplicated"] is True


# ── Facet ───────────────────────────────────────────────────────────────────


class TestIngestFacet:

    def test_facet_returns_correct_fields(self, client, mock_facet_store):
        mock_facet_store.set.return_value = FacetRecord(
            id=10,
            tenant_id="t1",
            key="user.name",
            value="Alice",
            confidence=0.95,
            layer="identity",
        )

        response = client.post(
            "/ingest/facet",
            json={
                "tenant_id": "t1",
                "key": "user.name",
                "value": "Alice",
                "confidence": 0.95,
                "layer": "identity",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 10
        assert data["tenant_id"] == "t1"
        assert data["key"] == "user.name"
        assert data["value"] == "Alice"
        assert data["confidence"] == 0.95
        assert data["layer"] == "identity"


# ── Triplet ─────────────────────────────────────────────────────────────────


class TestIngestTriplet:

    def test_triplet_returns_correct_fields(self, client, mock_graph_store):
        mock_graph_store.add.return_value = Triplet(
            id=5,
            tenant_id="t1",
            subject="Alice",
            predicate="works_on",
            object="agentmem",
            confidence=1.0,
            source="manual",
        )

        response = client.post(
            "/ingest/triplet",
            json={
                "tenant_id": "t1",
                "subject": "Alice",
                "predicate": "works_on",
                "object": "agentmem",
                "confidence": 1.0,
                "source": "manual",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 5
        assert data["tenant_id"] == "t1"
        assert data["subject"] == "Alice"
        assert data["predicate"] == "works_on"
        assert data["object"] == "agentmem"
        assert data["confidence"] == 1.0
        assert data["source"] == "manual"


# ── Status ──────────────────────────────────────────────────────────────────


class TestIngestStatus:

    def test_status_returns_ready(self, client):
        response = client.get("/ingest/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["surface"] == "ingest"


# ── Validation ──────────────────────────────────────────────────────────────


class TestIngestValidation:

    def test_missing_required_field_returns_422(self, client):
        response = client.post(
            "/ingest/evidence",
            json={
                "tenant_id": "t1",
                # missing event_type, content, occurred_at, source_event_id, dedupe_key
            },
        )
        assert response.status_code == 422
