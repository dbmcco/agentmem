# ABOUTME: CLI command tests using httpx mocking
# ABOUTME: Tests all CLI commands with mocked HTTP responses
"""CLI command tests."""
from __future__ import annotations

import json
from unittest.mock import Mock, patch

import httpx
import pytest
from typer.testing import CliRunner

from agentmem.cli.commands.admin import app as admin_app
from agentmem.cli.commands.digest import app as digest_app
from agentmem.cli.commands.facet import app as facet_app
from agentmem.cli.commands.graph import app as graph_app
from agentmem.cli.commands.ingest import app as ingest_app
from agentmem.cli.commands.retrieve import app as retrieve_app

runner = CliRunner()


class MockResponse:
    def __init__(self, json_data: dict, status_code: int = 200, text: str = ""):
        self._json_data = json_data
        self.status_code = status_code
        self.text = text or json.dumps(json_data)
        self.response = Mock()
        self.response.status_code = status_code
        self.response.text = self.text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("Error", request=Mock(), response=self.response)


@patch("httpx.post")
def test_ingest_evidence(mock_post):
    """Test evidence ingest command."""
    mock_post.return_value = MockResponse({"id": 123, "dedupe_key": "test_key", "deduplicated": False})

    result = runner.invoke(ingest_app, [
        "evidence",
        "--tenant", "test_tenant",
        "--type", "conversation.turn",
        "--content", "Test content",
        "--dedupe-key", "test_key",
        "--metadata", '{"test": "value"}'
    ])

    assert result.exit_code == 0
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/ingest/evidence")
    assert kwargs["json"]["tenant_id"] == "test_tenant"
    assert kwargs["json"]["event_type"] == "conversation.turn"
    assert kwargs["json"]["content"] == "Test content"


@patch("httpx.post")
def test_ingest_facet(mock_post):
    """Test facet ingest command."""
    mock_post.return_value = MockResponse({"key": "test_key", "value": "test_value"})

    result = runner.invoke(ingest_app, [
        "facet",
        "--tenant", "test_tenant",
        "test_key",
        "test_value",
        "--confidence", "0.9"
    ])

    assert result.exit_code == 0
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/ingest/facet")
    assert kwargs["json"]["tenant_id"] == "test_tenant"
    assert kwargs["json"]["key"] == "test_key"
    assert kwargs["json"]["value"] == "test_value"
    assert kwargs["json"]["confidence"] == 0.9


@patch("httpx.post")
def test_ingest_triplet(mock_post):
    """Test triplet ingest command."""
    mock_post.return_value = MockResponse({"subject": "user", "predicate": "likes", "object": "music"})

    result = runner.invoke(ingest_app, [
        "triplet",
        "--tenant", "test_tenant",
        "user",
        "likes",
        "music",
        "--confidence", "0.8"
    ])

    assert result.exit_code == 0
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/ingest/triplet")
    assert kwargs["json"]["tenant_id"] == "test_tenant"
    assert kwargs["json"]["subject"] == "user"
    assert kwargs["json"]["predicate"] == "likes"
    assert kwargs["json"]["object"] == "music"
    assert kwargs["json"]["confidence"] == 0.8


@patch("httpx.get")
def test_retrieve_evidence(mock_get):
    """Test evidence retrieval command."""
    mock_get.return_value = MockResponse([{"id": 123, "content": "Test evidence"}])

    result = runner.invoke(retrieve_app, [
        "evidence",
        "--tenant", "test_tenant",
        "--type", "conversation.turn",
        "--limit", "10"
    ])

    assert result.exit_code == 0
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0].endswith("/retrieve/evidence")
    assert kwargs["params"]["tenant_id"] == "test_tenant"
    assert kwargs["params"]["event_type"] == "conversation.turn"
    assert kwargs["params"]["limit"] == 10


@patch("httpx.get")
def test_retrieve_semantic(mock_get):
    """Test semantic search command."""
    mock_get.return_value = MockResponse([{"content": "Similar content", "score": 0.9}])

    result = runner.invoke(retrieve_app, [
        "semantic",
        "--tenant", "test_tenant",
        "--q", "test query",
        "--limit", "5"
    ])

    assert result.exit_code == 0
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0].endswith("/retrieve/semantic")
    assert kwargs["params"]["tenant_id"] == "test_tenant"
    assert kwargs["params"]["q"] == "test query"
    assert kwargs["params"]["limit"] == 5


@patch("httpx.get")
def test_retrieve_context(mock_get):
    """Test context retrieval command."""
    mock_get.return_value = MockResponse([{"section": "test", "content": "context"}])

    result = runner.invoke(retrieve_app, [
        "context",
        "--tenant", "test_tenant",
        "--max-age-seconds", "3600"
    ])

    assert result.exit_code == 0
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0].endswith("/retrieve/context")
    assert kwargs["params"]["tenant_id"] == "test_tenant"
    assert kwargs["params"]["max_age_seconds"] == 3600.0


@patch("httpx.get")
def test_facet_get(mock_get):
    """Test facet get command."""
    mock_get.return_value = MockResponse([{"key": "test_key", "value": "test_value"}])

    result = runner.invoke(facet_app, [
        "get",
        "--tenant", "test_tenant",
        "--key", "test_key"
    ])

    assert result.exit_code == 0
    mock_get.assert_called_once()


