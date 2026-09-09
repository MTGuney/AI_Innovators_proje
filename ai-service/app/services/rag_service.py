"""RAG orchestration: question -> retrieval -> grounded, cited answer.

This is the module that wires the pieces together. Each step stays small and
inspectable, and every answer carries the chunks it was built from so the UI
can show the user exactly why a source was used.
"""

from __future__ import annotations

import logging
import time
from typing import Sequence

from app.config import settings
from app.models.schemas import (
    ChatTurn,
    Confidence,
    RagAnswer,
    RagQueryRequest,
    RetrievalFilters,
    RetrievedChunk,
    SearchRequest,
    SearchResponse,
    SourceCitation,
)
from app.llm.foundry_client import FoundryError, FoundryLocalClient, get_foundry_client
from app.rag import prompts
from app.rag.retriever import ContextBundle, Retriever, build_context, get_retriever
from app.services.grounding import GroundingReport, check_numeric_grounding
from app.services.response_parser import ParsedAnswer, parse_structured_answer

logger = logging.getLogger(__name__)

# Characters of a chunk shown inline under an answer (full text stays available).
EXCERPT_CHARS = 420
# When the model cites nothing, fall back to this many top-relevance chunks.
IMPLICIT_SOURCE_LIMIT = 3
# Retrieval budget per company when a question spans several companies.
MULTI_COMPANY_MIN_K = 3


class RagService:
    """Answers financial questions from the indexed report corpus."""

    def __init__(
        self,
        retriever: Retriever | None = None,
        foundry: FoundryLocalClient | None = None,
    ) -> None:
        self._retriever = retriever or get_retriever()
        self._foundry = foundry or get_foundry_client()

    # ------------------------------------------------------------------ #
    # Semantic search (no generation)
    # ------------------------------------------------------------------ #

    def search(self, request: SearchRequest) -> SearchResponse:
        """Expose raw retrieval so the UI can explore the index directly."""
        result = self._retriever.retrieve(
            request.question,
            top_k=request.top_k,
            filters=request.filters,
            similarity_threshold=request.similarity_threshold,
        )
        return SearchResponse(
            question=request.question,
            top_k=result.top_k,
            similarity_threshold=result.similarity_threshold,
            total_candidates=result.total_candidates,
            chunks=result.chunks,
        )

    # ------------------------------------------------------------------ #
    # Grounded question answering
    # ------------------------------------------------------------------ #

    def answer(self, request: RagQueryRequest) -> RagAnswer:
        """Run the full RAG pipeline and return a validated, cited answer."""
        started = time.perf_counter()

        search_query = self._resolve_query(request.question, request.history)
        chunks = self._retrieve(request, search_query)

        if not chunks:
            logger.info("No chunks above threshold for: %s", search_query[:120])
            return self._no_context_answer(started)

        bundle = build_context(chunks)
        raw = self._foundry.chat(
            [
                {"role": "system", "content": prompts.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": prompts.build_rag_prompt(
                        request.question, bundle.text, request.history
                    ),
                },
            ]
        )
        parsed = parse_structured_answer(raw)
        sources = build_citations(parsed.source_tags, bundle)

        # Validate before answering: figures the context does not contain are
        # the failure mode that matters most in financial QA.
        grounding = check_numeric_grounding(
            " ".join([parsed.answer, *parsed.key_points]), bundle.text
        )

        return RagAnswer(
            answer=parsed.answer,
            key_points=parsed.key_points,
            sources=sources,
            confidence=_final_confidence(parsed, sources, grounding),
            grounded=True,
            unsupported_figures=grounding.unsupported,
            model=self._foundry.chat_model,
            elapsed_ms=_elapsed_ms(started),
            retrieved_chunks=chunks,
        )

    # ------------------------------------------------------------------ #
    # Pipeline steps
    # ------------------------------------------------------------------ #

    def _resolve_query(
        self, question: str, history: Sequence[ChatTurn]
    ) -> str:
        """Rewrite a follow-up into a standalone query before embedding it.

        Retrieval sees only one string, so "How is that different from 2023?"
        must be expanded or it will retrieve the wrong chunks. A failure here
        is never fatal -- we simply search on the original wording.
        """
        if not history:
            return question
        try:
            rewritten = self._foundry.generate(
                prompts.build_query_rewrite_prompt(question, history),
                max_tokens=120,
                temperature=0.0,
            ).strip().strip('"')
        except FoundryError as exc:
            logger.warning("Query rewrite failed, using original question: %s", exc)
            return question

        if not rewritten or len(rewritten) > 400:
            return question
        logger.info("Rewrote follow-up %r -> %r", question, rewritten)
        return rewritten

    def _retrieve(
        self, request: RagQueryRequest, search_query: str
    ) -> list[RetrievedChunk]:
        """Retrieve chunks, balancing across companies for comparison questions."""
        filters = request.filters

        # Explicit filters always win over inference.
        if not filters.is_empty:
            return self._retriever.retrieve(
                search_query,
                top_k=request.top_k,
                filters=filters,
                similarity_threshold=request.similarity_threshold,
            ).chunks

        detected = self._retriever.detect_companies(search_query)

        if len(detected) >= 2:
            # Multi-document question: give every company its own budget so one
            # verbose filing cannot crowd the others out of the context window.
            per_company = max(
                MULTI_COMPANY_MIN_K,
                (request.top_k or settings.top_k) // len(detected),
            )
            logger.info(
                "Multi-company question across %s (k=%d each)", detected, per_company
            )
            results = self._retriever.retrieve_per_company(
                search_query,
                companies=detected,
                top_k_per_company=per_company,
                similarity_threshold=request.similarity_threshold,
            )
            merged = [chunk for result in results.values() for chunk in result.chunks]
            merged.sort(key=lambda chunk: chunk.relevance, reverse=True)
            return merged

        return self._retriever.retrieve(
            search_query,
            top_k=request.top_k,
            filters=RetrievalFilters(companies=detected) if detected else filters,
            similarity_threshold=request.similarity_threshold,
        ).chunks

    def _no_context_answer(self, started: float) -> RagAnswer:
        """The honest answer when retrieval found nothing relevant."""
        return RagAnswer(
            answer=prompts.NO_CONTEXT_MESSAGE,
            key_points=[],
            sources=[],
            confidence="low",
            grounded=False,
            model=self._foundry.chat_model,
            elapsed_ms=_elapsed_ms(started),
            retrieved_chunks=[],
        )


