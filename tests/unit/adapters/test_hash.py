# ABOUTME: Tests for HashEmbeddingAdapter - deterministic hash-based embeddings.
# ABOUTME: Verifies dimensions, model_id, deterministic behavior, and unit normalization.
"""Tests for HashEmbeddingAdapter."""
import pytest
import math

from agentmem.adapters.embeddings.hash import HashEmbeddingAdapter


class TestHashEmbeddingAdapter:
    """Test HashEmbeddingAdapter implementation."""

    def test_dimensions_property(self):
        """HashEmbeddingAdapter dimensions property returns constructor value."""
        adapter = HashEmbeddingAdapter(128)
        assert adapter.dimensions == 128

        adapter_64 = HashEmbeddingAdapter(64)
        assert adapter_64.dimensions == 64

    def test_model_id(self):
        """HashEmbeddingAdapter model_id property returns correct format."""
        adapter = HashEmbeddingAdapter(64)
        assert adapter.model_id == 'hash-64'

        adapter_256 = HashEmbeddingAdapter(256)
        assert adapter_256.model_id == 'hash-256'

    @pytest.mark.asyncio
    async def test_embed_returns_correct_length(self):
        """Embed method returns vector of correct length."""
        adapter = HashEmbeddingAdapter(128)
        result = await adapter.embed('hello')
        assert len(result) == 128

        adapter_64 = HashEmbeddingAdapter(64)
        result_64 = await adapter_64.embed('hello')
        assert len(result_64) == 64

    @pytest.mark.asyncio
    async def test_embed_deterministic(self):
        """Two calls with same text return same vector."""
        adapter = HashEmbeddingAdapter(128)
        result1 = await adapter.embed('hello')
        result2 = await adapter.embed('hello')
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_embed_unit_norm(self):
        """Embed returns unit-normalized vectors."""
        adapter = HashEmbeddingAdapter(128)
        result = await adapter.embed('hello')

        norm_squared = sum(x * x for x in result)
        assert abs(norm_squared - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_embed_different_texts_differ(self):
        """Different text inputs return different vectors."""
        adapter = HashEmbeddingAdapter(128)
        result_hello = await adapter.embed('hello')
        result_world = await adapter.embed('world')
        assert result_hello != result_world