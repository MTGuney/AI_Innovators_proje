"""Side-by-side comparison of a metric across several companies.

The spec requires the UI to distinguish three kinds of statement, so this
service keeps them structurally separate rather than blending them into prose:

  * `retrieved_fact`       -- sentences lifted verbatim from indexed reports;
  * `ai_summary`           -- the model's comparison of those sentences;
  * `calculated_comparison`-- arithmetic, which the prompt requires the model to
                              label and to perform only when both operands are
                              present in the context.

Retrieval is balanced per company so a verbose filing cannot crowd out the
other side of the comparison.
"""

from __future__ import annotations

import logging
import re
import time

from app.config import settings
from app.models.schemas import (
    CompanyFindings,
    ComparisonRequest,
    ComparisonResponse,
    Confidence,
    RetrievedChunk,
)
from app.llm.foundry_client import FoundryLocalClient, get_foundry_client
from app.rag import prompts
from app.rag.retriever import ContextBundle, Retriever, build_context, get_retriever
from app.services.grounding import check_numeric_grounding
from app.services.rag_service import to_citation
from app.services.response_parser import parse_structured_answer

logger = logging.getLogger(__name__)

# Facts are only useful for comparison if they carry a figure.
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_HAS_NUMBER = re.compile(r"\d")
MAX_FACTS_PER_COMPANY = 4
MIN_FACT_CHARS = 40
MAX_FACT_CHARS = 320


class ComparisonService:
    """Compares companies on a metric using only indexed report content."""

    def __init__(
        self,
        retriever: Retriever | None = None,
        foundry: FoundryLocalClient | None = None,
    ) -> None:
        self._retriever = retriever or get_retriever()
        self._foundry = foundry or get_foundry_client()

    def compare(self, request: ComparisonRequest) -> ComparisonResponse:
        """Retrieve per company, then summarise the differences."""
        started = time.perf_counter()
        query = _build_query(request)

        results = self._retriever.retrieve_per_company(
            query,
            companies=request.companies,
            top_k_per_company=request.top_k_per_company or settings.top_k,
            years=request.years,
        )

        # Number every company's excerpts continuously so citation tags stay
        # unique across the whole prompt.
        bundles: dict[str, ContextBundle] = {}
        next_index = 1
        # Split the context budget evenly so no company is truncated away.
        per_company_budget = max(
            1000, settings.max_context_chars // max(1, len(request.companies))
        )
        for company, result in results.items():
            bundle = build_context(
                result.chunks, max_chars=per_company_budget, start_index=next_index
            )
            bundles[company] = bundle
            next_index = bundle.next_index

        per_company = [
            _summarise_company(company, results[company].chunks)
            for company in request.companies
        ]

        if not any(entry.has_data for entry in per_company):
            return ComparisonResponse(
                metric=request.metric,
                companies=request.companies,
                years=request.years,
                per_company=per_company,
                summary=prompts.NO_CONTEXT_MESSAGE,
                confidence="low",
                model=self._foundry.chat_model,
                elapsed_ms=_elapsed_ms(started),
            )

        raw = self._foundry.chat(
            [
                {"role": "system", "content": prompts.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": prompts.build_comparison_prompt(
                        request.metric,
                        {company: bundle.text for company, bundle in bundles.items()},
                    ),
                },
            ]
        )
        parsed = parse_structured_answer(raw)
        summary = parsed.answer or prompts.NO_CONTEXT_MESSAGE

        # Comparisons invite arithmetic, which is exactly where invented figures
        # appear, so the same numeric check applies across all the companies.
        grounding = check_numeric_grounding(
            summary, "\n".join(bundle.text for bundle in bundles.values())
        )

        confidence: Confidence = "low"
        if (
            not parsed.used_fallback
            and all(e.has_data for e in per_company)
            and grounding.is_fully_grounded
        ):
            confidence = parsed.confidence

        logger.info(
            "Compared %s on %r in %dms",
            request.companies, request.metric, _elapsed_ms(started),
        )
        return ComparisonResponse(
            metric=request.metric,
            companies=request.companies,
            years=request.years,
            per_company=per_company,
            summary=summary,
            summary_kind="ai_summary",
            confidence=confidence,
            unsupported_figures=grounding.unsupported,
            model=self._foundry.chat_model,
            elapsed_ms=_elapsed_ms(started),
        )


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


def _build_query(request: ComparisonRequest) -> str:
    """Turn the structured request into a natural-language retrieval query."""
    years = " ".join(str(year) for year in request.years)
    return f"{request.metric} {years}".strip()


def _summarise_company(company: str, chunks: list[RetrievedChunk]) -> CompanyFindings:
    """Collect verbatim, figure-bearing sentences -- no generation involved."""
    if not chunks:
        return CompanyFindings(
            company=company,
            kind="retrieved_fact",
            findings=[],
            sources=[],
            has_data=False,
        )

    findings: list[str] = []
    for chunk in chunks:
        for sentence in _SENTENCE.split(" ".join(chunk.text.split())):
            candidate = sentence.strip()
            if (
                MIN_FACT_CHARS <= len(candidate) <= MAX_FACT_CHARS
                and _HAS_NUMBER.search(candidate)
                and candidate not in findings
            ):
                findings.append(candidate)
            if len(findings) >= MAX_FACTS_PER_COMPANY:
                break
        if len(findings) >= MAX_FACTS_PER_COMPANY:
            break

    return CompanyFindings(
        company=company,
        kind="retrieved_fact",
        findings=findings,
        sources=[to_citation(chunk) for chunk in chunks],
        has_data=True,
    )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


_service: ComparisonService | None = None


def get_comparison_service() -> ComparisonService:
    """Return the process-wide comparison service (FastAPI dependency)."""
    global _service
    if _service is None:
        _service = ComparisonService()
    return _service
