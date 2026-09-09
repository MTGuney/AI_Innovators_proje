"""Document ingestion and index-management endpoints.

The .NET backend owns report *metadata* in PostgreSQL; this service owns the
*vector index*. These endpoints are how the backend keeps the two in step.
"""

from __future__ import annotations

import logging
import shutil
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.config import settings
from app.models.schemas import (
    IndexedDocument,
    IndexStats,
    IngestRequest,
    IngestResult,
)
from app.rag.document_loader import SUPPORTED_SUFFIXES
from app.rag.ingestion import DocumentDescriptor, IngestionPipeline, get_ingestion_pipeline
from app.rag.vector_store import VectorStore, get_vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/ingest", response_model=IngestResult)
def ingest_document(
    request: IngestRequest,
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
) -> IngestResult:
    """Index a document that already exists on the AI service's filesystem."""
    path = Path(request.path)
    if not path.is_absolute():
        path = (settings.data_dir / path).resolve()

    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document not found: {request.path}",
        )

    return pipeline.ingest_file(
        path,
        descriptor=DocumentDescriptor(
            company=request.company,
            year=request.year,
            report_type=request.report_type,
            title=request.title,
            document_id=request.document_id,
        ),
        force=request.force,
    )


@router.post("/upload", response_model=IngestResult)
def upload_document(
    file: UploadFile = File(...),
    company: str | None = Form(default=None),
    year: int | None = Form(default=None),
    report_type: str | None = Form(default=None),
    title: str | None = Form(default=None),
    force: bool = Form(default=False),
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
) -> IngestResult:
    """Accept an uploaded report, store it, and index it."""
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A filename is required."
        )

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{suffix}'. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_SUFFIXES))}."
            ),
        )

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    destination = settings.upload_dir / filename
    try:
        with destination.open("wb") as target:
            shutil.copyfileobj(file.file, target)
    finally:
        file.file.close()

    logger.info("Stored upload %s (%d bytes)", filename, destination.stat().st_size)
    return pipeline.ingest_file(
        destination,
        descriptor=DocumentDescriptor(
            company=company, year=year, report_type=report_type, title=title
        ),
        force=force,
    )


@router.get("", response_model=list[IndexedDocument])
def list_documents(
    store: VectorStore = Depends(get_vector_store),
) -> list[IndexedDocument]:
    """List every document currently present in the vector index."""
    return [IndexedDocument(**_as_document(doc)) for doc in store.list_documents()]


@router.get("/stats", response_model=IndexStats)
def index_stats(store: VectorStore = Depends(get_vector_store)) -> IndexStats:
    """Aggregates that back the dashboard."""
    documents = store.list_documents()
    years = sorted({int(d["year"]) for d in documents if d.get("year") is not None})
    year_counts = Counter(
        str(int(d["year"])) for d in documents if d.get("year") is not None
    )
    return IndexStats(
        total_documents=len(documents),
        total_chunks=store.count(),
        companies=sorted({str(d["company"]) for d in documents if d.get("company")}),
        years=years,
        report_types=sorted(
            {str(d["report_type"]) for d in documents if d.get("report_type")}
        ),
        documents_by_year=dict(sorted(year_counts.items())),
    )


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id: str,
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
) -> dict[str, object]:
    """Remove a document and all of its chunks from the index."""
    deleted = pipeline.delete_document(document_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No indexed document with id '{document_id}'.",
        )
    return {"document_id": document_id, "deleted_chunks": deleted}


def _as_document(raw: dict) -> dict:
    """Coerce loose vector-store metadata into the response model's shape."""
    year = raw.get("year")
    return {
        "document_id": raw.get("document_id", ""),
        "source_file": raw.get("source_file"),
        "title": raw.get("title"),
        "company": raw.get("company"),
        "year": int(year) if isinstance(year, (int, float)) else None,
        "report_type": raw.get("report_type"),
        "chunk_count": raw.get("chunk_count", 0),
        "page_count": raw.get("page_count", 0),
    }
