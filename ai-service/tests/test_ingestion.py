"""Ingestion pipeline: metadata inference, indexing and duplicate detection."""

from __future__ import annotations

from app.rag.ingestion import DocumentDescriptor, IngestionPipeline


def build_pipeline(vector_store, fake_embedder) -> IngestionPipeline:
    return IngestionPipeline(vector_store=vector_store, embedder=fake_embedder)


def test_indexes_a_report_and_infers_metadata_from_the_filename(
    sample_report, vector_store, fake_embedder
):
    result = build_pipeline(vector_store, fake_embedder).ingest_file(sample_report)

    assert result.status == "indexed"
    assert result.chunk_count > 0
    # Filename convention: TICKER_Company-Name_TYPE_YEAR
    assert result.company == "Acme Corp"
    assert result.year == 2024
    assert result.report_type == "10-K"
    assert result.document_id == "acme-corp-2024-10-k"
    assert vector_store.count() == result.chunk_count


def test_identical_content_is_not_embedded_twice(
    sample_report, vector_store, fake_embedder
):
    pipeline = build_pipeline(vector_store, fake_embedder)
    first = pipeline.ingest_file(sample_report)
    calls_after_first = fake_embedder.calls

    second = pipeline.ingest_file(sample_report)

    assert second.status == "skipped_duplicate"
    assert second.document_id == first.document_id
    # The whole point of the checksum check: no embedding work is repeated.
    assert fake_embedder.calls == calls_after_first
    assert vector_store.count() == first.chunk_count


def test_force_reindexes_without_duplicating_chunks(
    sample_report, vector_store, fake_embedder
):
    pipeline = build_pipeline(vector_store, fake_embedder)
    first = pipeline.ingest_file(sample_report)

    second = pipeline.ingest_file(sample_report, force=True)

    assert second.status == "indexed"
    assert vector_store.count() == first.chunk_count


def test_changed_content_replaces_the_previous_version(
    sample_report, vector_store, fake_embedder
):
    pipeline = build_pipeline(vector_store, fake_embedder)
    first = pipeline.ingest_file(sample_report)

    sample_report.write_text(
        "Item 7. MD&A\nTotal revenue for fiscal 2024 was $5,000 million.",
        encoding="utf-8",
    )
    second = pipeline.ingest_file(sample_report)

    assert second.status == "indexed"
    assert second.document_id == first.document_id
    # Same logical document: old chunks are removed, not left orphaned.
    assert vector_store.count() == second.chunk_count


def test_explicit_descriptor_overrides_filename_inference(
    sample_report, vector_store, fake_embedder
):
    result = build_pipeline(vector_store, fake_embedder).ingest_file(
        sample_report,
        descriptor=DocumentDescriptor(
            company="Acme Corporation", year=2023, report_type="Annual Report"
        ),
    )

    assert result.company == "Acme Corporation"
    assert result.year == 2023
    assert result.report_type == "Annual Report"


def test_unsupported_file_fails_without_raising(tmp_path, vector_store, fake_embedder):
    path = tmp_path / "notes.docx"
    path.write_bytes(b"binary")

    result = build_pipeline(vector_store, fake_embedder).ingest_file(path)

    # A bad file must not abort a batch of otherwise-good documents.
    assert result.status == "failed"
    assert "Unsupported file type" in (result.message or "")
    assert vector_store.count() == 0


def test_directory_ingestion_skips_unsupported_files(
    tmp_path, sample_report, vector_store, fake_embedder
):
    # Unsupported extensions are not candidates at all, so they are never
    # attempted and never reported as failures.
    (tmp_path / "notes.docx").write_bytes(b"binary")

    results = build_pipeline(vector_store, fake_embedder).ingest_directory(tmp_path)

    assert [result.source_file for result in results] == [sample_report.name]


def test_directory_ingestion_continues_past_a_failing_document(
    tmp_path, sample_report, vector_store, fake_embedder
):
    # A supported file with no extractable text fails, but must not abort the batch.
    (tmp_path / "EMPTY_Empty-Co_10-K_2024.txt").write_text("   \n\n ", encoding="utf-8")

    results = build_pipeline(vector_store, fake_embedder).ingest_directory(tmp_path)

    statuses = {result.source_file: result.status for result in results}
    assert statuses["EMPTY_Empty-Co_10-K_2024.txt"] == "failed"
    assert statuses[sample_report.name] == "indexed"


def test_delete_document_clears_the_index(sample_report, vector_store, fake_embedder):
    pipeline = build_pipeline(vector_store, fake_embedder)
    result = pipeline.ingest_file(sample_report)

    assert pipeline.delete_document(result.document_id) == result.chunk_count
    assert vector_store.count() == 0
