"""Split loaded documents into embeddable chunks.

Design decisions, kept deliberately simple for the MVP:

  * Chunks never span pages. A chunk therefore always maps to exactly one
    page number, which keeps citations honest and checkable.
  * Splitting is recursive over progressively weaker separators (paragraph ->
    line -> sentence -> word), so paragraphs and table rows stay intact
    whenever they fit.
  * The nearest preceding heading (e.g. "Item 1A. Risk Factors") is tracked and
    stored as `section` metadata, and prepended to the chunk text so a
    retrieved fragment carries the context it was written under.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Sequence

from app.config import settings
from app.rag.document_loader import LoadedDocument

logger = logging.getLogger(__name__)

# Weakest-last: we only fall through when a fragment is still too large.
SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ")

# SEC filings are organised as "PART II" / "Item 7A. Quantitative Disclosures".
# Item headings carry the real meaning, so they are matched separately from the
# much less informative PART dividers.
_ITEM_HEADING = re.compile(r"^\s*item\s+\d{1,2}\s*[abc]?\s*[.:\-]?(\s|$)", re.I)
_PART_HEADING = re.compile(r"^\s*part\s+[ivx]{1,4}\b", re.I)
_MAX_HEADING_CHARS = 120


@dataclass(frozen=True)
class Chunk:
    """One embeddable unit of text plus the metadata that makes it citable."""

    chunk_id: str
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


def chunk_document(
    document: LoadedDocument,
    document_id: str,
    base_metadata: dict[str, object] | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    """Chunk every page of `document`, carrying metadata through unchanged."""
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap
    if overlap >= size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    shared = dict(base_metadata or {})
    chunks: list[Chunk] = []
    running_index = 0
    current_section: str | None = None

    for page in document.pages:
        # Segment on item headings first so no chunk ever straddles two
        # sections -- a chunk that mixed "Risk Factors" with "MD&A" would be
        # mislabelled whichever heading we picked for it.
        for heading, body_text in split_sections(page.text):
            # Fall back to a generic heading for documents with no item
            # structure; otherwise the previous section carries over.
            current_section = heading or pick_section(body_text) or current_section
            section = current_section

            for piece in split_text(body_text, size, overlap):
                body = piece.strip()
                if not body:
                    continue
                # Prepend the section so an isolated fragment still reads in
                # context, both for the reader and for the embedding.
                text = (
                    f"[{section}]\n{body}"
                    if section and section not in body
                    else body
                )
                metadata: dict[str, object] = {
                    **shared,
                    "document_id": document_id,
                    "source_file": document.source_file,
                    "page_number": page.page_number,
                    "chunk_index": running_index,
                }
                if section:
                    metadata["section"] = section
                chunks.append(
                    Chunk(
                        chunk_id=f"{document_id}::p{page.page_number}::c{running_index}",
                        text=text,
                        metadata=metadata,
                    )
                )
                running_index += 1

    logger.info(
        "Chunked %s into %d chunk(s) (size=%d overlap=%d)",
        document.source_file, len(chunks), size, overlap,
    )
    return chunks


def split_text(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: Sequence[str] = SEPARATORS,
) -> list[str]:
    """Recursively split `text` into pieces of at most `chunk_size` characters."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    fragments = _fragment(text, chunk_size, separators)
    return _merge(fragments, chunk_size, chunk_overlap)


# ---------------------------------------------------------------------- #
# Internals
# ---------------------------------------------------------------------- #


def _fragment(text: str, chunk_size: int, separators: Sequence[str]) -> list[str]:
    """Break text into atoms no larger than `chunk_size`, weakest separator last."""
    if not separators:
        # No separator left: hard-cut. Only reachable for pathological input
        # such as an unbroken run of characters longer than a chunk.
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    separator, *rest = separators
    pieces = [p for p in text.split(separator) if p.strip()]

    fragments: list[str] = []
    for index, piece in enumerate(pieces):
        # Keep the separator so re-joined chunks read naturally.
        restored = piece + separator if index < len(pieces) - 1 else piece
        if len(restored) <= chunk_size:
            fragments.append(restored)
        else:
            fragments.extend(_fragment(restored, chunk_size, rest))
    return fragments


