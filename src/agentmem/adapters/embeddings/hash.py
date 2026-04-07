# ABOUTME: HashEmbeddingAdapter — deterministic SHA-256 based embeddings for tests.
# ABOUTME: No external services. Dimension-configurable. Never returns None.
"""HashEmbeddingAdapter: deterministic test embedding adapter."""
from __future__ import annotations

import hashlib
import math
import struct


class HashEmbeddingAdapter:
    """SHA-256-based deterministic embedding adapter for tests.

    Produces a unit-norm vector from the SHA-256 hash of the input text.
    Dimension-configurable. Never returns None (no external service).
    model_id: "hash-{dimensions}" (e.g. "hash-128").

    NOT suitable for semantic similarity — only for testing that vector
    storage, retrieval, and index operations work correctly.
    """

    def __init__(self, dimensions: int = 128) -> None:
        # STUB: store self._dimensions
        self._dimensions = dimensions

    @property
    def model_id(self) -> str:
        # STUB: return f"hash-{self._dimensions}"
        return f"hash-{self._dimensions}"

    @property
    def dimensions(self) -> int:
        # STUB: return self._dimensions
        return self._dimensions

    async def embed(self, text: str) -> list[float] | None:
        """Return a deterministic unit-norm vector derived from SHA-256(text).

        Algorithm:
          1. sha256_bytes = hashlib.sha256(text.encode()).digest()  # 32 bytes
          2. Tile/truncate sha256_bytes to fill self._dimensions * 4 bytes
          3. Unpack as little-endian floats: struct.unpack_from('<f', ...)
          4. L2-normalise the resulting vector
          5. Return as list[float]
        """
        # STUB: implement deterministic hash → unit-norm float vector
        sha_bytes = hashlib.sha256(text.encode()).digest()  # 32 bytes
        # need self._dimensions * 4 bytes total; tile sha_bytes
        raw = (sha_bytes * (self._dimensions * 4 // 32 + 1))[:self._dimensions * 4]
        # unpack as little-endian floats
        vec = list(struct.unpack_from(f'<{self._dimensions}f', raw))
        # L2-normalise
        norm = math.sqrt(sum(x*x for x in vec))
        if norm > 0:
            vec = [x/norm for x in vec]
        return vec

    async def close(self) -> None:
        """No-op."""
        pass
