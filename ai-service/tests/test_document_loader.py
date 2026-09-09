"""Document loading, cleaning and synthetic pagination."""

from __future__ import annotations

import pytest

from app.rag.document_loader import (
    PSEUDO_PAGE_CHARS,
    DocumentParseError,
    UnsupportedDocumentError,
    clean_text,
    load_document,
)


def test_loads_text_report_with_pages(sample_report):
    document = load_document(sample_report)

    assert document.source_file == "ACME_Acme-Corp_10-K_2024.txt"
    assert document.page_count >= 1
    assert "4,820 million" in document.pages[0].text
    assert len(document.checksum) == 64


def test_checksum_is_content_addressed(tmp_path, sample_report):
    copy = tmp_path / "copy.txt"
    copy.write_text(sample_report.read_text(encoding="utf-8"), encoding="utf-8")

    # Duplicate detection depends on identical content hashing identically.
    assert load_document(copy).checksum == load_document(sample_report).checksum


def test_rejects_unsupported_extension(tmp_path):
    path = tmp_path / "report.docx"
    path.write_bytes(b"binary")

    with pytest.raises(UnsupportedDocumentError) as error:
        load_document(path)

    assert ".pdf" in error.value.user_message


def test_rejects_empty_document(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("   \n\n  ", encoding="utf-8")

    with pytest.raises(DocumentParseError):
        load_document(path)


def test_html_tags_are_stripped(tmp_path):
    path = tmp_path / "filing.html"
    path.write_text(
        "<html><head><title>Acme 10-K</title><style>b{}</style></head>"
        "<body><script>x=1</script><p>Revenue rose to $4,820 million.</p></body></html>",
        encoding="utf-8",
    )

    document = load_document(path)
    body = document.pages[0].text

    assert "Revenue rose to $4,820 million." in body
    assert "x=1" not in body and "b{}" not in body
    assert document.detected_title == "Acme 10-K"


def test_pages_are_bounded_so_citations_stay_useful(tmp_path):
    # HTML-to-text output routinely yields a single enormous block; it must
    # still be split, or a page number would point at 30k characters.
    path = tmp_path / "long.txt"
    path.write_text("word " * 20000, encoding="utf-8")

    document = load_document(path)

    assert document.page_count > 1
    assert all(len(page.text) <= PSEUDO_PAGE_CHARS for page in document.pages)


def test_clean_text_drops_page_number_noise_and_rejoins_hyphens():
    cleaned = clean_text("Total reve-\nnue grew.\n\n  12  \n\nOperating income rose.")

    assert "revenue grew" in cleaned
    assert "\n12\n" not in cleaned