@patch("httpx.post")
def test_facet_set(mock_post):
    """Test facet set command."""
    mock_post.return_value = MockResponse({"key": "test_key", "value": "test_value"})

    result = runner.invoke(facet_app, [
        "set",
        "--tenant", "test_tenant",
        "--key", "test_key",
        "--value", "test_value"
    ])

    assert result.exit_code == 0
    mock_post.assert_called_once()


@patch("httpx.get")
def test_facet_list(mock_get):
    """Test facet list command."""
    mock_get.return_value = MockResponse([
        {"key": "key1", "value": "value1"},
        {"key": "key2", "value": "value2"}
    ])

    result = runner.invoke(facet_app, [
        "list",
        "--tenant", "test_tenant",
        "--prefix", "test"
    ])

    assert result.exit_code == 0
    mock_get.assert_called_once()


@patch("httpx.delete")
def test_facet_delete(mock_delete):
    """Test facet delete command."""
    mock_delete.return_value = MockResponse({"deleted": True})

    result = runner.invoke(facet_app, [
        "delete",
        "--tenant", "test_tenant",
        "--key", "test_key"
    ])

    assert result.exit_code == 0
    mock_delete.assert_called_once()


@patch("httpx.post")
def test_graph_add(mock_post):
    """Test graph add command."""
    mock_post.return_value = MockResponse({"subject": "user", "predicate": "likes", "object": "music"})

    result = runner.invoke(graph_app, [
        "add",
        "--tenant", "test_tenant",
        "--subject", "user",
        "--predicate", "likes",
        "--object", "music"
    ])

    assert result.exit_code == 0
    mock_post.assert_called_once()


@patch("httpx.get")
def test_graph_query(mock_get):
    """Test graph query command."""
    mock_get.return_value = MockResponse([{"subject": "user", "predicate": "likes", "object": "music"}])

    result = runner.invoke(graph_app, [
        "query",
        "--tenant", "test_tenant",
        "--subject", "user"
    ])

    assert result.exit_code == 0
    mock_get.assert_called_once()


@patch("httpx.post")
def test_digest_generate(mock_post):
    """Test digest generate command."""
    mock_post.return_value = MockResponse({"digest_id": 123, "type": "daily", "date": "2024-01-01"})

    result = runner.invoke(digest_app, [
        "generate",
        "--tenant", "test_tenant",
        "--type", "daily",
        "--date", "2024-01-01"
    ])

    assert result.exit_code == 0
    mock_post.assert_called_once()


@patch("httpx.get")
def test_digest_list(mock_get):
    """Test digest list command."""
    mock_get.return_value = MockResponse([{"digest_id": 123, "type": "daily"}])

    result = runner.invoke(digest_app, [
        "list",
        "--tenant", "test_tenant",
        "--type", "daily"
    ])

    assert result.exit_code == 0
    mock_get.assert_called_once()


@patch("httpx.post")
def test_admin_reindex(mock_post):
    """Test admin reindex command."""
    mock_post.return_value = MockResponse({"indexed_count": 1000})

    result = runner.invoke(admin_app, [
        "reindex",
        "--tenant", "test_tenant",
        "--dry-run"
    ])

    assert result.exit_code == 0
    mock_post.assert_called_once()


@patch("httpx.post")
def test_admin_retention(mock_post):
    """Test admin retention command."""
    mock_post.return_value = MockResponse({"deleted_count": 50})

    result = runner.invoke(admin_app, [
        "retention",
        "--tenant", "test_tenant",
        "--evidence-days", "90"
    ])

    assert result.exit_code == 0
    mock_post.assert_called_once()


@patch("httpx.get")
def test_admin_stats(mock_get):
    """Test admin stats command."""
    mock_get.return_value = MockResponse({"evidence_count": 1000, "facet_count": 500})

    result = runner.invoke(admin_app, [
        "stats",
        "--tenant", "test_tenant"
    ])

    assert result.exit_code == 0
    mock_get.assert_called_once()


@patch("httpx.get")
def test_workers_status(mock_get):
    """Test workers status command."""
    mock_get.return_value = MockResponse([{"job": "embed_reindex", "status": "idle"}])

    result = runner.invoke(admin_app, [
        "workers-status"
    ])

    assert result.exit_code == 0
    mock_get.assert_called_once()


@patch("httpx.post")
def test_workers_run(mock_post):
    """Test workers run command."""
    mock_post.return_value = MockResponse({"job": "embed_reindex", "started": True})

    result = runner.invoke(admin_app, [
        "workers-run",
        "embed_reindex"
    ])

    assert result.exit_code == 0
    mock_post.assert_called_once()


@patch("httpx.post")
def test_http_error_handling(mock_post):
    """Test HTTP error handling."""
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    mock_post.side_effect = httpx.HTTPStatusError("Error", request=Mock(), response=mock_response)

    result = runner.invoke(ingest_app, [
        "evidence",
        "--tenant", "test_tenant",
        "--type", "test",
        "--content", "test"
    ])

    assert result.exit_code == 1
    assert "Error 400: Bad Request" in result.stderr


def test_invalid_metadata_json():
    """Test invalid JSON metadata handling."""
    result = runner.invoke(ingest_app, [
        "evidence",
        "--tenant", "test_tenant",
        "--type", "test",
        "--content", "test",
        "--metadata", "invalid_json"
    ])

    assert result.exit_code == 1
    assert "Invalid metadata JSON" in result.stderr