"""Embedding generation.

Embeddings are produced by Foundry Local's `/v1/embeddings` endpoint, so the
whole stack stays local and we avoid pulling in a heavyweight ML runtime.
The `Embedder` protocol keeps the rest of the RAG pipeline independent of that
choice -- swapping in another provider means implementing two methods.
"""

from __future__ import annotations

import logging
from typing import Iterable, Protocol, Sequence, runtime_checkable

from app.config import settings
from app.llm.foundry_client import FoundryLocalClient, get_foundry_client

logger = logging.getLogger(__name__)

Vector = list[float]


@runtime_checkable
class Embedder(Protocol):
    """Minimal contract the retriever and ingestion pipeline depend on."""

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        """Embed passages for storage."""

    def embed_query(self, text: str) -> Vector:
        """Embed a single search query."""


class FoundryEmbedder:
    """Embedder backed by a local embedding model served by Foundry Local."""

    def __init__(
        self,
        client: FoundryLocalClient | None = None,
        batch_size: int | None = None,
    ) -> None:
        self._client = client or get_foundry_client()
        self.batch_size = batch_size or settings.embedding_batch_size
        self.model = self._client.embedding_model

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        """Embed passages in batches, preserving input order."""
        vectors: list[Vector] = []
        for batch in _batched(texts, self.batch_size):
            vectors.extend(self._client.embed(batch))
            logger.debug("Embedded %d/%d passages", len(vectors), len(texts))
        return vectors

    def embed_query(self, text: str) -> Vector:
        """Embed one query string."""
        vectors = self._client.embed([text])
        if not vectors:
            raise RuntimeError("Embedding backend returned no vector for the query.")
        return vectors[0]


def _batched(items: Sequence[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Return the process-wide embedder (used as a FastAPI dependency)."""
    global _embedder
    if _embedder is None:
        _embedder = FoundryEmbedder()
    return _embedder
