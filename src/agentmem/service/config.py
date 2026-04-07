# ABOUTME: Pydantic Settings config for agentmem service.
# ABOUTME: Env vars or TOML file. Nested delimiter '__' for env var override.
"""Service configuration via Pydantic Settings."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageConfig(BaseSettings):
    backend: str = "postgres"
    dsn: str = "postgresql://localhost/agentmem"


class EmbeddingsConfig(BaseSettings):
    backend: str = "ollama"
    url: str = "http://localhost:11434"
    model: str = "qwen3-embedding:8b"
    dimensions: int = 4096


class TenancyConfig(BaseSettings):
    mode: str = "single"           # "single" | "multi"
    default_tenant: str = "default"


class WorkerJobConfig(BaseSettings):
    trigger: str = "on_demand"
    # Job-specific keys read dynamically from config; each job checks context.config


class WorkersConfig(BaseSettings):
    embed_reindex: dict = Field(default_factory=lambda: {"trigger": "cron:0 2 * * *", "batch_size": 100})
    digest: dict = Field(default_factory=lambda: {"trigger": "cron:59 23 * * *", "types": ["daily", "weekly", "monthly"]})
    retention: dict = Field(default_factory=lambda: {"trigger": "cron:0 3 * * 0", "evidence_days": 180})
    active_context: dict = Field(default_factory=lambda: {"trigger": "continuous:pg_listen"})


class AdminConfig(BaseSettings):
    token: str = ""  # empty = open (dev only); set for production


class AgentMemConfig(BaseSettings):
    """Root config. Load from environment or TOML file.

    Env var override uses nested delimiter '__':
      AGENTMEM__STORAGE__DSN=postgresql://...
      AGENTMEM__TENANCY__DEFAULT_TENANT=myagent
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENTMEM__",
        env_nested_delimiter="__",
        toml_file="agentmem.toml",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        from pydantic_settings import TomlConfigSettingsSource
        return (init_settings, env_settings, TomlConfigSettingsSource(settings_cls), file_secret_settings)

    storage: StorageConfig = Field(default_factory=StorageConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    tenancy: TenancyConfig = Field(default_factory=TenancyConfig)
    workers: WorkersConfig = Field(default_factory=WorkersConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
