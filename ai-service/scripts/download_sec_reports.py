"""Download real annual reports (10-K filings) from SEC EDGAR.

EDGAR is the *primary* corpus source because it needs no credentials, is freely
redistributable, and provides genuine multi-company, multi-year report prose --
which is what a RAG system needs (isolated numeric rows are not enough).

`download_kaggle_reports.py` adds a second source for what EDGAR cannot give:
annual reports as PDFs, which carry real page numbers. EDGAR serves HTML, which
has no pages, so those citations rest on synthetic pagination.

Usage:
    python scripts/download_sec_reports.py --years 2
    python scripts/download_sec_reports.py --tickers AAPL MSFT --full

Set SEC_USER_AGENT in `.env` first: EDGAR requires a descriptive User-Agent
with a contact address and will reject anonymous traffic.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

# Allow `python scripts/download_sec_reports.py` from the service root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402
from app.rag.document_loader import clean_text  # noqa: E402
from app.rag.document_loader import html_to_text as shared_html_to_text  # noqa: E402

logger = logging.getLogger("download_sec_reports")

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

# EDGAR asks for no more than 10 requests/second; stay well under it.
REQUEST_DELAY_SECONDS = 0.25


@dataclass(frozen=True)
class Company:
    ticker: str
    name: str
    cik: int


# A spread of well-known filers, chosen so the comparison feature has natural
# pairs (Apple/Microsoft, Tesla/Ford) as in the project specification.
DEFAULT_COMPANIES: tuple[Company, ...] = (
    Company("AAPL", "Apple Inc", 320193),
    Company("MSFT", "Microsoft Corp", 789019),
    Company("TSLA", "Tesla Inc", 1318605),
    Company("F", "Ford Motor Co", 37996),
    Company("NVDA", "NVIDIA Corp", 1045810),
)

# The narrative sections worth indexing. Financial-statement exhibits are mostly
# tables that survive plain-text extraction poorly, so they are skipped by
# default; pass --full to keep the entire filing.
KEY_ITEMS: tuple[str, ...] = ("1", "1A", "7", "7A")

_ITEM_MARKER = re.compile(
    r"^\s*item\s+(\d{1,2}\s*[abc]?)\s*[.:\-]?\s*(.{0,90})$",
    re.IGNORECASE | re.MULTILINE,
)
# A real section has substance; anything shorter is a table-of-contents entry.
MIN_SECTION_CHARS = 800
# If section extraction keeps almost nothing, the filing's layout defeated the
# heuristics -- index the whole document rather than throwing content away.
MIN_EXTRACTION_RATIO = 0.05


class DownloadError(RuntimeError):
    """A filing could not be retrieved."""


def build_client(user_agent: str) -> httpx.Client:
    """EDGAR rejects requests without a descriptive, contactable User-Agent."""
    return httpx.Client(
        headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
        timeout=httpx.Timeout(60.0),
        follow_redirects=True,
    )


def fetch_filings(
    client: httpx.Client, company: Company, form: str, limit: int
) -> list[dict[str, str]]:
    """Return metadata for the most recent `limit` filings of `form`."""
    url = SUBMISSIONS_URL.format(cik=company.cik)
    response = client.get(url)
    response.raise_for_status()
    recent = (response.json().get("filings") or {}).get("recent") or {}

    forms = recent.get("form") or []
    filings: list[dict[str, str]] = []
    for index, filed_form in enumerate(forms):
        if filed_form != form:
            continue
        report_date = (recent.get("reportDate") or [""] * len(forms))[index]
        filings.append(
            {
                "accession": (recent.get("accessionNumber") or [])[index].replace("-", ""),
                "document": (recent.get("primaryDocument") or [])[index],
                "report_date": report_date,
                "filing_date": (recent.get("filingDate") or [""] * len(forms))[index],
                "fiscal_year": (report_date or "")[:4],
            }
        )
        if len(filings) >= limit:
            break
    return filings


def download_filing(
    client: httpx.Client, company: Company, filing: dict[str, str]
) -> str:
    """Fetch one filing document and return it as cleaned plain text."""
    url = ARCHIVE_URL.format(
        cik=company.cik, accession=filing["accession"], document=filing["document"]
    )
    logger.info("Fetching %s %s -> %s", company.ticker, filing["fiscal_year"], url)
    response = client.get(url)
    if response.status_code != 200:
        raise DownloadError(f"HTTP {response.status_code} for {url}")
    return html_to_text(response.text)


def html_to_text(markup: str) -> str:
    """Strip an EDGAR HTML filing down to readable text.

    Tables are flattened rather than dropped: a 10-K keeps its revenue and
    income figures in tables, so discarding them would leave the corpus unable
    to answer the questions this system exists to answer.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(markup, "lxml")
    return clean_text(shared_html_to_text(soup))


