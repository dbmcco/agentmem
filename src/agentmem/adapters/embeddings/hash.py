# ABOUTME: Hash-based pseudo-embedding provider for testing.
# ABOUTME: Deterministic embeddings via character-level hashing.
"""Hash-based pseudo-embedding provider — zero external services.

Produces deterministic embeddings using character-level hashing.
Not suitable for production semantic search but enables the
zero-external-services deployment mode and testing.
"""

from __future__ import annotations

import hashlib


class HashEmbeddingAdapter:
    """Deterministic hash-based embeddings for testing and offline use."""

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions
        self.model_id = f'hash-{dimensions}d'

    async def embed(self, text: str) -> list[float]:
        """Generate deterministic embedding from text using SHA-256."""
        # Hash the text and expand to requested dimensions deterministically
        digest = hashlib.sha256(text.encode()).digest()
        # Repeat digest bytes to fill dimensions, normalize to [-1, 1]
        raw = list(digest) * (self.dimensions // 32 + 1)
        return [(b / 127.5 - 1.0) for b in raw[:self.dimensions]]

    async def close(self) -> None:
        """No-op close method since no resources to clean up."""
        pass


class HashEmbeddingProvider:
    """Deterministic hash-based embeddings for testing and offline use."""

    def __init__(self, dimensions: int = 64) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        # Extend hash bytes to fill dimensions
        extended = h * ((self._dimensions * 4 // len(h)) + 1)
        values: list[float] = []
        for i in range(self._dimensions):
            byte_val = extended[i * 4] | (extended[i * 4 + 1] << 8)
            values.append((byte_val / 65535.0) * 2 - 1)  # normalize to [-1, 1]
        return values
