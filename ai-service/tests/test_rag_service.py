"""End-to-end RAG orchestration, with a scripted LLM instead of a real one."""

from __future__ import annotations

import json

import pytest

from app.models.schemas import RagQueryRequest, RetrievalFilters, SearchRequest
from app.rag import prompts
from app.services.rag_service import RagService

from .test_retriever import seed


class ScriptedFoundry:
    """Stands in for Foundry Local; records prompts and replays canned replies."""

    def __init__(self, replies=None):
        self.chat_model = "test-model"
        self.embedding_model = "test-embedder"
        self.replies = list(replies or [])
        self.prompts: list[str] = []

    def _next(self) -> str:
        return self.replies.pop(0) if self.replies else json.dumps(
            {"answer": "Revenue grew [S1].", "sources": ["S1"], "confidence": "high"}
        )

    def chat(self, messages, **_):
        self.prompts.append(messages[-1]["content"])
        return self._next()

    def generate(self, prompt, **_):
        self.prompts.append(prompt)
        return self._next()


@pytest.fixture
def service(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)
    foundry = ScriptedFoundry()
    return RagService(retriever=retriever, foundry=foundry), foundry


def test_answer_is_grounded_and_cited(service):
    rag, _ = service

    answer = rag.answer(
        RagQueryRequest(question="How did revenue change?", similarity_threshold=0.0)
    )

    assert answer.grounded is True
    assert answer.answer.startswith("Revenue grew")
    assert len(answer.sources) == 1
    assert answer.sources[0].document
    assert answer.sources[0].page is not None
    # Retrieval stays inspectable: the caller sees everything the model saw.
    assert answer.retrieved_chunks
    assert answer.model == "test-model"


def test_context_is_the_only_evidence_offered_to_the_model(service):
    rag, foundry = service

    rag.answer(RagQueryRequest(question="risk supplier", similarity_threshold=0.0))

    prompt = foundry.prompts[-1]
    assert "CONTEXT:" in prompt
    assert "[S1]" in prompt
    assert "supplier" in prompt.lower()


def test_no_relevant_context_yields_an_honest_refusal(service):
    rag, foundry = service

    answer = rag.answer(
        RagQueryRequest(question="What is the weather?", similarity_threshold=0.99)
    )

    assert answer.grounded is False
    assert answer.answer == prompts.NO_CONTEXT_MESSAGE
    assert answer.sources == []
    assert answer.confidence == "low"
    # Nothing was retrieved, so the model must not be invoked at all.
    assert foundry.prompts == []


def test_confidence_is_capped_when_the_reply_could_not_be_parsed(
    vector_store, fake_embedder
):
    retriever = seed(vector_store, fake_embedder)
    foundry = ScriptedFoundry(replies=["Revenue grew, I think."])
    rag = RagService(retriever=retriever, foundry=foundry)

    answer = rag.answer(RagQueryRequest(question="revenue", similarity_threshold=0.0))

    assert answer.confidence == "low"


def test_uncited_answers_still_show_their_strongest_evidence(
    vector_store, fake_embedder
):
    retriever = seed(vector_store, fake_embedder)
    foundry = ScriptedFoundry(
        replies=[json.dumps({"answer": "Revenue grew.", "sources": [], "confidence": "high"})]
    )
    rag = RagService(retriever=retriever, foundry=foundry)

    answer = rag.answer(RagQueryRequest(question="revenue", similarity_threshold=0.0))

    # An answer with no provenance would be unverifiable, so fall back to the
    # top-ranked passages the model was shown.
    assert answer.sources


def test_multi_company_questions_retrieve_from_both_companies(
    vector_store, fake_embedder
):
    retriever = seed(vector_store, fake_embedder)
    foundry = ScriptedFoundry()
    rag = RagService(retriever=retriever, foundry=foundry)

    answer = rag.answer(
        RagQueryRequest(
            question="Compare Apple and Microsoft revenue",
            similarity_threshold=0.0,
        )
    )

    companies = {chunk.company for chunk in answer.retrieved_chunks}
    assert companies == {"Apple Inc", "Microsoft Corp"}


def test_explicit_filters_take_precedence_over_detection(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)
    rag = RagService(retriever=retriever, foundry=ScriptedFoundry())

    answer = rag.answer(
        RagQueryRequest(
            question="Compare Apple and Microsoft revenue",
            filters=RetrievalFilters(companies=["Microsoft Corp"]),
            similarity_threshold=0.0,
        )
    )

    assert {chunk.company for chunk in answer.retrieved_chunks} == {"Microsoft Corp"}


def test_follow_up_questions_are_rewritten_before_retrieval(
    vector_store, fake_embedder
):
    retriever = seed(vector_store, fake_embedder)
    foundry = ScriptedFoundry(
        replies=[
            "Microsoft revenue in 2024",  # the rewrite
            json.dumps({"answer": "It grew [S1].", "sources": ["S1"]}),
        ]
    )
    rag = RagService(retriever=retriever, foundry=foundry)

    rag.answer(
        RagQueryRequest(
            question="How about them?",
            history=[
                {"role": "user", "content": "What was Microsoft revenue?"},
                {"role": "assistant", "content": "Microsoft revenue grew."},
            ],
            similarity_threshold=0.0,
        )
    )

    # The first call rewrites the pronoun; the second answers with context.
    assert "Rewrite the user's latest question" in foundry.prompts[0]
    assert len(foundry.prompts) == 2


def test_search_returns_chunks_without_calling_the_model(service):
    rag, foundry = service

    response = rag.search(SearchRequest(question="revenue", similarity_threshold=0.0))

    assert response.chunks
    assert response.total_candidates >= len(response.chunks)
    assert foundry.prompts == []


@pytest.mark.parametrize("question", ["", "  ", "ab"])
def test_short_questions_are_rejected(question):
    with pytest.raises(ValueError):
        RagQueryRequest(question=question)


def test_invented_figures_cap_confidence_and_are_reported(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)
    foundry = ScriptedFoundry(
        replies=[
            json.dumps(
                {
                    "answer": "Revenue was $245.5 billion [S1].",
                    "sources": ["S1"],
                    "confidence": "high",
                }
            )
        ]
    )
    rag = RagService(retriever=retriever, foundry=foundry)

    answer = rag.answer(RagQueryRequest(question="revenue", similarity_threshold=0.0))

    # The seeded corpus contains no such figure, so the claim is flagged and
    # the model's self-reported confidence is not taken at face value.
    assert "245.5" in answer.unsupported_figures
    assert answer.confidence == "low"
