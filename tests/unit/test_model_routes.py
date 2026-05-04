# ABOUTME: Tests for the central Paia model route resolver used by agentmem.
# ABOUTME: Verifies agentmem.ollama_embedding resolves to the expected concrete model.
"""Tests for ``agentmem.model_routes`` registry resolution."""
from __future__ import annotations

import pytest

from agentmem.model_routes import (
    OLLAMA_EMBEDDING_ROUTE_ID,
    ModelRouteError,
    clear_route_cache,
    model_for_route,
    resolve_route,
)


@pytest.fixture(autouse=True)
def _reset_route_cache():
    clear_route_cache()
    yield
    clear_route_cache()


class TestOllamaEmbeddingRoute:
    def test_route_id_constant(self):
        assert OLLAMA_EMBEDDING_ROUTE_ID == "agentmem.ollama_embedding"

    def test_resolves_to_qwen3_embedding(self):
        route = resolve_route(OLLAMA_EMBEDDING_ROUTE_ID)
        assert route.model == "qwen3-embedding:8b"
        assert route.provider == "ollama"
        assert route.surface == "ollama"
        assert route.owner == "agentmem"

    def test_model_for_route_helper(self):
        assert model_for_route(OLLAMA_EMBEDDING_ROUTE_ID) == "qwen3-embedding:8b"

    def test_unknown_route_raises(self):
        with pytest.raises(ModelRouteError):
            resolve_route("agentmem.does_not_exist")

    def test_blank_route_id_raises(self):
        with pytest.raises(ModelRouteError):
            resolve_route("   ")

    def test_explicit_registry_path_via_env(self, monkeypatch, tmp_path):
        registry = tmp_path / "registry.toml"
        registry.write_text(
            "\n".join(
                [
                    '[model_routes."agentmem.ollama_embedding"]',
                    'owner = "agentmem"',
                    'surface = "ollama"',
                    'provider = "ollama"',
                    'model = "stub-model:test"',
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("PAIA_MODEL_ROUTE_REGISTRY_PATH", str(registry))
        clear_route_cache()
        assert model_for_route(OLLAMA_EMBEDDING_ROUTE_ID) == "stub-model:test"
