"""Logging setup for the AI service.

Deliberately logs *about* documents (names, counts, timings) and never their
contents, so indexing a confidential report does not scatter its text through
the log files.
"""

from __future__ import annotations

import logging
import sys

from app.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str | None = None) -> None:
    """Install a single stdout handler for the whole process."""
    resolved = (level or settings.log_level).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, resolved, logging.INFO))

    # These libraries are extremely chatty at INFO and add no signal here.
    for noisy in ("httpx", "httpcore", "chromadb", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
