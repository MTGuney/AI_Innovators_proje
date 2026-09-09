"""Retrieval: thresholds, filtering, company detection and context assembly."""

from __future__ import annotations

from app.models.schemas import RetrievalFilters
from app.rag.chunker import Chunk
from app.rag.retriever import Retriever, build_context, parse_tag

from .conftest import make_chunk


def seed(vector_store, embedder):
    """Index a small two-company corpus using the deterministic embedder."""
    chunks = [
        Chunk(
            chunk_id="apple::p1::c0",
            text="Apple total revenue grew this year. revenue revenue",
            metadata={
                "document_id": "apple-2024",
                "company": "Apple Inc",
                "year": 2024,
                "report_type": "10-K",
                "source_file": "AAPL.txt",
                "page_number": 1,
                "chunk_index": 0,
            },
        ),
        Chunk(
            chunk_id="apple::p2::c1",
            text="Apple risk factors mention supplier concentration. risk risk supplier",
            metadata={
                "document_id": "apple-2024",
                "company": "Apple Inc",
                "year": 2024,
                "report_type": "10-K",
                "source_file": "AAPL.txt",
                "page_number": 2,
                "chunk_index": 1,
            },
        ),
        Chunk(
            chunk_id="msft::p1::c0",
            text="Microsoft revenue and software income grew. revenue software income",
            metadata={
                "document_id": "msft-2024",
                "company": "Microsoft Corp",
                "year": 2024,
                "report_type": "10-K",
                "source_file": "MSFT.txt",
                "page_number": 1,
                "chunk_index": 0,
            },
        ),
    ]
    vector_store.add_chunks(chunks, embedder.embed_documents([c.text for c in chunks]))
    return Retriever(vector_store=vector_store, embedder=embedder)


def test_retrieves_semantically_closest_chunk(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)

    result = retriever.retrieve("risk supplier", top_k=1, similarity_threshold=0.0)

    assert result.chunks[0].chunk_id == "apple::p2::c1"
    assert result.chunks[0].company == "Apple Inc"
    assert result.chunks[0].page_number == 2


def test_top_k_limits_returned_chunks(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)

    result = retriever.retrieve("revenue", top_k=2, similarity_threshold=0.0)

    assert len(result.chunks) == 2
    # Over-fetching means more candidates are considered than returned.
    assert result.total_candidates >= len(result.chunks)


def test_threshold_discards_weak_matches(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)

    strict = retriever.retrieve("revenue", top_k=5, similarity_threshold=0.99)

    assert strict.is_empty


def test_company_filter_restricts_retrieval(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)

    result = retriever.retrieve(
        "revenue",
        top_k=5,
        filters=RetrievalFilters(companies=["Microsoft Corp"]),
        similarity_threshold=0.0,
    )

    assert {chunk.company for chunk in result.chunks} == {"Microsoft Corp"}


def test_detects_companies_named_in_the_question(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)

    detected = retriever.detect_companies("Compare Apple and Microsoft revenue growth")

    assert set(detected) == {"Apple Inc", "Microsoft Corp"}


def test_company_detection_ignores_unrelated_questions(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)

    assert retriever.detect_companies("What were the main risk factors?") == []


def test_resolve_company_matches_partial_names(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)

    assert retriever.resolve_company("apple") == "Apple Inc"
    assert retriever.resolve_company("Tesla") is None


def test_per_company_retrieval_gives_each_company_a_budget(vector_store, fake_embedder):
    retriever = seed(vector_store, fake_embedder)

    results = retriever.retrieve_per_company(
        "revenue",
        companies=["Apple Inc", "Microsoft Corp"],
        top_k_per_company=1,
        similarity_threshold=0.0,
    )

    assert set(results) == {"Apple Inc", "Microsoft Corp"}
    # Neither company can crowd the other out of the comparison.
    for company, result in results.items():
        assert len(result.chunks) == 1
        assert result.chunks[0].company == company


# --- context assembly ----------------------------------------------------- #


def test_context_numbers_chunks_for_citation():
    bundle = build_context([make_chunk(chunk_id="a"), make_chunk(chunk_id="b")])

    assert "[S1]" in bundle.text and "[S2]" in bundle.text
    assert bundle.tag_map()["S2"].chunk_id == "b"


def test_context_headers_carry_provenance():
    bundle = build_context([make_chunk()])

    # The model sees where each passage came from, which lets it cite honestly.
    assert "Acme Annual Report" in bundle.text
    assert "page 1" in bundle.text
    assert "Item 7. MD&A" in bundle.text


def test_context_respects_the_character_budget():
    chunks = [make_chunk(text="x" * 900, chunk_id=f"c{i}") for i in range(10)]

    bundle = build_context(chunks, max_chars=2000)

    # Whole chunks only: a truncated financial passage is worse than none.
    assert 0 < len(bundle.chunks) < 10
    assert len(bundle.text) <= 2000


def test_continuous_numbering_keeps_tags_unique_across_groups():
    first = build_context([make_chunk(chunk_id="a")], start_index=1)
    second = build_context([make_chunk(chunk_id="b")], start_index=first.next_index)

    assert "[S2]" in second.text
    assert second.tag_map()["S2"].chunk_id == "b"


def test_parse_tag_normalises_shapes():
    assert parse_tag("[s3]") == "S3"
    assert parse_tag(" S3 ") == "S3"
    assert parse_tag("nonsense") is None
