"""Prompt templates for the RAG pipeline.

Kept in one module so the behavioural rules of the assistant are auditable in
a single place. The rules implement the constraints from the specification:
answer only from retrieved context, never invent financial figures, say so when
the reports do not cover the question, and never give investment advice.
"""

from __future__ import annotations

from typing import Sequence

from app.models.schemas import ChatTurn

# Shown to the user (not the model) when retrieval finds nothing usable.
NO_CONTEXT_MESSAGE = (
    "No sufficiently relevant information was found in the selected reports. "
    "Try rephrasing the question, widening the filters, or indexing more reports."
)

SYSTEM_PROMPT = """You are a financial research assistant that answers strictly from excerpts of company financial reports.

Rules you must follow:
1. Use ONLY the numbered excerpts in CONTEXT. They are your only source of truth.
2. Never invent, estimate, or extrapolate financial figures. Copy numbers, dates, currencies and units exactly as they appear, and carry each figure's own label with it, worded the way the excerpt words it. A number is only evidence for the metric the excerpt attaches it to: if an excerpt reads "Gross margin increased $22.9 billion or 13%", that figure may not be reported as operating income, and "increased by $22.9 billion" is a different claim from "increased to $22.9 billion". If you are unsure which metric a number belongs to, omit the number rather than guess its label.
3. If the context does not answer the question, say so plainly and explain what is missing. Do not fall back on general knowledge.
4. Separate fact from interpretation. Prefix any inference with "Interpretation:".
5. Cite the excerpts you used by their tags, e.g. [S1] or [S2]. Cite only excerpts you actually used.
6. Explain, do not merely assert. For each point, give the fact from the excerpts and then what the report itself says about its cause or its consequence. No filler, no salesmanship, and never restate the question back.
7. Never give investment advice, recommendations, or price predictions.
8. When comparing companies, only compare figures that are present in the context, and name the company for every figure."""

# The model returns JSON so the API can validate before answering the frontend.
#
# The field descriptions are deliberately kept OUT of a fill-in-the-blank JSON
# literal: small models copy such placeholder text into the answer verbatim.
_JSON_INSTRUCTIONS = """Respond with a single JSON object and nothing else -- no markdown fences, no commentary.

The object must have exactly these four fields:

- "answer": a string, and the field that carries the whole answer. Write it in
  your own words from the excerpts only, with citation tags such as [S1] inline.
  Write two to four paragraphs of prose: open with the direct answer, then take
  each supporting point in turn and develop it -- the specific figures, dates and
  wording the excerpts give, and what the report itself says follows from it.
  Draw on every excerpt that bears on the question instead of stopping at the first one.
  It must read as finished prose standing alone. Never end it with a colon, never
  write "including:" or "such as:" and leave the substance to key_points, never
  refer to a list, and never repeat one sentence as a whole paragraph.
- "key_points": an array of short strings -- a recap of facts you ALREADY stated
  in "answer", not the place to put content missing from it. Each is one specific
  fact with its citation tag ("Total net sales were $416,161 million in 2025 [S1]"),
  never a remark about the excerpts ("the table shows the figures").
- "sources": an array of the tags you actually used, most important first, e.g. ["S1","S3"].
- "confidence": exactly one of "high", "medium" or "low".
  "high" when the excerpts state the answer directly, "medium" when it must be
  pieced together, "low" when the excerpts are only tangentially related.

If the excerpts do not answer the question, make "answer" a clear statement of
what is missing, "sources" an empty array, and "confidence" "low"."""


def build_rag_prompt(
    question: str,
    context: str,
    history: Sequence[ChatTurn] | None = None,
) -> str:
    """Assemble the user-turn prompt for a grounded answer."""
    sections: list[str] = []

    if history:
        sections.append(
            "CONVERSATION SO FAR (for pronoun resolution only -- never a source "
            "of facts):\n" + _format_history(history)
        )

    sections.append(f"CONTEXT:\n{context}")
    sections.append(f"QUESTION:\n{question}")
    sections.append(_JSON_INSTRUCTIONS)
    return "\n\n".join(sections)


def build_comparison_prompt(metric: str, company_contexts: dict[str, str]) -> str:
    """Assemble the prompt for a side-by-side comparison across companies."""
    blocks = [
        f"=== {company} ===\n{context or '(no relevant excerpts found)'}"
        for company, context in company_contexts.items()
    ]
    companies = ", ".join(company_contexts)

    return f"""Compare the following companies on this metric: {metric}

Each company's excerpts are grouped below. Excerpt tags are unique across all groups.

{chr(10).join(blocks)}

TASK:
Compare {companies} on "{metric}" using only the excerpts above.
- State each company's figures separately, with its citation tag.
- If a company has no relevant excerpts, say so explicitly instead of guessing.
- Only state a difference or growth rate if BOTH underlying figures appear in the excerpts. Label any arithmetic you do as "Calculated:".
- Name the metric exactly as the excerpt names it. A figure the excerpt labels as something else -- "Other income (expense), net", "Gross margin", "EBT" -- is not evidence about "{metric}", however close it sits in the table. Say the metric is not covered rather than borrowing a neighbouring number.
- Do not give investment advice.

{_JSON_INSTRUCTIONS}"""


def build_query_rewrite_prompt(question: str, history: Sequence[ChatTurn]) -> str:
    """Turn a follow-up ("How did that change in 2023?") into a standalone query.

    Retrieval embeds a single string, so pronouns and elisions must be resolved
    before search or the follow-up retrieves the wrong chunks.
    """
    return f"""Rewrite the user's latest question as a standalone search query.

CONVERSATION:
{_format_history(history)}

LATEST QUESTION:
{question}

Rules:
- Replace pronouns and references ("that", "it", "the company") with the explicit
  company names, metrics and years from the conversation.
- Keep it under 40 words, and keep every number and year.
- Add no new facts.
- Output ONLY the rewritten query, with no preamble or quotes."""


def _format_history(history: Sequence[ChatTurn], max_turns: int = 6) -> str:
    """Render the most recent turns compactly for prompt inclusion."""
    recent = list(history)[-max_turns:]
    return "\n".join(
        f"{'User' if turn.role == 'user' else 'Assistant'}: {turn.content.strip()}"
        for turn in recent
    )
