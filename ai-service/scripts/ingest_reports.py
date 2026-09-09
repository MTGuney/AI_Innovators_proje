"""Index downloaded reports into ChromaDB.

Usage:
    python scripts/ingest_reports.py                       # index data/raw
    python scripts/ingest_reports.py --path data/raw/X.txt # index one file
    python scripts/ingest_reports.py --force               # re-index everything
    python scripts/ingest_reports.py --list                # show what is indexed
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow `python scripts/ingest_reports.py` from the service root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.models.schemas import IngestResult  # noqa: E402
from app.rag.ingestion import (  # noqa: E402
    DocumentDescriptor,
    IngestionPipeline,
    summarise,
)
from app.rag.vector_store import get_vector_store  # noqa: E402

logger = logging.getLogger("ingest_reports")


def print_results(results: list[IngestResult]) -> None:
    """Show one line per document, then the totals."""
    for result in results:
        marker = {"indexed": "+", "skipped_duplicate": "=", "failed": "!"}[result.status]
        detail = (
            f"{result.chunk_count} chunks, {result.page_count} pages"
            if result.status == "indexed"
            else (result.message or "")
        )
        print(f" {marker} {result.source_file:<48} {result.status:<18} {detail}")

    totals = summarise(results)
    print(
        f"\n{totals['indexed']} indexed, {totals['skipped_duplicate']} already present, "
        f"{totals['failed']} failed -- {totals['chunks']} chunks written."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Index financial reports into ChromaDB.")
    parser.add_argument(
        "--path",
        type=Path,
        help="A single file, or a directory (default: data/raw).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-index even if the content is already present.",
    )
    parser.add_argument("--company", help="Override the company name.")
    parser.add_argument("--year", type=int, help="Override the fiscal year.")
    parser.add_argument(
        "--report-type", default="10-K", help="Report type label (default: 10-K)."
    )
    parser.add_argument(
        "--list", action="store_true", help="List indexed documents and exit."
    )
    args = parser.parse_args()

    configure_logging()
    settings.ensure_directories()

    if args.list:
        documents = get_vector_store().list_documents()
        if not documents:
            print("The index is empty.")
            return 0
        print(f"{len(documents)} indexed document(s):\n")
        for document in documents:
            print(
                f"  {document['document_id']:<28} "
                f"{str(document.get('company')):<18} "
                f"{str(document.get('year')):<6} "
                f"{document['chunk_count']:>4} chunks   {document.get('source_file')}"
            )
        return 0

    target = args.path or (settings.data_dir / "raw")
    if not target.is_absolute():
        target = (Path.cwd() / target).resolve()

    if not target.exists():
        logger.error(
            "Nothing to index at %s. Run scripts/download_sec_reports.py first.", target
        )
        return 1

    pipeline = IngestionPipeline()
    descriptor = DocumentDescriptor(
        company=args.company, year=args.year, report_type=args.report_type
    )

    if target.is_file():
        results = [pipeline.ingest_file(target, descriptor, force=args.force)]
    else:
        # Directory mode relies on filename metadata, so per-document company
        # and year are inferred rather than forced from the CLI.
        results = pipeline.ingest_directory(target, force=args.force)

    print_results(results)
    return 0 if any(r.status != "failed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
