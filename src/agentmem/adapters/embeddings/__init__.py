# ABOUTME: Export embeddings adapters for easy importing.
"""Embeddings adapters."""

from .hash import HashEmbeddingAdapter

# For backward compatibility with existing tests
HashEmbeddingProvider = HashEmbeddingAdapter

__all__ = ["HashEmbeddingAdapter", "HashEmbeddingProvider"]