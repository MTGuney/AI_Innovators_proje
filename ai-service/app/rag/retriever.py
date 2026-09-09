"""Semantic retrieval over the indexed chunks.

Responsibilities:
  * translate `RetrievalFilters` into a Chroma `where` clause;
  * embed the query and pull candidates, over-fetching so the similarity
    threshold can drop weak matches without starving `top_k`;
  * balance retrieval across companies for comparison questions, so one
    verbose filing cannot crowd out the other side of the comparison;
  * assemble a numbered context block that the prompt can cite by index.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.config import settings
from app.models.schemas import RetrievalFilters, RetrievedChunk
from app.rag.embeddings import Embedder, get_embedder
from app.rag.vector_store import SearchHit, VectorStore, get_vector_store

logger = logging.getLogger(__name__)

# Pull extra candidates so threshold filtering still leaves us `top_k` results.
OVERFETCH_FACTOR = 3
MIN_CANDIDATES = 15


@dataclass
class RetrievalResult:
    """Everything retrieval produced, including what it discarded and why."""

    question: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    total_candidates: int = 0
    top_k: int = 0
    similarity_threshold: float = 0.0
    filters: RetrievalFilters = field(default_factory=RetrievalFilters)

    @property
    def is_empty(self) -> bool:
        return not self.chunks


class Retriever:
    """Embeds questions and finds the most relevant indexed chunks."""

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._store = vector_store or get_vector_store()
        self._embedder = embedder or get_embedder()

    # ------------------------------------------------------------------ #
    # Retrieval
    # ------------------------------------------------------------------ #

    def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        filters: RetrievalFilters | None = None,
        similarity_threshold: float | None = None,
    ) -> RetrievalResult:
        """Single-pass semantic search with optional metadata narrowing."""
        k = top_k or settings.top_k
        threshold = (
            settings.similarity_threshold
            if similarity_threshold is None
            else similarity_threshold
        )
        filters = filters or RetrievalFilters()

        embedding = self._embedder.embed_query(question)
        hits = self._store.query(
            embedding,
            top_k=max(k * OVERFETCH_FACTOR, MIN_CANDIDATES),
            where=build_where_clause(filters),
        )
        kept = [hit for hit in hits if hit.relevance >= threshold][:k]

        logger.info(
            "Retrieval: %d candidate(s), %d above threshold %.2f (top_k=%d)",
            len(hits), len(kept), threshold, k,
        )
        return RetrievalResult(
            question=question,
            chunks=[to_retrieved_chunk(hit) for hit in kept],
            total_candidates=len(hits),
            top_k=k,
            similarity_threshold=threshold,
            filters=filters,
        )

    def retrieve_per_company(
        self,
        question: str,
        companies: Sequence[str],
        top_k_per_company: int | None = None,
        years: Sequence[int] | None = None,
        similarity_threshold: float | None = None,
    ) -> dict[str, RetrievalResult]:
        """Run one balanced search per company (used by comparison queries)."""
        k = top_k_per_company or settings.top_k
        results: dict[str, RetrievalResult] = {}
        for company in companies:
            resolved = self.resolve_company(company) or company
            results[company] = self.retrieve(
                question,
                top_k=k,
                filters=RetrievalFilters(
                    companies=[resolved], years=list(years or [])
                ),
                similarity_threshold=similarity_threshold,
            )
        return results

    # ------------------------------------------------------------------ #
    # Company awareness
    # ------------------------------------------------------------------ #

    def indexed_companies(self) -> list[str]:
        """Distinct company names present in the index."""
        names = {
            str(doc.get("company"))
            for doc in self._store.list_documents()
            if doc.get("company")
        }
        return sorted(names)

    def resolve_company(self, name: str) -> str | None:
        """Map a user-typed company ("apple") onto an indexed one ("Apple Inc")."""
        needle = name.strip().lower()
        if not needle:
            return None
        candidates = self.indexed_companies()
        for candidate in candidates:
            if candidate.lower() == needle:
                return candidate
        for candidate in candidates:
            if needle in candidate.lower() or candidate.lower() in needle:
                return candidate
        return None

    def detect_companies(self, question: str) -> list[str]:
        """Find indexed companies mentioned in the question.

        Enables the spec's multi-document behaviour ("Compare Tesla and Ford")
        without asking the user to set filters by hand.
        """
        found: list[str] = []
        for company in self.indexed_companies():
            # Match the distinctive first token ("Apple" in "Apple Inc"), so
            # suffixes like Inc/Corp do not have to be typed.
            head = re.split(r"[\s,]+", company.strip())[0]
            if len(head) < 3:
                continue
            if re.search(rf"\b{re.escape(head)}\b", question, re.IGNORECASE):
                found.append(company)
        return found


# ---------------------------------------------------------------------- #
# Helpers shared with the services layer
# ---------------------------------------------------------------------- #


def build_where_clause(filters: RetrievalFilters) -> dict[str, Any] | None:
    """Translate filters into Chroma's `where` syntax."""
    clauses: list[dict[str, Any]] = []
    if filters.companies:
        clauses.append({"company": {"$in": list(filters.companies)}})
    if filters.years:
        clauses.append({"year": {"$in": [int(year) for year in filters.years]}})
    if filters.report_types:
        clauses.append({"report_type": {"$in": list(filters.report_types)}})
    if filters.document_ids:
        clauses.append({"document_id": {"$in": list(filters.document_ids)}})

    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def to_retrieved_chunk(hit: SearchHit) -> RetrievedChunk:
    """Convert a raw vector-store hit into the public API shape."""
    metadata = hit.metadata
    year = metadata.get("year")
    chunk_index = metadata.get("chunk_index")
    return RetrievedChunk(
        chunk_id=hit.chunk_id,
        document_id=str(metadata.get("document_id", "")),
        source_file=str(metadata.get("source_file", "")),
        company=_optional_str(metadata.get("company")),
        year=int(year) if isinstance(year, (int, float)) else None,
        report_type=_optional_str(metadata.get("report_type")),
        title=_optional_str(metadata.get("title")),
        section=_optional_str(metadata.get("section")),
        page_number=hit.page_number,
        chunk_index=int(chunk_index) if isinstance(chunk_index, (int, float)) else None,
        relevance=round(hit.relevance, 4),
        text=hit.text,
    )


