# ABOUTME: Unit tests for CLI command structure and help output.
# ABOUTME: Verifies all am subcommands are registered and produce valid --help output.
"""Unit tests for CLI commands."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from agentmem.cli.main import app

runner = CliRunner()


def test_am_help():
    """am --help should list all subcommands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ingest", "retrieve", "facet", "graph", "digest", "admin", "workers"):
        assert cmd in result.output


def test_ingest_help():
    """am ingest --help should list evidence, facet, triplet."""
    result = runner.invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "evidence" in result.output
    assert "facet" in result.output
    assert "triplet" in result.output


def test_retrieve_help():
    """am retrieve --help should list evidence, semantic, context."""
    result = runner.invoke(app, ["retrieve", "--help"])
    assert result.exit_code == 0
    assert "evidence" in result.output
    assert "semantic" in result.output
    assert "context" in result.output


def test_facet_help():
    """am facet --help should list get, set, list, delete."""
    result = runner.invoke(app, ["facet", "--help"])
    assert result.exit_code == 0
    assert "get" in result.output
    assert "set" in result.output
    assert "list" in result.output
    assert "delete" in result.output


def test_graph_help():
    """am graph --help should list add, query."""
    result = runner.invoke(app, ["graph", "--help"])
    assert result.exit_code == 0
    assert "add" in result.output
    assert "query" in result.output


def test_digest_help():
    """am digest --help should list generate, list."""
    result = runner.invoke(app, ["digest", "--help"])
    assert result.exit_code == 0
    assert "generate" in result.output
    assert "list" in result.output


def test_admin_help():
    """am admin --help should list reindex, retention, stats, workers commands."""
    result = runner.invoke(app, ["admin", "--help"])
    assert result.exit_code == 0
    assert "reindex" in result.output
    assert "retention" in result.output
    assert "stats" in result.output


def test_workers_help():
    """am workers --help should list status, run."""
    result = runner.invoke(app, ["workers", "--help"])
    assert result.exit_code == 0
    assert "status" in result.output
    assert "run" in result.output


def test_ingest_evidence_requires_tenant():
    """am ingest evidence should fail without --tenant."""
    result = runner.invoke(app, ["ingest", "evidence"])
    assert result.exit_code != 0


def test_retrieve_evidence_requires_tenant():
    """am retrieve evidence should fail without --tenant."""
    result = runner.invoke(app, ["retrieve", "evidence"])
    assert result.exit_code != 0


def test_facet_get_requires_tenant():
    """am facet get should fail without --tenant."""
    result = runner.invoke(app, ["facet", "get"])
    assert result.exit_code != 0


def test_digest_generate_requires_tenant_type_date():
    """am digest generate should fail without required parameters."""
    result = runner.invoke(app, ["digest", "generate"])
    assert result.exit_code != 0
