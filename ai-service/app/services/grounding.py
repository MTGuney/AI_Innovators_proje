"""Verify that figures in an answer actually appear in the retrieved context.

The prompt forbids inventing numbers, but a small local model will still do it
when the context is thin. This is the mechanical check behind the specification's
"validate structured responses before sending them to the frontend": any figure
that cannot be found in the passages the model was shown is reported, and the
answer's confidence is capped accordingly.

The check is deliberately conservative -- it is a caution flag, not a verdict.
A model may legitimately restate "416,161" (millions) as "$416.2 billion", which
this cannot recognise, so callers should surface findings as "not found verbatim"
rather than as proof of fabrication.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Numbers as they appear in financial prose: 4,820 / 12.4 / 416,161.5
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Citation tags ([S1]) and percent-of-total style small integers are not claims.
_CITATION_TAG = re.compile(r"\[\s*S\s*\d+\s*\]", re.IGNORECASE)

# Bare integers below this are ordinals, list markers or segment counts.
MIN_CHECKED_VALUE = 100.0

# Four-digit values in this range are almost always years, which appear in the
# context in many forms and are not the figures worth policing.
YEAR_RANGE = (1900, 2100)


@dataclass
class GroundingReport:
    """Which figures in an answer could be located in the context."""

    checked: int = 0
    unsupported: list[str] = field(default_factory=list)

    @property
    def is_fully_grounded(self) -> bool:
        return not self.unsupported

    @property
    def unsupported_ratio(self) -> float:
        return len(self.unsupported) / self.checked if self.checked else 0.0


def check_numeric_grounding(answer: str, context: str) -> GroundingReport:
    """Report figures in `answer` that do not occur in `context`."""
    if not answer or not context:
        return GroundingReport()

    context_numbers = {_normalise(match.group(0)) for match in _NUMBER.finditer(context)}
    # Also index digits-only forms so "4,820" in context matches "4820" in the
    # answer, and vice versa.
    context_numbers |= {number.replace(",", "") for number in context_numbers}

    report = GroundingReport()
    seen: set[str] = set()

    for raw in _NUMBER.findall(_CITATION_TAG.sub(" ", answer)):
        normalised = _normalise(raw)
        if not _is_worth_checking(normalised) or normalised in seen:
            continue

        seen.add(normalised)
        report.checked += 1

        if normalised not in context_numbers and normalised.replace(",", "") not in context_numbers:
            report.unsupported.append(raw)

    if report.unsupported:
        logger.warning(
            "Answer contains %d figure(s) not present in the retrieved context: %s",
            len(report.unsupported),
            ", ".join(report.unsupported[:5]),
        )
    return report


def _normalise(number: str) -> str:
    """Strip grouping separators and trailing zeros so forms compare equal."""
    cleaned = number.replace(",", "").rstrip(".")
    if "." in cleaned:
        cleaned = cleaned.rstrip("0").rstrip(".")
    return cleaned or "0"


def _is_worth_checking(number: str) -> bool:
    """Skip values too small or too year-like to be meaningful claims."""
    try:
        value = float(number)
    except ValueError:
        return False

    # Decimals are precise claims (percentages, ratios) whatever their size.
    if "." in number:
        return True
    if YEAR_RANGE[0] <= value <= YEAR_RANGE[1] and len(number) == 4:
        return False
    return value >= MIN_CHECKED_VALUE
