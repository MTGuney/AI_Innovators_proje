"""Retrieval and generation endpoints: search, question answering, comparison."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.models.schemas import (
    ComparisonRequest,
    ComparisonResponse,
    RagAnswer,
    RagQueryRequest,
    SearchRequest,
    SearchResponse,
)
from app.rag.retriever import Retriever, get_retriever
from app.services.comparison_service import ComparisonService, get_comparison_service
from app.services.rag_service import RagService, get_rag_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rag"])


@router.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    service: RagService = Depends(get_rag_service),
) -> SearchResponse:
    """Semantic search with no generation -- lets the UI inspect retrieval."""
    return service.search(request)


@router.post("/query", response_model=RagAnswer)
def query(
    request: RagQueryRequest,
    service: RagService = Depends(get_rag_service),
) -> RagAnswer:
    """Answer a question from the indexed reports, with source citations."""
    logger.info("Question: %s", request.question[:200])
    return service.answer(request)


@router.post("/compare", response_model=ComparisonResponse)
def compare(
    request: ComparisonRequest,
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonResponse:
    """Compare companies on a metric, keeping facts and summary separate."""
    logger.info("Comparing %s on %r", request.companies, request.metric)
    return service.compare(request)


@router.get("/companies", response_model=list[str])
def companies(retriever: Retriever = Depends(get_retriever)) -> list[str]:
    """Companies available in the index, for populating filter controls."""
    return retriever.indexed_companies()
