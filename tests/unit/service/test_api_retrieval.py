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
def mock_digest_engine():
    return AsyncMock()


@pytest.fixture
def mock_active_context_store():
    return AsyncMock()


@pytest.fixture
def mock_embedding_service():
    service = AsyncMock()
    service.search.return_value = []  # Default empty results
    return service


@pytest.fixture
def test_app(mock_evidence_ledger, mock_facet_store, mock_graph_store,
             mock_digest_engine, mock_active_context_store, mock_embedding_service):
    app = FastAPI()
    app.include_router(router)

    # Mock app.state with the services using correct attribute names
    app.state.evidence_ledger = mock_evidence_ledger
    app.state.facet_store = mock_facet_store
    app.state.graph_store = mock_graph_store
    app.state.digest_engine = mock_digest_engine
    app.state.active_context_store = mock_active_context_store
    app.state.embedding_service = mock_embedding_service

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

    async def test_retrieve_semantic_returns_vector_results(self, client, mock_embedding_service):
        # Given
        vector_results = [
            VectorResult(
                source_table="evidence", source_id=123, tenant_id="test-tenant",
                content="matching content", score=0.95
            )
        ]
        mock_embedding_service.search.return_value = vector_results

        # When
        response = client.get("/retrieve/semantic?tenant_id=test-tenant&query=search%20term&limit=5")

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1
        assert response_data[0]["source_table"] == "evidence"
        assert response_data[0]["source_id"] == 123
        assert response_data[0]["score"] == 0.95

        # Verify embedding_service.search called with correct parameters
        mock_embedding_service.search.assert_called_once()
        call_args = mock_embedding_service.search.call_args
        query = call_args[0][0]
        filters = call_args[0][1]
        assert query == "search term"
        assert isinstance(filters, VectorFilters)
        assert filters.tenant_id == "test-tenant"
        assert filters.limit == 5

    async def test_retrieve_semantic_with_extra_tenants(self, client, mock_embedding_service):
        # Given
        vector_results = [
            VectorResult(
                source_table="evidence", source_id=123, tenant_id="test-tenant",
                content="matching content", score=0.95
            )
        ]
        mock_embedding_service.search.return_value = vector_results

        # When
        response = client.get("/retrieve/semantic?tenant_id=test-tenant&query=search%20term&extra_tenants=tenant2,tenant3")

        # Then
        assert response.status_code == 200

        # Verify embedding_service.search called with correct parameters including extra_tenant_ids
        mock_embedding_service.search.assert_called_once()
        call_args = mock_embedding_service.search.call_args
        query = call_args[0][0]
        filters = call_args[0][1]
        assert query == "search term"
        assert isinstance(filters, VectorFilters)
        assert filters.tenant_id == "test-tenant"
        assert filters.extra_tenant_ids == ["tenant2", "tenant3"]


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

    async def test_retrieve_facets_with_extra_tenants(self, client, mock_facet_store):
        # Given
        facet_records = [
            FacetRecord(
                id=456, tenant_id="test-tenant", key="user_role", value="admin",
                confidence=0.9, layer="searchable"
            ),
            FacetRecord(
                id=457, tenant_id="tenant2", key="org_type", value="enterprise",
                confidence=0.95, layer="searchable"
            )
        ]
        mock_facet_store.list_multi.return_value = facet_records

        # When
        response = client.get("/retrieve/facets?tenant_id=test-tenant&extra_tenants=tenant2,tenant3&prefix=user_")

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2

        # Verify facet_store.list_multi called with correct parameters
        mock_facet_store.list_multi.assert_called_once_with(
            ["test-tenant", "tenant2", "tenant3"], prefix="user_", layer=None
        )


class TestRetrieveDigests:

    async def test_retrieve_digests_returns_digest_list(self, client, mock_digest_engine):
        # Given
        now = datetime.now(timezone.utc)
        digest_records = [
            Digest(
                id=789, tenant_id="test-tenant", digest_type="daily",
                period_start=now, period_end=now, content="Daily summary"
            )
        ]
        mock_digest_engine.list.return_value = digest_records

        # When
        response = client.get("/retrieve/digests?tenant_id=test-tenant&type=daily&limit=20")

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1
        assert response_data[0]["id"] == 789
        assert response_data[0]["digest_type"] == "daily"
        assert response_data[0]["content"] == "Daily summary"

        # Verify digest_engine.list called with correct filters
        mock_digest_engine.list.assert_called_once()
        filters = mock_digest_engine.list.call_args[0][0]
        assert isinstance(filters, DigestFilters)
        assert filters.tenant_id == "test-tenant"
        assert filters.digest_type == "daily"
        assert filters.limit == 20


