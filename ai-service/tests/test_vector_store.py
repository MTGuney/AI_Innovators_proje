"""Vector store: storage, metadata filtering, relevance and deletion."""

from __future__ import annotations

from app.models.schemas import RetrievalFilters
from app.rag.chunker import Chunk
from app.rag.retriever import build_where_clause


def _chunk(chunk_id: str, text: str, **metadata) -> Chunk:
    base = {
        "document_id": "doc-a",
        "source_file": "a.txt",
        "page_number": 1,
        "chunk_index": 0,
        "checksum": "sum-a",
    }
    base.update(metadata)
    return Chunk(chunk_id=chunk_id, text=text, metadata=base)


def test_add_and_search_orders_by_similarity(vector_store):
    chunks = [
        _chunk("c1", "Total revenue grew", company="Acme", year=2024),
        _chunk("c2", "Risk factors include supplier concentration", company="Acme", year=2024),
    ]
    embeddings = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

    assert vector_store.add_chunks(chunks, embeddings) == 2
    assert vector_store.count() == 2

    hits = vector_store.query([1.0, 0.05, 0.0], top_k=2)

    assert [hit.chunk_id for hit in hits] == ["c1", "c2"]
    # Cosine distance is converted into a 0..1 relevance for display.
    assert hits[0].relevance > hits[1].relevance
    assert 0.0 <= hits[1].relevance <= 1.0


def test_metadata_filter_restricts_results(vector_store):
    vector_store.add_chunks(
        [
            _chunk("a1", "Apple revenue", document_id="apple", company="Apple", year=2024),
            _chunk("m1", "Microsoft revenue", document_id="msft", company="Microsoft", year=2024),
        ],
        [[1.0, 0.0], [1.0, 0.0]],
    )

    hits = vector_store.query([1.0, 0.0], top_k=5, where={"company": {"$in": ["Apple"]}})

    assert [hit.chunk_id for hit in hits] == ["a1"]


def test_delete_document_removes_only_its_chunks(vector_store):
    vector_store.add_chunks(
        [
            _chunk("a1", "Apple revenue", document_id="apple"),
            _chunk("m1", "Microsoft revenue", document_id="msft"),
        ],
        [[1.0, 0.0], [0.0, 1.0]],
    )

    assert vector_store.delete_document("apple") == 1
    assert vector_store.count() == 1
    assert not vector_store.document_exists("apple")
    assert vector_store.document_exists("msft")


def test_find_by_checksum_powers_duplicate_detection(vector_store):
    vector_store.add_chunks(
        [_chunk("a1", "Apple revenue", document_id="apple", checksum="deadbeef")],
        [[1.0, 0.0]],
    )

    assert vector_store.find_by_checksum("deadbeef") == "apple"
    assert vector_store.find_by_checksum("unknown") is None


def test_upsert_replaces_rather_than_duplicates(vector_store):
    chunk = _chunk("a1", "First version")
    vector_store.add_chunks([chunk], [[1.0, 0.0]])
    vector_store.add_chunks([_chunk("a1", "Second version")], [[1.0, 0.0]])

    assert vector_store.count() == 1
    assert vector_store.query([1.0, 0.0], top_k=1)[0].text == "Second version"


def test_list_documents_summarises_the_corpus(vector_store):
    vector_store.add_chunks(
        [
            _chunk("a1", "one", document_id="apple", company="Apple", year=2024, page_number=1),
            _chunk("a2", "two", document_id="apple", company="Apple", year=2024, page_number=7),
        ],
        [[1.0, 0.0], [0.0, 1.0]],
    )

    documents = vector_store.list_documents()

    assert len(documents) == 1
    assert documents[0]["chunk_count"] == 2
    assert documents[0]["page_count"] == 7
    assert documents[0]["company"] == "Apple"


def test_null_metadata_is_dropped_before_storage(vector_store):
    # Chroma rejects null metadata values, so they must be stripped.
    vector_store.add_chunks([_chunk("a1", "text", report_type=None)], [[1.0, 0.0]])

    assert "report_type" not in vector_store.query([1.0, 0.0], top_k=1)[0].metadata


# --- where-clause construction ------------------------------------------- #


def test_where_clause_is_none_when_unfiltered():
    assert build_where_clause(RetrievalFilters()) is None


def test_single_filter_needs_no_and_wrapper():
    clause = build_where_clause(RetrievalFilters(companies=["Apple"]))

    assert clause == {"company": {"$in": ["Apple"]}}


def test_multiple_filters_are_combined_with_and():
    clause = build_where_clause(RetrievalFilters(companies=["Apple"], years=[2024]))

    assert clause == {
        "$and": [{"company": {"$in": ["Apple"]}}, {"year": {"$in": [2024]}}]
    }