# ---------------------------------------------------------------------- #
# Shared helpers (also used by the comparison service)
# ---------------------------------------------------------------------- #


def build_citations(tags: Sequence[str], *bundles: ContextBundle) -> list[SourceCitation]:
    """Map citation tags onto the chunks they refer to across one or more bundles."""
    tag_map: dict[str, RetrievedChunk] = {}
    for bundle in bundles:
        tag_map.update(bundle.tag_map())

    cited = [tag_map[tag] for tag in tags if tag in tag_map]
    if not cited:
        # The model answered but cited nothing; surface the strongest evidence
        # it was shown rather than presenting an answer with no provenance.
        all_chunks = [chunk for bundle in bundles for chunk in bundle.chunks]
        cited = sorted(all_chunks, key=lambda c: c.relevance, reverse=True)[
            :IMPLICIT_SOURCE_LIMIT
        ]

    return [to_citation(chunk) for chunk in cited]


def to_citation(chunk: RetrievedChunk) -> SourceCitation:
    """Convert a retrieved chunk into a user-facing citation."""
    return SourceCitation(
        document=chunk.title or chunk.source_file or chunk.document_id,
        document_id=chunk.document_id,
        page=chunk.page_number,
        relevance=chunk.relevance,
        company=chunk.company,
        year=chunk.year,
        report_type=chunk.report_type,
        section=chunk.section,
        chunk_id=chunk.chunk_id,
        excerpt=_excerpt(chunk.text),
    )


def _excerpt(text: str) -> str:
    body = " ".join(text.split())
    return body if len(body) <= EXCERPT_CHARS else body[:EXCERPT_CHARS].rstrip() + "..."


def _final_confidence(
    parsed: ParsedAnswer,
    sources: Sequence[SourceCitation],
    grounding: GroundingReport | None = None,
) -> Confidence:
    """Never report more confidence than the evidence and parse quality allow."""
    if parsed.used_fallback or not sources:
        return "low"
    if grounding and not grounding.is_fully_grounded:
        # Unverifiable figures are the worst failure mode here, so they cap
        # confidence hard regardless of how sure the model claimed to be.
        return "low"
    if parsed.confidence == "high" and max(s.relevance for s in sources) < 0.5:
        # The model felt sure, but nothing retrieved was a strong match.
        return "medium"
    return parsed.confidence


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


_service: RagService | None = None


def get_rag_service() -> RagService:
    """Return the process-wide RAG service (used as a FastAPI dependency)."""
    global _service
    if _service is None:
        _service = RagService()
    return _service
