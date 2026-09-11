"""Download annual reports from a Kaggle dataset.

This is a *second* corpus source, alongside `download_sec_reports.py`. EDGAR
remains the primary one -- it needs no credentials and is freely
redistributable -- but every EDGAR filing arrives as HTML, which has no pages,
so the whole corpus currently relies on synthetic pagination. A dataset of
annual report PDFs exercises the `pypdf` path instead and gives citations
*real* page numbers, which is the one provenance claim the HTML corpus cannot
make honestly.

Usage:
    python scripts/download_kaggle_reports.py --inspect      # look before leaping
    python scripts/download_kaggle_reports.py                # download + normalise
    python scripts/download_kaggle_reports.py --limit 20     # take a subset

Credentials are required even for public datasets. Either:
  * place `kaggle.json` in %USERPROFILE%\\.kaggle\\ (Kaggle -> Settings -> API
    -> "Create New Token"), or
  * set KAGGLE_USERNAME and KAGGLE_KEY in `.env`.

Output files follow the `TICKER_Company-Name_TYPE_YEAR` convention that
`app.rag.ingestion` parses metadata from, so `ingest_reports.py` picks them up
with no special-casing.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Allow `python scripts/download_kaggle_reports.py` from the service root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402

logger = logging.getLogger("download_kaggle_reports")

# Kaggle ships datasets as a single zip; keep it out of data/raw so that a
# re-download never looks like a corpus document to the ingestion pipeline.
CACHE_DIRNAME = "kaggle"

# Report-type label for everything this dataset yields. The corpus is annual
# reports, but they are not all SEC 10-Ks (the dataset spans non-US filers), so
# calling them 10-K would put a false claim into every citation.
REPORT_TYPE = "annual-report"

# A PDF whose pages yield almost no text is image-only: pypdf will "succeed"
# and return blanks, which would silently poison the index with empty chunks.
MIN_CHARS_PER_PAGE = 200
# Pages sampled per PDF when probing for a text layer.
PROBE_PAGES = 5

# The dataset names its files `EXCHANGE_TICKER_YEAR.pdf`.
_DATASET_NAME = re.compile(
    r"^(?P<exchange>[A-Z]{2,8})_(?P<ticker>[A-Z0-9.]{1,8})_(?P<year>(?:19|20)\d{2})$"
)

# Ticker -> the company name written into every citation.
#
# AAPL and MSFT deliberately reuse the exact spelling `download_sec_reports.py`
# writes. Company is a metadata *string*, so "Apple Inc" from EDGAR and
# "Apple Inc." from here would be two companies to the retriever: filters would
# silently see half the reports and a comparison would answer from one year.
KNOWN_COMPANIES: dict[str, str] = {
    "AAPL": "Apple Inc",
    "MSFT": "Microsoft Corp",
    "CWN": "Crown Resorts",
    "DMP": "Dominos Pizza Enterprises",
    "CZR": "Caesars Entertainment",
    "MCD": "McDonalds Corp",
}

# Files that ignore the naming convention. Listing them explicitly beats
# loosening the regex, which would start mis-reading well-formed names.
FILENAME_OVERRIDES: dict[str, tuple[str, str, int]] = {
    # "ar20" is adidas' own shorthand for the 2020 annual report.
    "annual-report-adidas-ar20": ("ADS", "adidas AG", 2020),
}


class KaggleError(RuntimeError):
    """Raised when the dataset cannot be retrieved."""


@dataclass(frozen=True)
class PlannedReport:
    """One source PDF and the name it will be stored under."""

    source: Path
    ticker: str
    company: str
    year: int

    @property
    def filename(self) -> str:
        # `_infer_company` / `_infer_report_type` split the stem on "_" and
        # require exactly four parts, so no field may contain an underscore.
        # Spaces become hyphens because `_infer_company` reverses exactly that.
        company = self.company.replace(" ", "-")
        return (
            f"{self.ticker}_{company}_{REPORT_TYPE}_{self.year}"
            f"{self.source.suffix.lower()}"
        )


# ---------------------------------------------------------------------- #
# Kaggle access
# ---------------------------------------------------------------------- #


def authenticate():
    """Return an authenticated Kaggle API client.

    `import kaggle` calls `authenticate()` at *import* time and raises OSError
    when no credentials exist, so the import has to live in here -- a
    module-level import would make `--help` fail on a machine without a token.
    """
    if settings.kaggle_username and settings.kaggle_key:
        # The client only reads credentials from the environment or kaggle.json,
        # so values coming from .env have to be promoted before the import.
        os.environ.setdefault("KAGGLE_USERNAME", settings.kaggle_username)
        os.environ.setdefault("KAGGLE_KEY", settings.kaggle_key)

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except OSError as exc:
        raise KaggleError(
            "No Kaggle credentials found. Create a token at "
            "https://www.kaggle.com/settings -> API -> 'Create New Token', save it "
            f"as {Path.home() / '.kaggle' / 'kaggle.json'}, or set KAGGLE_USERNAME "
            "and KAGGLE_KEY in .env."
        ) from exc
    except ImportError as exc:
        raise KaggleError(
            "The 'kaggle' package is not installed. Run: pip install -r requirements.txt"
        ) from exc

    api = KaggleApi()
    try:
        api.authenticate()
    except OSError as exc:
        raise KaggleError(
            "Kaggle credentials were found but rejected. Re-download kaggle.json "
            "from https://www.kaggle.com/settings -> API."
        ) from exc
    return api


def download_dataset(dataset: str, cache_dir: Path, force: bool = False) -> Path:
    """Fetch `dataset` into `cache_dir` and return the extracted directory."""
    target = cache_dir / dataset.replace("/", "__")
    marker = target / ".complete"

    if marker.exists() and not force:
        logger.info("Using cached dataset at %s (pass --force to re-download).", target)
        return target

    api = authenticate()
    target.mkdir(parents=True, exist_ok=True)

    # Report the size before pulling it. A mistyped slug can point at a
    # multi-gigabyte dataset, and the download reports progress but cannot be
    # sized from the progress bar alone until it is already underway.
    try:
        entries = api.dataset_list_files(dataset).files
        total = sum(int(getattr(entry, "totalBytes", 0) or 0) for entry in entries)
        logger.info(
            "%s: %d file(s), %.1f MiB", dataset, len(entries), total / 1_048_576
        )
    except Exception as exc:  # noqa: BLE001 - informational only
        logger.debug("Could not size %s before download: %s", dataset, exc)

    logger.info("Downloading %s -- this can take a while on a large dataset.", dataset)
    try:
        # unzip=False so a partial extraction cannot be mistaken for a complete
        # one; we unzip ourselves and only then write the marker.
        api.dataset_download_files(dataset, path=str(target), unzip=False, quiet=False)
    except Exception as exc:  # noqa: BLE001 - the API raises a wide range
        raise KaggleError(f"Download failed for {dataset!r}: {exc}") from exc

    archives = sorted(target.glob("*.zip"))
    for archive in archives:
        logger.info("Extracting %s", archive.name)
        try:
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(target)
        except zipfile.BadZipFile as exc:
            raise KaggleError(f"Downloaded archive is corrupt: {archive}") from exc
        archive.unlink()

    marker.write_text("ok", encoding="utf-8")
    return target


# ---------------------------------------------------------------------- #
# Inspection
# ---------------------------------------------------------------------- #


def probe_pdf(path: Path) -> tuple[int, float]:
    """Return `(page_count, mean chars per sampled page)` for a PDF.

    A scanned filing extracts to nothing. Finding that out here is much cheaper
    than discovering it as empty chunks after a 45-minute embedding run.
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001 - malformed PDFs raise freely
        logger.debug("Could not read %s: %s", path.name, exc)
        return 0, 0.0

    pages = reader.pages
    if not pages:
        return 0, 0.0

    sampled = list(pages)[:PROBE_PAGES]
    total = 0
    for page in sampled:
        try:
            total += len(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - one bad page must not abort the probe
            continue
    return len(pages), total / len(sampled)


def inspect(root: Path, sample: int = 8) -> None:
    """Print what the dataset actually contains, without changing anything."""
    files = [path for path in root.rglob("*") if path.is_file() and path.name != ".complete"]
    if not files:
        print(f"Nothing found under {root}")
        return

    total_bytes = sum(path.stat().st_size for path in files)
    extensions = Counter(path.suffix.lower() or "(none)" for path in files)

    print(f"\nRoot: {root}")
    print(f"Files: {len(files)}   Total size: {total_bytes / 1_048_576:.1f} MiB\n")

    print("By extension:")
    for suffix, count in extensions.most_common():
        print(f"  {suffix:<10} {count:>6}")

    directories = sorted({path.parent.relative_to(root).as_posix() or "." for path in files})
    print(f"\nDirectories ({len(directories)}):")
    for directory in directories[:15]:
        print(f"  {directory}")
    if len(directories) > 15:
        print(f"  ... and {len(directories) - 15} more")

    print(f"\nSample filenames:")
    for path in files[:sample]:
        print(f"  {path.relative_to(root).as_posix()}")

    pdfs = [path for path in files if path.suffix.lower() == ".pdf"]
    if pdfs:
        print(f"\nText-layer probe ({min(sample, len(pdfs))} of {len(pdfs)} PDFs):")
        for path in pdfs[:sample]:
            pages, mean_chars = probe_pdf(path)
            verdict = "OK" if mean_chars >= MIN_CHARS_PER_PAGE else "NO TEXT LAYER"
            print(f"  {path.name[:52]:<54} {pages:>4}p  {mean_chars:>7.0f} ch/p  {verdict}")


# ---------------------------------------------------------------------- #
# Normalisation
# ---------------------------------------------------------------------- #


def parse_source_name(path: Path) -> PlannedReport | None:
    """Resolve a dataset filename into a fully attributed report.

    Returns None when the file cannot be attributed with certainty. Nothing is
    guessed: a wrong company or year here would be baked into every citation
    the report ever produces, and a confidently mislabelled source is worse
    than an absent one.
    """
    stem = path.stem

    override = FILENAME_OVERRIDES.get(stem)
    if override:
        ticker, company, year = override
        return PlannedReport(source=path, ticker=ticker, company=company, year=year)

    match = _DATASET_NAME.match(stem)
    if not match:
        return None

    ticker = match.group("ticker").upper()
    company = KNOWN_COMPANIES.get(ticker)
    if not company:
        # The exchange prefix is not a company name, and a bare ticker in a
        # citation tells the reader nothing, so an unmapped ticker is skipped.
        return None

    return PlannedReport(
        source=path, ticker=ticker, company=company, year=int(match.group("year"))
    )


def plan(root: Path, limit: int | None = None) -> tuple[list[PlannedReport], list[Path]]:
    """Map every usable PDF to its destination name.

    Returns `(planned, rejected)`; see `parse_source_name` for why rejection is
    preferred over a placeholder name.
    """
    pdfs = sorted(path for path in root.rglob("*.pdf") if path.is_file())
    planned: list[PlannedReport] = []
    rejected: list[Path] = []

    for path in pdfs:
        report = parse_source_name(path)
        if report is None:
            rejected.append(path)
            continue
        planned.append(report)
        if limit and len(planned) >= limit:
            break

    return planned, rejected


def copy_reports(
    planned: list[PlannedReport], out_dir: Path, dry_run: bool = False
) -> int:
    """Copy planned reports into the corpus directory under their new names."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    for report in planned:
        destination = out_dir / report.filename
        if dry_run:
            print(f"  {report.source.name[:48]:<50} -> {destination.name}")
            continue
        if destination.exists() and destination.stat().st_size == report.source.stat().st_size:
            logger.debug("Already present, skipping: %s", destination.name)
            continue
        shutil.copy2(report.source, destination)
        written += 1

    return written


# ---------------------------------------------------------------------- #
# CLI
# ---------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download annual reports from a Kaggle dataset into data/raw."
    )
    parser.add_argument(
        "--dataset",
        default=settings.kaggle_dataset,
        help=f"Kaggle dataset slug (default: {settings.kaggle_dataset}).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=settings.data_dir / "raw",
        help="Output directory (default: data/raw).",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Download, then describe the contents and exit without copying.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the planned renames without writing anything.",
    )
    parser.add_argument("--limit", type=int, help="Stop after N reports.")
    parser.add_argument(
        "--force", action="store_true", help="Re-download even if cached."
    )
    args = parser.parse_args()

    configure_logging()
    settings.ensure_directories()

    cache_dir = settings.data_dir / CACHE_DIRNAME
    try:
        root = download_dataset(args.dataset, cache_dir, force=args.force)
    except KaggleError as exc:
        logger.error("%s", exc)
        return 2

    if args.inspect:
        inspect(root)
        return 0

    planned, rejected = plan(root, limit=args.limit)
    if rejected:
        logger.warning(
            "Skipped %d file(s) that could not be attributed: %s. Add the ticker to "
            "KNOWN_COMPANIES (or the filename to FILENAME_OVERRIDES) to include them.",
            len(rejected),
            ", ".join(path.name for path in rejected[:5]),
        )
    if not planned:
        logger.error(
            "No usable PDFs found under %s. Run with --inspect to see the layout.", root
        )
        return 1

    logger.info("Planned %d report(s).", len(planned))
    written = copy_reports(planned, args.out, dry_run=args.dry_run)

    if args.dry_run:
        logger.info("Dry run: nothing written.")
        return 0

    logger.info(
        "Done: %d report(s) copied to %s. Next: python scripts/ingest_reports.py",
        written, args.out,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