@dataclass(frozen=True)
class ContextBundle:
    """The context string plus the chunks that actually fit inside it.

    Citation tags are positional ([S1] is `chunks[0]`), so the caller must map
    tags against *these* chunks rather than the full retrieval result.
    """

    text: str
    chunks: tuple[RetrievedChunk, ...]
    start_index: int = 1

    @property
    def is_empty(self) -> bool:
        return not self.chunks

    @property
    def next_index(self) -> int:
        """First unused tag number, for numbering a following group."""
        return self.start_index + len(self.chunks)

    def tag_map(self) -> dict[str, RetrievedChunk]:
        """Citation tag ("S1") -> chunk, honouring this bundle's numbering."""
        return {
            f"S{self.start_index + offset}": chunk
            for offset, chunk in enumerate(self.chunks)
        }


def parse_tag(tag: str) -> str | None:
    """Normalise a citation tag such as "[s2]" or " S2 " to "S2"."""
    match = re.fullmatch(r"\[?\s*s\s*(\d+)\s*\]?", str(tag).strip(), re.IGNORECASE)
    return f"S{int(match.group(1))}" if match else None


def build_context(
    chunks: Sequence[RetrievedChunk],
    max_chars: int | None = None,
    start_index: int = 1,
) -> ContextBundle:
    """Assemble a numbered context block; [S1], [S2]... are cited by the prompt.

    `start_index` lets callers number several groups continuously, which the
    comparison flow relies on to keep tags unique across companies.
    """
    budget = max_chars or settings.max_context_chars
    blocks: list[str] = []
    included: list[RetrievedChunk] = []
    used = 0

    for offset, chunk in enumerate(chunks):
        block = f"[S{start_index + offset}] {_describe(chunk)}\n{chunk.text.strip()}"
        if used + len(block) > budget:
            # Keep whole chunks: a truncated financial passage is worse than none.
            logger.debug("Context budget reached after %d chunk(s)", offset)
            break
        blocks.append(block)
        included.append(chunk)
        used += len(block)

    return ContextBundle(
        text="\n\n---\n\n".join(blocks),
        chunks=tuple(included),
        start_index=start_index,
    )


def _describe(chunk: RetrievedChunk) -> str:
    """Human-readable provenance line shown to the model above each chunk."""
    parts = [chunk.title or chunk.source_file or chunk.document_id]
    if chunk.company:
        parts.append(chunk.company)
    if chunk.year:
        parts.append(str(chunk.year))
    if chunk.page_number:
        parts.append(f"page {chunk.page_number}")
    if chunk.section:
        parts.append(chunk.section)
    return " | ".join(str(part) for part in parts if part)


def _optional_str(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    """Return the process-wide retriever (used as a FastAPI dependency)."""
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever
