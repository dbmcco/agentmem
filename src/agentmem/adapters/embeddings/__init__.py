# ABOUTME: Embedding adapter implementations.
# ABOUTME: HashEmbeddingProvider and future backends (Ollama, OpenAI).

from .hash import HashEmbeddingProvider, HashEmbeddingAdapter

__all__ = ["HashEmbeddingProvider", "HashEmbeddingAdapter"]
