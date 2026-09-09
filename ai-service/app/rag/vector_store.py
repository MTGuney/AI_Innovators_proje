"""ChromaDB persistence for chunk embeddings and their metadata.

The rest of the service never imports `chromadb` directly -- it goes through
`VectorStore`, which owns collection setup, metadata hygiene and the conversion
from Chroma's cosine *distance* into the *relevance* score shown to users.

Embeddings are always supplied explicitly (see `app.rag.embeddings`), so Chroma
is used purely as a vector index and never runs an embedding model of its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import urlparse

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection

from app.config import settings
from app.rag.chunker import Chunk

logger = logging.getLogger(__name__)

# Cosine distance keeps relevance interpretable: relevance = 1 - distance.
COLLECTION_METADATA: dict[str, Any] = {"hnsw:space": "cosine"}

# Chroma only stores scalar metadata values.
_SCALARS = (str, int, float, bool)


class VectorStoreError(RuntimeError):
    """Raised when the vector database cannot serve a request."""

    user_message = "The document index is unavailable. Please try again shortly."


@dataclass(frozen=True)
class SearchHit:
    """One retrieved chunk with its provenance and relevance."""

    chunk_id: str
    text: str
    metadata: dict[str, Any]
    relevance: float

    @property
    def document_id(self) -> str:
        return str(self.metadata.get("document_id", ""))

    @property
    def page_number(self) -> int | None:
        page = self.metadata.get("page_number")
        return int(page) if isinstance(page, (int, float)) else None


class VectorStore:
    """Thin, testable wrapper around a single Chroma collection."""

    def __init__(
        self,
        client: ClientAPI | None = None,
        collection_name: str | None = None,
    ) -> None:
        self.collection_name = collection_name or settings.chroma_collection
        self._client = client or _build_client()
        self._collection = self._get_or_create_collection()

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #

    def add_chunks(self, chunks: Sequence[Chunk], embeddings: Sequence[list[float]]) -> int:
        """Upsert chunks and their vectors. Returns the number stored."""
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        if not chunks:
            return 0

        self._collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            embeddings=[list(vector) for vector in embeddings],
            metadatas=[_sanitise(chunk.metadata) for chunk in chunks],
        )
        logger.info("Stored %d chunk(s) in '%s'", len(chunks), self.collection_name)
        return len(chunks)

    def delete_document(self, document_id: str) -> int:
        """Remove every chunk belonging to a document. Returns chunks deleted."""
        existing = self._collection.get(
            where={"document_id": document_id}, include=[]
        )
        ids = existing.get("ids") or []
        if ids:
            self._collection.delete(ids=ids)
            logger.info("Deleted %d chunk(s) for document %s", len(ids), document_id)
        return len(ids)

    def reset(self) -> None:
        """Drop and recreate the collection (used by tests and re-indexing)."""
        self._client.delete_collection(self.collection_name)
        self._collection = self._get_or_create_collection()

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def query(
        self,
        embedding: Sequence[float],
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        """Return the `top_k` nearest chunks, optionally metadata-filtered."""
        try:
            result = self._collection.query(
                query_embeddings=[list(embedding)],
                n_results=max(1, top_k),
                where=where or None,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:  # noqa: BLE001 - surface one clean error type
            raise VectorStoreError(f"Vector search failed: {exc}") from exc

        ids = _first(result, "ids")
        documents = _first(result, "documents")
        metadatas = _first(result, "metadatas")
        distances = _first(result, "distances")

        return [
            SearchHit(
                chunk_id=str(chunk_id),
                text=str(document or ""),
                metadata=dict(metadata or {}),
                relevance=_to_relevance(distance),
            )
            for chunk_id, document, metadata, distance in zip(
                ids, documents, metadatas, distances
            )
        ]

    def document_exists(self, document_id: str) -> bool:
        """True when at least one chunk of the document is indexed."""
        found = self._collection.get(
            where={"document_id": document_id}, limit=1, include=[]
        )
        return bool(found.get("ids"))

    def find_by_checksum(self, checksum: str) -> str | None:
        """Return the document_id already indexed for this file content, if any."""
        found = self._collection.get(
            where={"checksum": checksum}, limit=1, include=["metadatas"]
        )
        metadatas = found.get("metadatas") or []
        if not metadatas:
            return None
        return str(metadatas[0].get("document_id", "")) or None

    def count(self) -> int:
        """Total number of indexed chunks."""
        return self._collection.count()

    def list_documents(self) -> list[dict[str, Any]]:
        """One metadata summary per indexed document."""
        records = self._collection.get(include=["metadatas"])
        documents: dict[str, dict[str, Any]] = {}
        for metadata in records.get("metadatas") or []:
            document_id = str((metadata or {}).get("document_id", ""))
            if not document_id:
                continue
            entry = documents.setdefault(
                document_id,
                {
                    "document_id": document_id,
                    "company": metadata.get("company"),
                    "year": metadata.get("year"),
                    "report_type": metadata.get("report_type"),
                    "title": metadata.get("title"),
                    "source_file": metadata.get("source_file"),
                    "checksum": metadata.get("checksum"),
                    "chunk_count": 0,
                    "page_count": 0,
                },
            )
            entry["chunk_count"] += 1
            page = metadata.get("page_number")
            if isinstance(page, (int, float)):
                entry["page_count"] = max(entry["page_count"], int(page))
        return sorted(documents.values(), key=lambda d: str(d.get("source_file") or ""))

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _get_or_create_collection(self) -> Collection:
        # embedding_function=None: vectors are always provided by the caller.
        return self._client.get_or_create_collection(
            name=self.collection_name,
            metadata=COLLECTION_METADATA,
            embedding_function=None,
        )


def _build_client() -> ClientAPI:
    """Create a Chroma client: HTTP when CHROMA_URL is set, else embedded."""
    if settings.use_remote_chroma:
        parsed = urlparse(settings.chroma_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 8000)
        logger.info("Connecting to Chroma server at %s:%s", host, port)
        return chromadb.HttpClient(host=host, port=port, ssl=parsed.scheme == "https")

    settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Using embedded Chroma store at %s", settings.chroma_persist_dir)
    return chromadb.PersistentClient(path=str(settings.chroma_persist_dir))


def _sanitise(metadata: dict[str, Any]) -> dict[str, Any]:
    """Drop null values and coerce anything Chroma cannot store into a string."""
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        clean[key] = value if isinstance(value, _SCALARS) else str(value)
    return clean


def _first(result: Any, key: str) -> list[Any]:
    """Chroma nests results one level per query; we only ever send one."""
    values = (result or {}).get(key) or []
    return list(values[0]) if values else []


def _to_relevance(distance: Any) -> float:
    """Convert cosine distance into a 0..1 relevance score."""
    try:
        return max(0.0, min(1.0, 1.0 - float(distance)))
    except (TypeError, ValueError):
        return 0.0


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Return the process-wide vector store (used as a FastAPI dependency)."""
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
