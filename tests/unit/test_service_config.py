# ABOUTME: Tests for Pydantic Settings config loading in agentmem service.
# ABOUTME: Covers defaults, env var override, nested config, and extra-ignore behavior.
"""Tests for agentmem service configuration."""
from __future__ import annotations

import os

import pytest

from agentmem.service.config import (
    AdminConfig,
    AgentMemConfig,
    EmbeddingsConfig,
    StorageConfig,
    TenancyConfig,
    WorkersConfig,
)


class TestStorageConfig:
    def test_defaults(self):
        cfg = StorageConfig()
        assert cfg.backend == "postgres"
        assert cfg.dsn == "postgresql://localhost/agentmem"

    def test_override(self):
        cfg = StorageConfig(backend="sqlite", dsn="sqlite:///test.db")
        assert cfg.backend == "sqlite"
        assert cfg.dsn == "sqlite:///test.db"


class TestEmbeddingsConfig:
    def test_defaults(self):
        cfg = EmbeddingsConfig()
        assert cfg.backend == "ollama"
        assert cfg.url == "http://localhost:11434"
        assert cfg.model == "qwen3-embedding:8b"
        assert cfg.dimensions == 4096

    def test_override(self):
        cfg = EmbeddingsConfig(backend="openai", dimensions=1536)
        assert cfg.backend == "openai"
        assert cfg.dimensions == 1536


class TestTenancyConfig:
    def test_defaults(self):
        cfg = TenancyConfig()
        assert cfg.mode == "single"
        assert cfg.default_tenant == "default"

    def test_multi_tenant(self):
        cfg = TenancyConfig(mode="multi", default_tenant="acme")
        assert cfg.mode == "multi"
        assert cfg.default_tenant == "acme"


class TestWorkersConfig:
    def test_defaults(self):
        cfg = WorkersConfig()
        assert cfg.embed_reindex["trigger"] == "cron:0 2 * * *"
        assert cfg.embed_reindex["batch_size"] == 100
        assert cfg.digest["trigger"] == "cron:59 23 * * *"
        assert cfg.digest["types"] == ["daily", "weekly", "monthly"]
        assert cfg.retention["trigger"] == "cron:0 3 * * 0"
        assert cfg.retention["evidence_days"] == 180
        assert cfg.active_context["trigger"] == "continuous:pg_listen"

    def test_override(self):
        cfg = WorkersConfig(
            embed_reindex={"trigger": "manual", "batch_size": 50},
        )
        assert cfg.embed_reindex["trigger"] == "manual"
        assert cfg.embed_reindex["batch_size"] == 50


class TestAdminConfig:
    def test_defaults(self):
        cfg = AdminConfig()
        assert cfg.token == ""

    def test_with_token(self):
        cfg = AdminConfig(token="s3cr3t")
        assert cfg.token == "s3cr3t"


class TestAgentMemConfig:
    def test_defaults(self):
        cfg = AgentMemConfig()
        assert isinstance(cfg.storage, StorageConfig)
        assert isinstance(cfg.embeddings, EmbeddingsConfig)
        assert isinstance(cfg.tenancy, TenancyConfig)
        assert isinstance(cfg.workers, WorkersConfig)
        assert isinstance(cfg.admin, AdminConfig)

    def test_nested_override(self):
        cfg = AgentMemConfig(
            storage=StorageConfig(dsn="postgresql://prod:5432/mem"),
            admin=AdminConfig(token="prod-token"),
        )
        assert cfg.storage.dsn == "postgresql://prod:5432/mem"
        assert cfg.admin.token == "prod-token"

    def test_env_prefix(self):
        assert AgentMemConfig.model_config["env_prefix"] == "AGENTMEM__"

    def test_env_nested_delimiter(self):
        assert AgentMemConfig.model_config["env_nested_delimiter"] == "__"

    def test_extra_ignored(self):
        assert AgentMemConfig.model_config["extra"] == "ignore"

    def test_model_dump_roundtrip(self):
        cfg = AgentMemConfig()
        data = cfg.model_dump()
        assert "storage" in data
        assert "embeddings" in data
        assert "tenancy" in data
        assert "workers" in data
        assert "admin" in data
        assert data["storage"]["backend"] == "postgres"

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("AGENTMEM__STORAGE__DSN", "postgresql://envhost/envdb")
        cfg = AgentMemConfig()
        assert cfg.storage.dsn == "postgresql://envhost/envdb"
