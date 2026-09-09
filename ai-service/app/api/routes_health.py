"""Health and readiness endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.config import settings
from app.llm.foundry_client import FoundryLocalClient, get_foundry_client
from app.models.schemas import ComponentHealth, HealthResponse
from app.rag.vector_store import VectorStore, get_vector_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(
    foundry: FoundryLocalClient = Depends(get_foundry_client),
    store: VectorStore = Depends(get_vector_store),
) -> HealthResponse:
    """Report whether the local LLM and the vector index are usable.

    Always returns 200 -- the payload carries the verdict, so a dashboard can
    show *which* dependency is down instead of a bare failure.
    """
    llm = foundry.health()
    components = [
        ComponentHealth(
            name="foundry_local",
            healthy=llm.reachable,
            detail=llm.detail or f"{llm.base_url} ({len(llm.available_models)} models)",
        )
    ]

    try:
        chunk_count = store.count()
        components.append(
            ComponentHealth(
                name="chroma",
                healthy=True,
                detail=f"{chunk_count} indexed chunk(s) in '{store.collection_name}'",
            )
        )
    except Exception as exc:  # noqa: BLE001 - health must never propagate
        logger.warning("Vector store health probe failed: %s", exc)
        components.append(
            ComponentHealth(name="chroma", healthy=False, detail=str(exc))
        )

    return HealthResponse(
        status="ok" if all(c.healthy for c in components) else "degraded",
        service=settings.app_name,
        components=components,
        chat_model=foundry.chat_model,
        embedding_model=foundry.embedding_model,
    )
