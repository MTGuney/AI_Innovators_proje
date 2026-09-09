"""Document ingestion: load -> clean -> chunk -> embed -> store.

The pipeline is idempotent. A file whose content has already been indexed is
skipped (matched on a SHA-256 checksum), and re-ingesting a changed file under
the same document id replaces the previous chunks instead of duplicating them.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.models.schemas import IngestResult
from app.rag.chunker import chunk_document
from app.rag.document_loader import (
    SUPPORTED_SUFFIXES,
    DocumentError,
    load_document,
)
from app.rag.embeddings import Embedder, get_embedder
from app.rag.vector_store import VectorStore, get_vector_store

logger = logging.getLogger(__name__)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_YEAR_IN_NAME = re.compile(r"(19|20)\d{2}")


@dataclass(frozen=True)
class DocumentDescriptor:
    """Caller-supplied metadata about a document being ingested."""

    company: str | None = None
    year: int | None = None
    report_type: str | None = None
    title: str | None = None
    document_id: str | None = None


class IngestionPipeline:
    """Turns files on disk into searchable, citable chunks."""

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._store = vector_store or get_vector_store()
        self._embedder = embedder or get_embedder()

    def ingest_file(
        self,
        path: str | Path,
        descriptor: DocumentDescriptor | None = None,
        force: bool = False,
    ) -> IngestResult:
        """Index a single document. Never raises for expected failures."""
        file_path = Path(path)
        descriptor = descriptor or DocumentDescriptor()

        try:
            document = load_document(file_path)
        except DocumentError as exc:
            logger.warning("Ingestion failed for %s: %s", file_path.name, exc)
            return IngestResult(
                document_id=descriptor.document_id or _slug(file_path.stem),
                source_file=file_path.name,
                status="failed",
                message=exc.user_message,
            )

        company = descriptor.company or _infer_company(file_path)
        year = descriptor.year or _infer_year(file_path)
        report_type = descriptor.report_type or _infer_report_type(file_path)
        # A structured title ("NVIDIA Corp 10-K 2025") beats the first line of
        # the file, which after section extraction is just a heading.
        title = (
            descriptor.title
            or _build_title(company, report_type, year)
            or document.detected_title
            or file_path.stem
        )
        document_id = descriptor.document_id or _build_document_id(
            company, year, report_type, file_path.stem
        )

        # --- duplicate detection -------------------------------------- #
        if not force:
            existing = self._store.find_by_checksum(document.checksum)
            if existing:
                logger.info(
                    "Skipping %s: identical content already indexed as %s",
                    file_path.name, existing,
                )
                return IngestResult(
                    document_id=existing,
                    source_file=document.source_file,
                    status="skipped_duplicate",
                    company=company,
                    year=year,
                    report_type=report_type,
                    title=title,
                    message="This document is already indexed.",
                )

        # A same-id document with different content is a new revision: replace.
        replaced = self._store.delete_document(document_id)
        if replaced:
            logger.info("Replacing %d existing chunk(s) for %s", replaced, document_id)

        base_metadata: dict[str, Any] = {
            "company": company,
            "year": year,
            "report_type": report_type,
            "title": title,
            "checksum": document.checksum,
        }
        chunks = chunk_document(document, document_id, base_metadata)
        if not chunks:
            return IngestResult(
                document_id=document_id,
                source_file=document.source_file,
                status="failed",
                message="No text could be extracted from this document.",
            )

        embeddings = self._embedder.embed_documents([chunk.text for chunk in chunks])
        stored = self._store.add_chunks(chunks, embeddings)

        logger.info(
            "Indexed %s as %s (%d chunks, %d pages)",
            document.source_file, document_id, stored, document.page_count,
        )
        return IngestResult(
            document_id=document_id,
            source_file=document.source_file,
            status="indexed",
            chunk_count=stored,
            page_count=document.page_count,
            char_count=document.char_count,
            company=company,
            year=year,
            report_type=report_type,
            title=title,
        )

    def ingest_paths(
        self,
        paths: Iterable[Path],
        descriptor: DocumentDescriptor | None = None,
        force: bool = False,
    ) -> list[IngestResult]:
        """Index many files, continuing past individual failures."""
        return [self.ingest_file(path, descriptor, force) for path in paths]

    def ingest_directory(
        self,
        directory: str | Path,
        force: bool = False,
        recursive: bool = True,
    ) -> list[IngestResult]:
        """Index every supported document under `directory`."""
        root = Path(directory)
        if not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {root}")
        pattern = "**/*" if recursive else "*"
        files = sorted(
            path
            for path in root.glob(pattern)
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        )
        logger.info("Found %d supported document(s) under %s", len(files), root)
        return self.ingest_paths(files, force=force)

    def delete_document(self, document_id: str) -> int:
        """Remove a document from the index. Returns chunks deleted."""
        return self._store.delete_document(document_id)


# ---------------------------------------------------------------------- #
# Metadata helpers
# ---------------------------------------------------------------------- #


def _slug(value: str) -> str:
    return _SLUG_STRIP.sub("-", value.lower()).strip("-") or "document"


def _build_document_id(
    company: str | None,
    year: int | None,
    report_type: str | None,
    stem: str,
) -> str:
    """Stable, human-readable id so re-ingesting a file updates it in place.

    Company is required to build a semantic id -- without it we would risk
    collapsing unrelated documents that merely share a year.
    """
    if not company:
        return _slug(stem)
    parts = [company, str(year) if year else None, report_type]
    return _slug("-".join(part for part in parts if part))


def _infer_year(path: Path) -> int | None:
    """Pull a fiscal year out of the filename, e.g. `AAPL_10-K_2024.html`."""
    match = _YEAR_IN_NAME.search(path.stem)
    return int(match.group(0)) if match else None


def _build_title(company: str | None, report_type: str | None, year: int | None) -> str | None:
    """Compose a citation-friendly document title from known metadata."""
    if not company:
        return None
    parts = [company, report_type, str(year) if year else None]
    return " ".join(part for part in parts if part)


def _infer_report_type(path: Path) -> str | None:
    """Report type from the `TICKER_Company-Name_TYPE_YEAR` convention."""
    parts = path.stem.split("_")
    return parts[2].strip() or None if len(parts) == 4 else None


def _infer_company(path: Path) -> str | None:
    """Company from the `TICKER_Company-Name_TYPE_YEAR` convention used by the
    dataset downloader. Arbitrary filenames yield None rather than a guess."""
    parts = path.stem.split("_")
    if len(parts) == 4 and parts[1]:
        return parts[1].replace("-", " ").strip() or None
    return None


def summarise(results: Sequence[IngestResult]) -> dict[str, int]:
    """Aggregate ingestion outcomes for logs and CLI output."""
    summary = {"indexed": 0, "skipped_duplicate": 0, "failed": 0, "chunks": 0}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
        summary["chunks"] += result.chunk_count
    return summary


_pipeline: IngestionPipeline | None = None


def get_ingestion_pipeline() -> IngestionPipeline:
    """Return the process-wide ingestion pipeline (FastAPI dependency)."""
    global _pipeline
    if _pipeline is None:
        _pipeline = IngestionPipeline()
    return _pipeline