def _item_runs(text: str) -> list[tuple[str, int, int]]:
    """Group Item markers into `(item, start, end)` runs.

    Filers repeat the current Item as a running page header, so a single
    section produces dozens of markers. Consecutive markers naming the same
    Item therefore belong to one section and must be merged -- otherwise every
    "section" is only one page long.
    """
    markers = list(_ITEM_MARKER.finditer(text))
    runs: list[tuple[str, int, int]] = []

    index = 0
    while index < len(markers):
        item = re.sub(r"\s+", "", markers[index].group(1)).upper()
        last = index
        while (
            last + 1 < len(markers)
            and re.sub(r"\s+", "", markers[last + 1].group(1)).upper() == item
        ):
            last += 1
        end = markers[last + 1].start() if last + 1 < len(markers) else len(text)
        runs.append((item, markers[index].start(), end))
        index = last + 1

    return runs


def extract_key_sections(text: str, wanted: tuple[str, ...] = KEY_ITEMS) -> str:
    """Keep only the substantive Item sections named in `wanted`.

    Each Item is named several times in a filing (contents page,
    cross-references, running headers, the section itself), so we keep the
    longest run per Item -- the real section rather than a pointer to it.
    """
    runs = [run for run in _item_runs(text) if run[0] in wanted]
    if not runs:
        return text

    best: dict[str, str] = {}
    for item, start, end in runs:
        section = text[start:end].strip()
        if len(section) < MIN_SECTION_CHARS:
            continue
        if item not in best or len(section) > len(best[item]):
            best[item] = section

    if not best:
        return text

    ordered = sorted(best.items(), key=lambda entry: wanted.index(entry[0]))
    extracted = "\n\n".join(section for _, section in ordered)

    if len(extracted) < len(text) * MIN_EXTRACTION_RATIO:
        logger.warning(
            "Section extraction kept only %d of %d chars; keeping the full filing.",
            len(extracted), len(text),
        )
        return text
    return extracted


def save_report(
    output_dir: Path, company: Company, filing: dict[str, str], text: str
) -> Path:
    """Write the report using the `TICKER_Company-Name_TYPE_YEAR` convention
    that the ingestion pipeline parses metadata from."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = company.name.replace(" ", "-")
    path = output_dir / f"{company.ticker}_{safe_name}_10-K_{filing['fiscal_year']}.txt"
    path.write_text(text, encoding="utf-8")
    logger.info("Saved %s (%d chars)", path.name, len(text))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download 10-K filings from SEC EDGAR.")
    parser.add_argument(
        "--tickers", nargs="*", help="Tickers to download (default: a built-in set)."
    )
    parser.add_argument(
        "--years", type=int, default=2, help="Filings per company (default: 2)."
    )
    parser.add_argument("--form", default="10-K", help="Filing type (default: 10-K).")
    parser.add_argument(
        "--out",
        type=Path,
        default=settings.data_dir / "raw",
        help="Output directory (default: data/raw).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Keep the whole filing instead of only the key Item sections.",
    )
    args = parser.parse_args()

    configure_logging()

    if "example.com" in settings.sec_user_agent:
        logger.error(
            "Set SEC_USER_AGENT in .env to '<project> <your-email>' before "
            "downloading. EDGAR rejects anonymous requests."
        )
        return 2

    selected = DEFAULT_COMPANIES
    if args.tickers:
        wanted = {ticker.upper() for ticker in args.tickers}
        selected = tuple(c for c in DEFAULT_COMPANIES if c.ticker.upper() in wanted)
        missing = wanted - {c.ticker.upper() for c in selected}
        if missing:
            logger.error(
                "Unknown ticker(s): %s. Add them to DEFAULT_COMPANIES with their CIK.",
                ", ".join(sorted(missing)),
            )
            return 2

    saved = 0
    failed = 0
    with build_client(settings.sec_user_agent) as client:
        for company in selected:
            try:
                filings = fetch_filings(client, company, args.form, args.years)
            except Exception as exc:  # noqa: BLE001 - report and continue
                logger.error("Could not list filings for %s: %s", company.ticker, exc)
                failed += 1
                continue

            if not filings:
                logger.warning("No %s filings found for %s", args.form, company.ticker)

            for filing in filings:
                time.sleep(REQUEST_DELAY_SECONDS)
                try:
                    text = download_filing(client, company, filing)
                except Exception as exc:  # noqa: BLE001 - report and continue
                    logger.error(
                        "Failed to download %s %s: %s",
                        company.ticker, filing.get("fiscal_year"), exc,
                    )
                    failed += 1
                    continue

                if not args.full:
                    trimmed = extract_key_sections(text)
                    logger.info(
                        "  key sections: %d -> %d chars", len(text), len(trimmed)
                    )
                    text = trimmed

                save_report(args.out, company, filing, text)
                saved += 1

    logger.info("Done: %d report(s) saved, %d failure(s). Output: %s", saved, failed, args.out)
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
