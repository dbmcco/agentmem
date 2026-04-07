# ABOUTME: Tests for retrieval API routes.
# ABOUTME: Test evidence, semantic, facets, graph, digests, and context retrieval endpoints.

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from agentmem.core.models import (
    EvidenceRecord, FacetRecord, Triplet, Digest, ContextSection,
    VectorResult, EvidenceFilters, VectorFilters, DigestFilters
)
from agentmem.service.api.retrieval import router


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
def mock_vector_store():
    return AsyncMock()


@pytest.fixture
def mock_digest_service():
    return AsyncMock()


@pytest.fixture
def mock_context_service():
    return AsyncMock()


@pytest.fixture
def mock_embedding_adapter():
    adapter = AsyncMock()
    adapter.model_id = "test-model"
    adapter.embed.return_value = [0.1, 0.2, 0.3]  # Mock embedding vector
    return adapter


@pytest.fixture
def test_app(mock_evidence_ledger, mock_facet_store, mock_graph_store, mock_vector_store,
             mock_digest_service, mock_context_service, mock_embedding_adapter):
    app = FastAPI()
    app.include_router(router)

    # Mock app.state with the services
    app.state.evidence_ledger = mock_evidence_ledger
    app.state.facet_store = mock_facet_store
    app.state.graph_store = mock_graph_store
    app.state.vector_store = mock_vector_store
    app.state.digest_service = mock_digest_service
    app.state.context_service = mock_context_service
    app.state.embedding_adapter = mock_embedding_adapter

    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


class TestRetrieveEvidence:

    async def test_retrieve_evidence_returns_evidence_list(self, client, mock_evidence_ledger):
        # Given
        now = datetime.now(timezone.utc)
        evidence_records = [
            EvidenceRecord(
                id=1, tenant_id="test-tenant", event_type="user_action",
                content="User clicked", occurred_at=now, source_event_id="evt-1",
                dedupe_key="key-1", metadata={"test": "data"}, channel_id="channel-1"
            )
        ]
        mock_evidence_ledger.query.return_value = evidence_records

        # When
        response = client.get("/retrieve/evidence?tenant_id=test-tenant&event_type=user_action&limit=10")

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1
        assert response_data[0]["id"] == 1
        assert response_data[0]["tenant_id"] == "test-tenant"
        assert response_data[0]["event_type"] == "user_action"

        # Verify evidence_ledger.query called with correct filters
        mock_evidence_ledger.query.assert_called_once()
        filters = mock_evidence_ledger.query.call_args[0][0]
        assert isinstance(filters, EvidenceFilters)
        assert filters.tenant_id == "test-tenant"
        assert filters.event_type == "user_action"
        assert filters.limit == 10


class TestRetrieveSemantic:

    async def test_retrieve_semantic_returns_vector_results(self, client, mock_embedding_adapter, mock_vector_store):
        # Given
        mock_embedding_adapter.embed.return_value = [0.1, 0.2, 0.3]
        vector_results = [
            VectorResult(
                source_table="evidence", source_id=123, tenant_id="test-tenant",
                content="matching content", score=0.95
            )
        ]
        mock_vector_store.search.return_value = vector_results

        # When
        response = client.get("/retrieve/semantic?tenant_id=test-tenant&query=search%20term&limit=5")

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1
        assert response_data[0]["source_table"] == "evidence"
        assert response_data[0]["source_id"] == 123
        assert response_data[0]["score"] == 0.95

        # Verify embedding adapter called to encode query
        mock_embedding_adapter.embed.assert_called_once_with("search term")

        # Verify vector store search called
        mock_vector_store.search.assert_called_once()
        call_args = mock_vector_store.search.call_args
        query_vector = call_args[0][0]
        filters = call_args[0][1]
        assert query_vector == [0.1, 0.2, 0.3]
        assert isinstance(filters, VectorFilters)
        assert filters.tenant_id == "test-tenant"
        assert filters.limit == 5


class TestRetrieveFacets:

    async def test_retrieve_facets_returns_facet_list(self, client, mock_facet_store):
        # Given
        facet_records = [
            FacetRecord(
                id=456, tenant_id="test-tenant", key="user_role", value="admin",
                confidence=0.9, layer="searchable"
            )
        ]
        mock_facet_store.list.return_value = facet_records

        # When
        response = client.get("/retrieve/facets?tenant_id=test-tenant&prefix=user_&layer=searchable")

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1
        assert response_data[0]["key"] == "user_role"
        assert response_data[0]["value"] == "admin"
        assert response_data[0]["layer"] == "searchable"

        # Verify facet_store.list called
        mock_facet_store.list.assert_called_once_with("test-tenant", "user_", "searchable")


class TestRetrieveContext:

    async def test_retrieve_context_returns_context_sections(self, client, mock_context_service):
        # Given
        now = datetime.now(timezone.utc)
        context_sections = [
            ContextSection(
                tenant_id="test-tenant", section="user_profile",
                content="Profile data", updated_at=now
            )
        ]
        mock_context_service.get_all.return_value = context_sections

        # When
        response = client.get("/retrieve/context?tenant_id=test-tenant&max_age_seconds=3600")

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1
        assert response_data[0]["section"] == "user_profile"
        assert response_data[0]["content"] == "Profile data"

        # Verify context_service.get_all called
        mock_context_service.get_all.assert_called_once_with("test-tenant", 3600.0)