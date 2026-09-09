"""Turn a file on disk into clean, page-addressable text.

Supported inputs: PDF, plain text/Markdown, and HTML (SEC EDGAR filings are
distributed as HTML). Everything downstream works with `DocumentPage` objects,
so citations can always name a page even for formats that have no real
pagination -- see `PSEUDO_PAGE_CHARS`.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

PDF_SUFFIXES = {".pdf"}
TEXT_SUFFIXES = {".txt", ".md", ".text"}
HTML_SUFFIXES = {".html", ".htm"}
SUPPORTED_SUFFIXES = PDF_SUFFIXES | TEXT_SUFFIXES | HTML_SUFFIXES

# Flowing formats (TXT/HTML) have no pages, so we slice them into fixed-size
# "pages" purely to give citations a stable, human-checkable anchor.
PSEUDO_PAGE_CHARS = 3000

# Lines that are nothing but a page number / rule -- pure noise for retrieval.
_NOISE_LINE = re.compile(r"^\s*(?:page\s*)?[-–—|]*\s*\d{1,4}\s*[-–—|]*\s*$", re.I)
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_MULTI_SPACE = re.compile(r"[ \t ]{2,}")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class DocumentError(Exception):
    """Base class for document-loading failures."""

    user_message = "Unable to process this document. Please check the file format."


class UnsupportedDocumentError(DocumentError):
    """The file extension is not one we can parse."""

    def __init__(self, suffix: str) -> None:
        self.suffix = suffix
        super().__init__(f"Unsupported document type: {suffix or '(no extension)'}")

    @property
    def user_message(self) -> str:  # type: ignore[override]
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        return f"Unsupported file type {self.suffix!r}. Supported formats: {supported}."


class DocumentParseError(DocumentError):
    """The file matched a supported type but could not be read."""


@dataclass(frozen=True)
class DocumentPage:
    """One page (real for PDFs, synthetic for flowing formats)."""

    page_number: int
    text: str


@dataclass(frozen=True)
class LoadedDocument:
    """A parsed document, ready for chunking."""

    source_file: str
    pages: tuple[DocumentPage, ...]
    checksum: str
    detected_title: str | None = None

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def char_count(self) -> int:
        return sum(len(page.text) for page in self.pages)


def load_document(path: str | Path) -> LoadedDocument:
    """Parse `path` into cleaned pages. Raises `DocumentError` on failure."""
    file_path = Path(path)
    if not file_path.is_file():
        raise DocumentParseError(f"File not found: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedDocumentError(suffix)

    raw_bytes = file_path.read_bytes()
    checksum = hashlib.sha256(raw_bytes).hexdigest()

    if suffix in PDF_SUFFIXES:
        pages, title = _load_pdf(file_path)
    elif suffix in HTML_SUFFIXES:
        pages, title = _load_html(raw_bytes)
    else:
        pages, title = _load_text(raw_bytes)

    kept = tuple(page for page in pages if page.text.strip())
    if not kept:
        raise DocumentParseError(
            f"No extractable text found in {file_path.name}. "
            "Scanned/image-only documents are not supported."
        )

    logger.info(
        "Loaded %s: %d page(s), %d chars", file_path.name, len(kept),
        sum(len(p.text) for p in kept),
    )
    return LoadedDocument(
        source_file=file_path.name,
        pages=kept,
        checksum=checksum,
        detected_title=title,
    )


# ---------------------------------------------------------------------- #
# Format-specific readers
# ---------------------------------------------------------------------- #


def _load_pdf(file_path: Path) -> tuple[list[DocumentPage], str | None]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise DocumentParseError("pypdf is required to read PDF files.") from exc

    try:
        reader = PdfReader(str(file_path))
        pages = [
            DocumentPage(page_number=index, text=clean_text(page.extract_text() or ""))
            for index, page in enumerate(reader.pages, start=1)
        ]
    except Exception as exc:  # noqa: BLE001 - pypdf raises many error types
        raise DocumentParseError(f"Could not read PDF {file_path.name}: {exc}") from exc

    title = None
    try:
        title = (reader.metadata or {}).get("/Title") or None
    except Exception:  # noqa: BLE001 - metadata is optional and often malformed
        title = None
    return pages, (str(title).strip() or None if title else None)


def _load_html(raw_bytes: bytes) -> tuple[list[DocumentPage], str | None]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise DocumentParseError("beautifulsoup4 is required to read HTML.") from exc

    markup = raw_bytes.decode("utf-8", errors="replace")
    soup = BeautifulSoup(markup, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else None

    text = clean_text(html_to_text(soup))
    return _paginate(text), (title or None)


def html_to_text(soup) -> str:
    """Render parsed HTML as text, keeping tables readable.

    Financial statements live in tables, so dropping them would remove exactly
    the figures the assistant is asked about. Each row is flattened to a
    pipe-delimited line, which survives chunking and stays quotable.
    """
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    for table in soup.find_all("table"):
        table.replace_with(_table_to_text(table))

    return soup.get_text(separator="\n")


def _table_to_text(table) -> str:
    """Flatten one table into `label | value | value` lines."""
    lines: list[str] = []

    for row in table.find_all("tr"):
        cells = [
            " ".join(cell.get_text(separator=" ").split())
            for cell in row.find_all(["td", "th"])
        ]
        # Filings pad tables with spacer cells and stray currency symbols;
        # dropping them keeps a row to its label and its numbers.
        cells = [cell for cell in cells if cell and cell not in {"$", "%", ")", "("}]
        if cells:
            lines.append(" | ".join(cells))

    return "\n" + "\n".join(lines) + "\n" if lines else ""


def _load_text(raw_bytes: bytes) -> tuple[list[DocumentPage], str | None]:
    text = clean_text(raw_bytes.decode("utf-8", errors="replace"))
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    title = first_line.strip()[:200] or None
    return _paginate(text), title


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


def clean_text(text: str) -> str:
    """Normalise whitespace and drop page-number noise, preserving structure."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub(" ", text)
    # Re-join words broken across a line by a hyphen ("reve-\nnue" -> "revenue").
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    lines = [
        "" if _NOISE_LINE.match(line) else _MULTI_SPACE.sub(" ", line).rstrip()
        for line in text.split("\n")
    ]
    return _MULTI_NEWLINE.sub("\n\n", "\n".join(lines)).strip()


