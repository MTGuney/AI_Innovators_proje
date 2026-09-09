"""Pydantic contracts for the AI service HTTP API.

These are the stable boundary between the Python RAG service and the .NET
backend, so treat changes here as breaking changes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Confidence = Literal["high", "medium", "low"]
IngestStatus = Literal["indexed", "skipped_duplicate", "failed"]
FactKind = Literal["retrieved_fact", "ai_summary", "calculated_comparison"]

MIN_QUESTION_CHARS = 3
MAX_QUESTION_CHARS = 2000


# --------------------------------------------------------------------- #
# Shared building blocks
# --------------------------------------------------------------------- #


class RetrievalFilters(BaseModel):
    """Optional metadata narrowing applied before semantic search."""

    companies: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    report_types: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.companies or self.years or self.report_types or self.document_ids
        )


class RetrievedChunk(BaseModel):
    """A chunk returned by semantic search, exposed for full transparency."""

    chunk_id: str
    document_id: str
    source_file: str
    company: str | None = None
    year: int | None = None
    report_type: str | None = None
    title: str | None = None
    section: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None
    relevance: float
    text: str


class SourceCitation(BaseModel):
    """What the UI renders under an answer so a claim can be traced."""

    document: str
    document_id: str
    page: int | None = None
    relevance: float
    company: str | None = None
    year: int | None = None
    report_type: str | None = None
    section: str | None = None
    chunk_id: str
    excerpt: str


class ChatTurn(BaseModel):
    """One prior message, used to resolve follow-up questions."""

    role: Literal["user", "assistant"]
    content: str


class QuestionMixin(BaseModel):
    """Shared question validation (spec: 'Validate the user question')."""

    question: str

    @field_validator("question", mode="after")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        question = value.strip()
        if len(question) < MIN_QUESTION_CHARS:
            raise ValueError(
                f"Question must be at least {MIN_QUESTION_CHARS} characters."
            )
        if len(question) > MAX_QUESTION_CHARS:
            raise ValueError(
                f"Question must be at most {MAX_QUESTION_CHARS} characters."
            )
        return question


# --------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------- #


class SearchRequest(QuestionMixin):
    top_k: int | None = Field(default=None, ge=1, le=50)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


class SearchResponse(BaseModel):
    question: str
    top_k: int
    similarity_threshold: float
    total_candidates: int
    chunks: list[RetrievedChunk]


# --------------------------------------------------------------------- #
# RAG question answering
# --------------------------------------------------------------------- #


class RagQueryRequest(QuestionMixin):
    top_k: int | None = Field(default=None, ge=1, le=50)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    history: list[ChatTurn] = Field(default_factory=list)


class RagAnswer(BaseModel):
    """The structured answer contract described in the spec."""

    answer: str
    key_points: list[str] = Field(default_factory=list)
    sources: list[SourceCitation] = Field(default_factory=list)
    confidence: Confidence = "low"
    grounded: bool = True
    model: str
    elapsed_ms: int = 0
    # Figures in the answer that could not be found in the retrieved passages.
    # A caution flag, not a verdict: a restated unit (416,161 -> $416.2bn) also
    # lands here. Non-empty means the answer needs checking against the sources.
    unsupported_figures: list[str] = Field(default_factory=list)
    # Everything the model was allowed to see, so retrieval stays inspectable.
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)


# --------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------- #


class ComparisonRequest(BaseModel):
    companies: list[str] = Field(min_length=2, max_length=4)
    metric: str = Field(min_length=2, max_length=200)
    years: list[int] = Field(default_factory=list)
    top_k_per_company: int | None = Field(default=None, ge=1, le=20)

    @field_validator("companies", mode="after")
    @classmethod
    def _unique_companies(cls, value: list[str]) -> list[str]:
        """Drop duplicates case-insensitively -- comparing a company with
        itself under different casing produces a meaningless result."""
        cleaned: list[str] = []
        seen: set[str] = set()
        for company in value:
            name = company.strip()
            if name and name.casefold() not in seen:
                seen.add(name.casefold())
                cleaned.append(name)

        if len(cleaned) < 2:
            raise ValueError("Provide at least two distinct companies.")
        return cleaned


class CompanyFindings(BaseModel):
    """Per-company evidence, labelled by provenance as the spec requires."""

    company: str
    kind: FactKind = "retrieved_fact"
    findings: list[str] = Field(default_factory=list)
    sources: list[SourceCitation] = Field(default_factory=list)
    has_data: bool = True


class ComparisonResponse(BaseModel):
    metric: str
    companies: list[str]
    years: list[int] = Field(default_factory=list)
    per_company: list[CompanyFindings] = Field(default_factory=list)
    summary: str
    summary_kind: FactKind = "ai_summary"
    confidence: Confidence = "low"
    unsupported_figures: list[str] = Field(default_factory=list)
    model: str
    elapsed_ms: int = 0


# --------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------- #


class IngestRequest(BaseModel):
    """Index a document already present on the AI service's filesystem."""

    path: str
    company: str | None = None
    year: int | None = Field(default=None, ge=1900, le=2200)
    report_type: str | None = None
    title: str | None = None
    document_id: str | None = None
    force: bool = False


class IngestResult(BaseModel):
    document_id: str
    source_file: str
    status: IngestStatus
    chunk_count: int = 0
    page_count: int = 0
    char_count: int = 0
    company: str | None = None
    year: int | None = None
    report_type: str | None = None
    title: str | None = None
    message: str | None = None


class IndexedDocument(BaseModel):
    """A document currently present in the vector index."""

    document_id: str
    source_file: str | None = None
    title: str | None = None
    company: str | None = None
    year: int | None = None
    report_type: str | None = None
    chunk_count: int = 0
    page_count: int = 0


class IndexStats(BaseModel):
    total_documents: int
    total_chunks: int
    companies: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    report_types: list[str] = Field(default_factory=list)
    documents_by_year: dict[str, int] = Field(default_factory=dict)


# --------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------- #


class ComponentHealth(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    components: list[ComponentHealth] = Field(default_factory=list)
    chat_model: str
    embedding_model: str


class ErrorResponse(BaseModel):
    """Uniform error envelope -- never carries stack traces."""

    error: str
    detail: str | None = None
