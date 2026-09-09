"""Numeric grounding: catching figures that are not in the retrieved context."""

from __future__ import annotations

import pytest

from app.services.grounding import check_numeric_grounding

CONTEXT = (
    "[S1] Acme 10-K 2024 | page 12\n"
    "Total revenue for fiscal 2024 was $4,820 million, an increase of 12.4% "
    "compared with $4,288 million in fiscal 2023.\n"
    "Total net sales | 416,161 | 391,035 | 383,285"
)


def test_figures_present_in_context_are_grounded():
    report = check_numeric_grounding(
        "Revenue was $4,820 million, up 12.4% from $4,288 million.", CONTEXT
    )

    assert report.is_fully_grounded
    assert report.checked == 3


def test_invented_figures_are_reported():
    report = check_numeric_grounding("Revenue was $245.5 billion in 2025.", CONTEXT)

    assert not report.is_fully_grounded
    assert "245.5" in report.unsupported


def test_grouping_separators_do_not_matter():
    # "4820" in the answer must match "4,820" in the context.
    assert check_numeric_grounding("Revenue was 4820 million.", CONTEXT).is_fully_grounded


def test_table_figures_count_as_context():
    report = check_numeric_grounding("Total net sales were 416,161.", CONTEXT)

    assert report.is_fully_grounded


def test_years_are_not_policed():
    # Years appear in many forms and are not the figures worth checking.
    report = check_numeric_grounding("In 2019 the company restructured.", CONTEXT)

    assert report.checked == 0
    assert report.is_fully_grounded


def test_small_integers_are_ignored():
    report = check_numeric_grounding("There are 3 reportable segments.", CONTEXT)

    assert report.checked == 0


def test_decimals_are_always_checked_however_small():
    report = check_numeric_grounding("Margin improved by 1.7 points.", CONTEXT)

    assert report.checked == 1
    assert report.unsupported == ["1.7"]


def test_citation_tags_are_not_treated_as_figures():
    report = check_numeric_grounding("Revenue rose [S1] and margins held [S2].", CONTEXT)

    assert report.checked == 0


def test_each_figure_is_reported_once():
    report = check_numeric_grounding(
        "Revenue was 999.9 million; yes, 999.9 million.", CONTEXT
    )

    assert report.unsupported == ["999.9"]


def test_unsupported_ratio_is_reported():
    report = check_numeric_grounding("Revenue was 4,820 and 999.9 million.", CONTEXT)

    assert report.checked == 2
    assert report.unsupported_ratio == pytest.approx(0.5)


@pytest.mark.parametrize("answer,context", [("", CONTEXT), ("Revenue was 1.2", "")])
def test_empty_inputs_are_safe(answer, context):
    assert check_numeric_grounding(answer, context).checked == 0