def _paginate(text: str, page_chars: int = PSEUDO_PAGE_CHARS) -> list[DocumentPage]:
    """Slice flowing text into synthetic pages of roughly `page_chars`.

    Page numbers are only useful as citation anchors if the pages are of
    comparable size, so oversized blocks are broken down rather than emitted
    whole. HTML-to-text conversion routinely yields blocks of tens of
    thousands of characters, which would otherwise become a single "page".
    """
    if not text:
        return []

    pages: list[DocumentPage] = []
    buffer: list[str] = []
    size = 0

    for paragraph in text.split("\n\n"):
        for block in _fit_blocks(paragraph, page_chars):
            if size and size + len(block) > page_chars:
                pages.append(
                    DocumentPage(page_number=len(pages) + 1, text="\n\n".join(buffer))
                )
                buffer, size = [], 0
            buffer.append(block)
            size += len(block) + 2

    if buffer:
        pages.append(DocumentPage(page_number=len(pages) + 1, text="\n\n".join(buffer)))
    return pages


def _fit_blocks(paragraph: str, limit: int) -> list[str]:
    """Break an oversized paragraph into blocks of at most `limit` characters.

    Splits on line boundaries first, and only hard-cuts a single line that is
    itself longer than the limit.
    """
    if len(paragraph) <= limit:
        return [paragraph]

    blocks: list[str] = []
    current: list[str] = []
    size = 0

    for line in paragraph.split("\n"):
        pieces = (
            [line]
            if len(line) <= limit
            else [line[i : i + limit] for i in range(0, len(line), limit)]
        )
        for piece in pieces:
            if size and size + len(piece) > limit:
                blocks.append("\n".join(current))
                current, size = [], 0
            current.append(piece)
            size += len(piece) + 1

    if current:
        blocks.append("\n".join(current))
    return blocks
