# ABOUTME: Tests for ingest API routes.
# ABOUTME: Test evidence, facet, and triplet ingestion endpoints with proper error handling.

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from agentmem.core.models import EvidenceRecord, InsertResult, FacetRecord, Triplet
from agentmem.service.api.ingest import router, IngestEvidenceRequest, IngestFacetRequest, IngestTripletRequest


@pytest.fixture
def mock_evidence_ledger():
    return AsyncMock()


@pytest.fixture
def mock_facet_store():
    return AsyncMock()


@pytest.fixture
def mock_graph_store():
    return AsyncMock()


@pytest.fixture
def mock_embedding_adapter():
    adapter = AsyncMock()
    adapter.model_id = "test-model"
    return adapter


@pytest.fixture
def test_app(mock_evidence_ledger, mock_facet_store, mock_graph_store, mock_embedding_adapter):
    app = FastAPI()
    app.include_router(router)

    # Mock app.state with the services
    app.state.evidence_ledger = mock_evidence_ledger
    app.state.facet_store = mock_facet_store
    app.state.graph_store = mock_graph_store
    app.state.embedding_adapter = mock_embedding_adapter

    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


class TestIngestEvidence:

    async def test_ingest_evidence_returns_insert_result(self, client, mock_evidence_ledger):
        # Given
        request_data = {
            "tenant_id": "test-tenant",
            "event_type": "user_action",
            "content": "User clicked button",
            "occurred_at": "2023-01-01T00:00:00Z",
            "source_event_id": "evt-123",
            "dedupe_key": "dedupe-456"
        }

        expected_result = InsertResult(id=123, dedupe_key="dedupe-456", deduplicated=False)
        mock_evidence_ledger.ingest.return_value = expected_result

        # When
        response = client.post("/ingest/evidence", json=request_data)

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["id"] == 123
        assert response_data["dedupe_key"] == "dedupe-456"
        assert response_data["deduplicated"] == False

        # Verify evidence_ledger.ingest was called with correct EvidenceRecord
        mock_evidence_ledger.ingest.assert_called_once()
        call_args = mock_evidence_ledger.ingest.call_args[0][0]
        assert isinstance(call_args, EvidenceRecord)
        assert call_args.tenant_id == "test-tenant"
        assert call_args.event_type == "user_action"
        assert call_args.content == "User clicked button"


class TestIngestFacet:

    async def test_ingest_facet_returns_saved_record(self, client, mock_facet_store):
        # Given
        request_data = {
            "tenant_id": "test-tenant",
            "key": "user_role",
            "value": "admin",
            "confidence": 0.9,
            "layer": "searchable"
        }

        expected_result = FacetRecord(
            id=456, tenant_id="test-tenant", key="user_role",
            value="admin", confidence=0.9, layer="searchable"
        )
        mock_facet_store.set.return_value = expected_result

        # When
        response = client.post("/ingest/facet", json=request_data)

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["id"] == 456
        assert response_data["key"] == "user_role"
        assert response_data["value"] == "admin"

        # Verify facet_store.set was called
        mock_facet_store.set.assert_called_once()
        call_args = mock_facet_store.set.call_args[0][0]
        assert isinstance(call_args, FacetRecord)
        assert call_args.tenant_id == "test-tenant"
        assert call_args.key == "user_role"


class TestIngestTriplet:

    async def test_ingest_triplet_returns_saved_record(self, client, mock_graph_store):
        # Given
        request_data = {
            "tenant_id": "test-tenant",
            "subject": "user:123",
            "predicate": "hasRole",
            "object": "admin",
            "confidence": 0.95
        }

        expected_result = Triplet(
            id=789, tenant_id="test-tenant", subject="user:123",
            predicate="hasRole", object="admin", confidence=0.95
        )
        mock_graph_store.add.return_value = expected_result

        # When
        response = client.post("/ingest/triplet", json=request_data)

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["id"] == 789
        assert response_data["subject"] == "user:123"
        assert response_data["predicate"] == "hasRole"
        assert response_data["object"] == "admin"

        # Verify graph_store.add was called
        mock_graph_store.add.assert_called_once()
        call_args = mock_graph_store.add.call_args[0][0]
        assert isinstance(call_args, Triplet)
        assert call_args.tenant_id == "test-tenant"
        assert call_args.subject == "user:123"