class TestRetrieveContext:

    async def test_retrieve_context_returns_context_sections(self, client, mock_active_context_store):
        # Given
        now = datetime.now(timezone.utc)
        context_sections = [
            ContextSection(
                tenant_id="test-tenant", section="user_profile",
                content="Profile data", updated_at=now
            )
        ]
        mock_active_context_store.get_all.return_value = context_sections

        # When
        response = client.get("/retrieve/context?tenant_id=test-tenant&max_age_seconds=3600")

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1
        assert response_data[0]["section"] == "user_profile"
        assert response_data[0]["content"] == "Profile data"

        # Verify active_context_store.get_all called
        mock_active_context_store.get_all.assert_called_once_with("test-tenant", 3600.0)


class TestRetrieveTurns:

    async def test_retrieve_turns_returns_turn_list(self, client, mock_evidence_ledger):
        # Given
        now = datetime.now(timezone.utc)
        evidence_records = [
            EvidenceRecord(
                id=1, tenant_id="test-tenant", event_type="conversation.turn",
                content="User said: Hello\nAgent: Hi there!",
                occurred_at=now, source_event_id="turn-1",
                dedupe_key="turn-key-1",
                metadata={"conversation_id": "conv-123", "user_message": "Hello", "agent_response": "Hi there!"},
                channel_id="channel-1"
            )
        ]
        mock_evidence_ledger.query.return_value = evidence_records

        # When
        response = client.get("/retrieve/turns?tenant_id=test-tenant&conversation_id=conv-123&limit=12")

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1
        assert response_data[0]["turn_id"] == "turn-1"
        assert response_data[0]["content"] == "User said: Hello\nAgent: Hi there!"
        assert response_data[0]["user_message"] == "Hello"
        assert response_data[0]["agent_response"] == "Hi there!"
        assert response_data[0]["conversation_id"] == "conv-123"
        assert response_data[0]["channel_id"] == "channel-1"
        assert response_data[0]["source_event_id"] == "turn-1"
        assert response_data[0]["origin_platform"] is None

        # Verify evidence_ledger.query called with correct filters
        mock_evidence_ledger.query.assert_called_once()
        filters = mock_evidence_ledger.query.call_args[0][0]
        assert isinstance(filters, EvidenceFilters)
        assert filters.tenant_id == "test-tenant"
        assert filters.event_type == "conversation.turn"
        assert filters.limit == 12
        assert filters.metadata_contains == {"conversation_id": "conv-123"}

    async def test_retrieve_turns_without_conversation_filter(self, client, mock_evidence_ledger):
        # Given
        now = datetime.now(timezone.utc)
        evidence_records = [
            EvidenceRecord(
                id=2, tenant_id="test-tenant", event_type="conversation.turn",
                content="User said: How are you?\nAgent: I'm doing well, thanks!",
                occurred_at=now, source_event_id="turn-2",
                dedupe_key="turn-key-2",
                metadata={"conversation_id": "conv-456"},
                channel_id="channel-2"
            )
        ]
        mock_evidence_ledger.query.return_value = evidence_records

        # When
        response = client.get("/retrieve/turns?tenant_id=test-tenant&channel_id=channel-2")

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1
        assert response_data[0]["conversation_id"] == "conv-456"
        assert response_data[0]["channel_id"] == "channel-2"

        # Verify evidence_ledger.query called with correct filters
        mock_evidence_ledger.query.assert_called_once()
        filters = mock_evidence_ledger.query.call_args[0][0]
        assert filters.tenant_id == "test-tenant"
        assert filters.event_type == "conversation.turn"
        assert filters.channel_id == "channel-2"
        assert filters.metadata_contains is None

    async def test_retrieve_turns_with_fallback_parsing(self, client, mock_evidence_ledger):
        # Given - test the fallback parsing when metadata doesn't have user_message/agent_response
        now = datetime.now(timezone.utc)
        evidence_records = [
            EvidenceRecord(
                id=3, tenant_id="test-tenant", event_type="conversation.turn",
                content="User said: What's the weather?\nAgent: I don't have current weather data.",
                occurred_at=now, source_event_id="turn-3",
                dedupe_key="turn-key-3",
                metadata={"conversation_id": "conv-789"},  # No user_message/agent_response in metadata
                channel_id="channel-3"
            )
        ]
        mock_evidence_ledger.query.return_value = evidence_records

        # When
        response = client.get("/retrieve/turns?tenant_id=test-tenant")

        # Then
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 1
        assert response_data[0]["user_message"] == "What's the weather?"
        assert response_data[0]["agent_response"] == "I don't have current weather data."