# ABOUTME: OllamaEmbeddingAdapter — HTTP client for local Ollama embedding service.
# ABOUTME: Graceful degradation: returns None on connection error or timeout.
"""OllamaEmbeddingAdapter: httpx-based Ollama embedding client."""
from __future__ import annotations


class OllamaEmbeddingAdapter:
    """Embedding adapter for Ollama local inference server.

    Calls POST {url}/api/embeddings with {"model": model, "prompt": text}.
    Returns None on connection error or timeout (graceful degradation).

    Dimensions: determined by model. Default model qwen3-embedding:8b → 4096 dims.
    model_id: used to tag VectorRecord entries for model migration.
    """

    def __init__(
        self,
        url: str = "http://localhost:11434",
        model: str = "qwen3-embedding:8b",
        timeout: float = 30.0,
        dimensions: int = 4096,
    ) -> None:
        self._url = url
        self._model = model
        self._timeout = timeout
        self._dimensions = dimensions
        self._client = None  # lazy init

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> list[float] | None:
        """POST to Ollama /api/embeddings. Returns embedding list or None on error.

        Request body: {"model": self._model, "prompt": text}
        Response: {"embedding": [...]}

        Returns None on httpx.ConnectError, httpx.TimeoutException, or non-200 response.
        """
        import httpx
        try:
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=self._timeout)
            response = await self._client.post(
                f'{self._url}/api/embeddings',
                json={'model': self._model, 'prompt': text}
            )
            response.raise_for_status()
            return response.json()['embedding']
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            return None

    async def close(self) -> None:
        """Close the underlying httpx client if open."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
