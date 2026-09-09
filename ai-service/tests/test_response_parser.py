"""Parsing the model's structured reply.

Small local models are inconsistent about JSON, so the parser must degrade
gracefully rather than fail a request.
"""

from __future__ import annotations

from app.services.response_parser import parse_structured_answer


def test_parses_clean_json():
    parsed = parse_structured_answer(
        '{"answer": "Revenue grew 12.4% [S1].",'
        ' "key_points": ["Revenue was $4,820m [S1]"],'
        ' "sources": ["S1", "S2"], "confidence": "high"}'
    )

    assert parsed.answer == "Revenue grew 12.4% [S1]."
    assert parsed.key_points == ["Revenue was $4,820m [S1]"]
    assert parsed.source_tags == ["S1", "S2"]
    assert parsed.confidence == "high"
    assert parsed.used_fallback is False


def test_strips_markdown_fences():
    parsed = parse_structured_answer(
        '```json\n{"answer": "Operating income rose.", "sources": ["S1"]}\n```'
    )

    assert parsed.answer == "Operating income rose."
    assert parsed.source_tags == ["S1"]
    assert parsed.used_fallback is False


def test_extracts_json_embedded_in_prose():
    parsed = parse_structured_answer(
        'Here is the result:\n{"answer": "Revenue grew.", "sources": ["S2"]}\nHope that helps.'
    )

    assert parsed.answer == "Revenue grew."
    assert parsed.source_tags == ["S2"]


def test_braces_inside_strings_do_not_break_extraction():
    parsed = parse_structured_answer('{"answer": "Uses {braces} inside.", "sources": []}')

    assert parsed.answer == "Uses {braces} inside."


def test_falls_back_to_raw_text_when_not_json():
    parsed = parse_structured_answer("Revenue increased by 12.4% according to [S1].")

    assert parsed.used_fallback is True
    assert "12.4%" in parsed.answer
    # Inline tags are still salvaged so the answer keeps its provenance.
    assert parsed.source_tags == ["S1"]
    assert parsed.confidence == "low"


def test_recovers_inline_tags_when_sources_field_is_empty():
    parsed = parse_structured_answer(
        '{"answer": "Revenue grew [S3] and margin improved [S1].", "sources": []}'
    )

    assert parsed.source_tags == ["S3", "S1"]


def test_accepts_loose_tag_shapes():
    parsed = parse_structured_answer(
        '{"answer": "Grew.", "sources": "S1, [s2]", "confidence": "HIGH"}'
    )

    assert parsed.source_tags == ["S1", "S2"]
    assert parsed.confidence == "high"


def test_invalid_confidence_becomes_low():
    parsed = parse_structured_answer('{"answer": "Grew.", "confidence": "certain"}')

    assert parsed.confidence == "low"


def test_empty_reply_is_handled():
    parsed = parse_structured_answer("")

    assert parsed.answer == ""
    assert parsed.used_fallback is True


def test_json_without_answer_falls_back_to_raw_text():
    parsed = parse_structured_answer('{"key_points": ["a"], "sources": ["S1"]}')

    assert parsed.used_fallback is True