def _merge(fragments: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    """Greedily pack fragments into chunks, repeating a tail as overlap."""
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0

    for fragment in fragments:
        if size + len(fragment) > chunk_size and buffer:
            chunks.append("".join(buffer).strip())
            buffer, size = _overlap_tail(buffer, chunk_overlap)
        buffer.append(fragment)
        size += len(fragment)

    if buffer:
        tail = "".join(buffer).strip()
        if tail:
            chunks.append(tail)
    return [c for c in chunks if c]


def _overlap_tail(buffer: list[str], chunk_overlap: int) -> tuple[list[str], int]:
    """Return the trailing fragments worth at most `chunk_overlap` characters."""
    if chunk_overlap <= 0:
        return [], 0
    tail: list[str] = []
    size = 0
    for fragment in reversed(buffer):
        if size + len(fragment) > chunk_overlap:
            break
        tail.insert(0, fragment)
        size += len(fragment)
    return tail, size


def find_headings(text: str) -> list[tuple[str, bool]]:
    """Return `(heading, is_item_heading)` pairs from `text`, in document order.

    Two cues cover most filings and annual reports: the SEC "Item 7." / "PART
    II" convention, and short ALL-CAPS lines.
    """
    headings: list[tuple[str, bool]] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line or len(line) > _MAX_HEADING_CHARS:
            continue
        if _ITEM_HEADING.match(line):
            headings.append((line.rstrip(".:"), True))
        elif _PART_HEADING.match(line) or (
            len(line) > 3 and line == line.upper() and any(c.isalpha() for c in line)
        ):
            headings.append((line.rstrip(".:"), False))
    return headings


def split_sections(text: str) -> list[tuple[str | None, str]]:
    """Split `text` at item-heading boundaries into `(heading, body)` segments.

    The heading line stays with its body so the section title is embedded
    alongside the content it introduces. Text before the first heading is
    returned with a heading of None.
    """
    lines = text.split("\n")
    segments: list[tuple[str | None, list[str]]] = []
    current: tuple[str | None, list[str]] = (None, [])

    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) <= _MAX_HEADING_CHARS and _ITEM_HEADING.match(
            stripped
        ):
            if current[1]:
                segments.append(current)
            current = (stripped.rstrip(".:"), [line])
        else:
            current[1].append(line)

    if current[1]:
        segments.append(current)

    # Filings repeat the current Item as a running page header, so the same
    # section arrives as many consecutive segments. Merge them back together or
    # every page boundary would start a new chunk mid-sentence.
    merged: list[tuple[str | None, list[str]]] = []
    for heading, body in segments:
        if merged and _same_section(merged[-1][0], heading):
            merged[-1][1].extend(body)
        else:
            merged.append((heading, list(body)))

    return [
        (heading, text_body)
        for heading, body in merged
        if (text_body := "\n".join(body).strip())
    ]


def _same_section(left: str | None, right: str | None) -> bool:
    """True when two headings name the same Item (e.g. "Item 1A" vs "ITEM 1A.")."""
    if left is None or right is None:
        return False
    return _item_key(left) == _item_key(right)


def _item_key(heading: str) -> str:
    """Normalise "Item 1A. Risk Factors" -> "1A" for comparison."""
    match = re.match(r"\s*item\s+(\d{1,2})\s*([abc]?)", heading, re.I)
    return f"{match.group(1)}{match.group(2).upper()}" if match else heading.lower()


def pick_section(text: str) -> str | None:
    """Choose the heading that best describes `text`, or None if it has none."""
    headings = find_headings(text)
    if not headings:
        return None
    items = [heading for heading, is_item in headings if is_item]
    return items[-1] if items else headings[-1][0]
