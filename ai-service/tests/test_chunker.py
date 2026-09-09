"""Chunking: size limits, overlap, and section attribution."""

from __future__ import annotations

import pytest

from app.rag.chunker import chunk_document, pick_section, split_sections, split_text
from app.rag.document_loader import load_document


def test_split_text_respects_chunk_size():
    text = "\n\n".join(f"Paragraph {index} " + "word " * 60 for index in range(20))

    pieces = split_text(text, chunk_size=500, chunk_overlap=50)

    assert len(pieces) > 1
    assert all(len(piece) <= 500 for piece in pieces)


def test_split_text_returns_short_text_unchanged():
    assert split_text("Revenue grew 12%.", 500, 50) == ["Revenue grew 12%."]


def test_overlap_repeats_content_between_chunks():
    text = ". ".join(f"Sentence number {index} about revenue" for index in range(60))

    with_overlap = split_text(text, chunk_size=300, chunk_overlap=120)
    without_overlap = split_text(text, chunk_size=300, chunk_overlap=0)

    # Overlap duplicates a tail into the next chunk, so it needs more chunks.
    assert len(with_overlap) > len(without_overlap)


def test_unsplittable_run_is_hard_cut():
    pieces = split_text("x" * 1000, chunk_size=100, chunk_overlap=0)

    assert all(len(piece) <= 100 for piece in pieces)
    assert "".join(pieces) == "x" * 1000


def test_sections_split_on_item_headings():
    segments = split_sections(
        "Item 1. Business\nWe build robots.\n"
        "Item 1A. Risk Factors\nSupply chain risk is material."
    )

    assert [heading for heading, _ in segments] == [
        "Item 1. Business",
        "Item 1A. Risk Factors",
    ]
    assert "robots" in segments[0][1]
    assert "Supply chain" in segments[1][1]


def test_repeated_running_headers_do_not_fragment_a_section():
    # Filers repeat "Item 1A" as a page header; those are one section.
    segments = split_sections(
        "Item 1A. Risk Factors\nFirst page of risks.\n"
        "Item 1A\nSecond page of risks.\n"
        "Item 7. MD&A\nRevenue discussion."
    )

    assert len(segments) == 2
    assert "First page" in segments[0][1] and "Second page" in segments[0][1]


def test_item_headings_win_over_all_caps_lines():
    section = pick_section("ACME CORPORATION\nPART I\nItem 1A. Risk Factors\nrisks")

    assert section == "Item 1A. Risk Factors"


def test_chunk_document_carries_metadata_and_section(sample_report):
    document = load_document(sample_report)

    chunks = chunk_document(
        document,
        document_id="acme-2024",
        base_metadata={"company": "Acme Corp", "year": 2024, "checksum": "abc"},
        chunk_size=400,
        chunk_overlap=60,
    )

    assert chunks
    for chunk in chunks:
        metadata = chunk.metadata
        assert metadata["document_id"] == "acme-2024"
        assert metadata["company"] == "Acme Corp"
        assert metadata["year"] == 2024
        assert metadata["checksum"] == "abc"
        assert metadata["page_number"] >= 1
        assert metadata["source_file"] == document.source_file

    # Chunk indices are unique and sequential, so citations are addressable.
    indices = [chunk.metadata["chunk_index"] for chunk in chunks]
    assert indices == list(range(len(chunks)))

    # The risk passage must be attributed to the risk section, not to MD&A.
    risk_chunks = [c for c in chunks if "precision actuators" in c.text]
    assert risk_chunks
    assert risk_chunks[0].metadata["section"].startswith("Item 1A")


def test_chunk_ids_are_deterministic(sample_report):
    document = load_document(sample_report)
    kwargs = {"document_id": "acme-2024", "chunk_size": 400, "chunk_overlap": 60}

    first = chunk_document(document, **kwargs)
    second = chunk_document(document, **kwargs)

    # Re-ingesting a file must overwrite its chunks, not duplicate them.
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_overlap_must_be_smaller_than_chunk_size(sample_report):
    document = load_document(sample_report)

    with pytest.raises(ValueError):
        chunk_document(document, "acme-2024", chunk_size=200, chunk_overlap=200)
