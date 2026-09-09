"""Comparison mode: balanced retrieval and labelled provenance."""

from __future__ import annotations

import json

import pytest

from app.models.schemas import ComparisonRequest
from app.services.comparison_service import ComparisonService

from .test_rag_service import ScriptedFoundry
from .test_retriever import seed


@pytest.fixture
def service(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)
    foundry = ScriptedFoundry(
        replies=[
            json.dumps(
                {
                    "answer": "Apple grew faster than Microsoft [S1][S2].",
                    "sources": ["S1", "S2"],
                    "confidence": "high",
                }
            )
        ]
    )
    return ComparisonService(retriever=retriever, foundry=foundry), foundry


def test_compares_both_companies_with_labelled_provenance(service):
    comparison, _ = service

    result = comparison.compare(
        ComparisonRequest(companies=["Apple Inc", "Microsoft Corp"], metric="Revenue")
    )

    assert [entry.company for entry in result.per_company] == [
        "Apple Inc",
        "Microsoft Corp",
    ]
    # The spec requires retrieved facts and the AI summary to be distinguishable.
    assert all(entry.kind == "retrieved_fact" for entry in result.per_company)
    assert result.summary_kind == "ai_summary"
    assert result.summary.startswith("Apple grew faster")


def test_each_company_gets_its_own_citations(service):
    comparison, _ = service

    result = comparison.compare(
        ComparisonRequest(companies=["Apple Inc", "Microsoft Corp"], metric="Revenue")
    )

    for entry in result.per_company:
        assert entry.sources, f"{entry.company} has no sources"
        assert all(source.company == entry.company for source in entry.sources)


def test_citation_tags_are_unique_across_companies(service):
    comparison, foundry = service

    comparison.compare(
        ComparisonRequest(companies=["Apple Inc", "Microsoft Corp"], metric="Revenue")
    )

    prompt = foundry.prompts[-1]
    # Numbering continues across groups, so [S1] never means two things.
    assert "[S1]" in prompt and "[S2]" in prompt
    assert "=== Apple Inc ===" in prompt and "=== Microsoft Corp ===" in prompt


def test_company_without_data_is_reported_not_guessed(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)
    comparison = ComparisonService(retriever=retriever, foundry=ScriptedFoundry())

    result = comparison.compare(
        ComparisonRequest(companies=["Apple Inc", "Nonexistent Corp"], metric="Revenue")
    )

    missing = next(e for e in result.per_company if e.company == "Nonexistent Corp")
    assert missing.has_data is False
    assert missing.findings == []
    # A partial comparison must not be presented confidently.
    assert result.confidence == "low"


def test_no_data_at_all_yields_the_no_context_message(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)
    foundry = ScriptedFoundry()
    comparison = ComparisonService(retriever=retriever, foundry=foundry)

    result = comparison.compare(
        ComparisonRequest(companies=["Ghost Ltd", "Phantom Inc"], metric="Revenue")
    )

    assert result.confidence == "low"
    assert "No sufficiently relevant information" in result.summary
    # With nothing retrieved the model must not be asked to summarise.
    assert foundry.prompts == []


def test_retrieved_facts_are_extracted_not_generated(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)
    foundry = ScriptedFoundry()
    comparison = ComparisonService(retriever=retriever, foundry=foundry)

    result = comparison.compare(
        ComparisonRequest(companies=["Apple Inc", "Microsoft Corp"], metric="Revenue")
    )

    # Exactly one model call, for the summary. The per-company facts are lifted
    # from the retrieved text, so they cannot have been invented.
    assert len(foundry.prompts) == 1

    for entry in result.per_company:
        for finding in entry.findings:
            assert any(character.isdigit() for character in finding)


def test_invented_summary_figures_are_flagged(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)
    foundry = ScriptedFoundry(
        replies=[
            json.dumps(
                {
                    "answer": "Apple made $245.5 billion, Microsoft $229.9 billion.",
                    "sources": ["S1"],
                    "confidence": "high",
                }
            )
        ]
    )
    comparison = ComparisonService(retriever=retriever, foundry=foundry)

    result = comparison.compare(
        ComparisonRequest(companies=["Apple Inc", "Microsoft Corp"], metric="Revenue")
    )

    assert "245.5" in result.unsupported_figures
    assert result.confidence == "low"


@pytest.mark.parametrize(
    "companies", [["Apple Inc"], ["Apple Inc", "apple inc"], []]
)
def test_at_least_two_distinct_companies_are_required(companies):
    with pytest.raises(ValueError):
        ComparisonRequest(companies=companies, metric="Revenue")
