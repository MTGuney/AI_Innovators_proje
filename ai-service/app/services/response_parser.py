"""Parse and validate the structured JSON the LLM is asked to return.

Small local models occasionally wrap JSON in prose or markdown fences, or drop
a field. Rather than failing the request we degrade gracefully: extract what is
there, fall back to treating the raw text as the answer, and always report
whether the fallback was used so the caller can lower its confidence.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from app.models.schemas import Confidence
from app.rag.retriever import parse_tag

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_INLINE_TAG = re.compile(r"\[\s*S\s*(\d+)\s*\]", re.IGNORECASE)
_VALID_CONFIDENCE = {"high", "medium", "low"}


@dataclass
class ParsedAnswer:
    """Normalised view of the model's reply."""

    answer: str
    key_points: list[str] = field(default_factory=list)
    source_tags: list[str] = field(default_factory=list)
    confidence: Confidence = "low"
    used_fallback: bool = False


def parse_structured_answer(raw: str) -> ParsedAnswer:
    """Best-effort conversion of a raw completion into `ParsedAnswer`."""
    text = (raw or "").strip()
    if not text:
        return ParsedAnswer(answer="", confidence="low", used_fallback=True)

    payload = _extract_json_object(text)
    if payload is None:
        logger.warning("LLM reply was not valid JSON; falling back to raw text.")
        return _fallback(text)

    answer = _as_text(payload.get("answer"))
    if not answer:
        logger.warning("LLM JSON had no usable 'answer' field; using raw text.")
        return _fallback(text)

    tags = _normalise_tags(payload.get("sources"))
    # Models often cite inline but leave "sources" empty -- recover those too.
    tags = _merge(tags, _inline_tags(answer))

    key_points = [
        point for point in (_as_text(item) for item in _as_list(payload.get("key_points")))
        if point
    ]
    for point in key_points:
        tags = _merge(tags, _inline_tags(point))

    confidence = str(payload.get("confidence", "")).strip().lower()
    return ParsedAnswer(
        answer=answer,
        key_points=key_points,
        source_tags=tags,
        confidence=confidence if confidence in _VALID_CONFIDENCE else "low",  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------- #
# Internals
# ---------------------------------------------------------------------- #


def _fallback(text: str) -> ParsedAnswer:
    """Treat the whole reply as prose, salvaging any inline citations."""
    return ParsedAnswer(
        answer=_FENCE.sub("", text).strip(),
        source_tags=_inline_tags(text),
        confidence="low",
        used_fallback=True,
    )


def _extract_json_object(text: str) -> dict | None:
    """Return the first balanced JSON object in `text`, if it parses."""
    stripped = _FENCE.sub("", text).strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    # Scan for a balanced {...} span, ignoring braces inside strings.
    start = stripped.find("{")
    while start != -1:
        candidate = _balanced_span(stripped, start)
        if candidate:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        start = stripped.find("{", start + 1)
    return None


def _balanced_span(text: str, start: int) -> str | None:
    """Extract the substring from `start` to its matching closing brace."""
    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _inline_tags(text: str) -> list[str]:
    """Collect [S1]-style tags in order of first appearance."""
    return _merge([], [f"S{match.group(1)}" for match in _INLINE_TAG.finditer(text)])


def _normalise_tags(value: object) -> list[str]:
    """Accept ["S1"], "S1, S2", or [{"tag": "S1"}] and normalise to ["S1"]."""
    tags: list[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            item = item.get("tag") or item.get("id") or item.get("source") or ""
        for piece in re.split(r"[,\s]+", str(item)):
            tag = parse_tag(piece)
            if tag:
                tags.append(tag)
    return _merge([], tags)


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (str, dict)):
        return [value]
    return list(value) if hasattr(value, "__iter__") else [value]


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return " ".join(_as_text(item) for item in value).strip()
    return str(value).strip()


def _merge(existing: list[str], incoming: list[str]) -> list[str]:
    """Append new tags, preserving order and removing duplicates."""
    merged = list(existing)
    seen = set(merged)
    for tag in incoming:
        if tag not in seen:
            merged.append(tag)
            seen.add(tag)
    return merged
