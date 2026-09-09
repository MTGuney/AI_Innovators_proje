"""Entry point for the Financial Report RAG AI service.

Run locally with:
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import routes_documents, routes_health, routes_rag
from app.config import settings
from app.llm.foundry_client import (
    FoundryError,
    FoundryModelNotLoadedError,
    FoundryUnavailableError,
    get_foundry_client,
)
from app.logging_config import configure_logging
from app.models.schemas import ErrorResponse
from app.rag.document_loader import DocumentError, UnsupportedDocumentError
from app.rag.vector_store import VectorStoreError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Prepare storage and report dependency status at startup."""
    configure_logging()
    settings.ensure_directories()

    logger.info("Starting %s", settings.app_name)
    logger.info(
        "RAG config: top_k=%d chunk_size=%d overlap=%d threshold=%.2f",
        settings.top_k,
        settings.chunk_size,
        settings.chunk_overlap,
        settings.similarity_threshold,
    )

    # Probe Foundry once so operators see the problem at boot, not on the first
    # question. A failed probe is not fatal -- /health reports it as degraded.
    health = get_foundry_client().health()
    if health.reachable:
        logger.info(
            "Foundry Local ready at %s (chat=%s, embeddings=%s)",
            health.base_url, health.chat_model, health.embedding_model,
        )
    else:
        logger.warning(
            "Foundry Local unreachable at %s: %s", health.base_url, health.detail
        )

    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Retrieval-Augmented Generation over financial reports, "
        "powered entirely by local models via Foundry Local."
    ),
    lifespan=lifespan,
)

# The React app and the .NET backend both call this service directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router)
app.include_router(routes_rag.router)
app.include_router(routes_documents.router)


# --------------------------------------------------------------------- #
# Error handling -- users see actionable messages, never stack traces.
# --------------------------------------------------------------------- #


def _error(status_code: int, error: str, detail: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )


@app.exception_handler(FoundryModelNotLoadedError)
async def _model_not_loaded(_: Request, exc: FoundryModelNotLoadedError) -> JSONResponse:
    logger.error("Model not loaded: %s", exc)
    return _error(503, exc.user_message)


@app.exception_handler(FoundryUnavailableError)
async def _foundry_unavailable(_: Request, exc: FoundryUnavailableError) -> JSONResponse:
    logger.error("Foundry Local unavailable: %s", exc)
    return _error(503, FoundryError.user_message, str(exc))


@app.exception_handler(FoundryError)
async def _foundry_error(_: Request, exc: FoundryError) -> JSONResponse:
    logger.error("Foundry Local error: %s", exc)
    return _error(502, "The local model could not complete this request.", str(exc))


@app.exception_handler(UnsupportedDocumentError)
async def _unsupported_document(_: Request, exc: UnsupportedDocumentError) -> JSONResponse:
    return _error(415, exc.user_message)


@app.exception_handler(DocumentError)
async def _document_error(_: Request, exc: DocumentError) -> JSONResponse:
    logger.warning("Document error: %s", exc)
    return _error(400, exc.user_message, str(exc))


@app.exception_handler(VectorStoreError)
async def _vector_store_error(_: Request, exc: VectorStoreError) -> JSONResponse:
    logger.error("Vector store error: %s", exc)
    return _error(503, exc.user_message, str(exc))


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Normalise FastAPI's `{"detail": ...}` into the shared error envelope."""
    return _error(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    problems = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'][1:])}: {error['msg']}"
        for error in exc.errors()
    )
    return _error(422, "The request was not valid.", problems or None)


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    # Log the traceback for operators; return nothing internal to the caller.
    logger.exception("Unhandled error: %s", exc)
    return _error(500, "An unexpected error occurred while processing the request.")


@app.get("/", tags=["health"])
def root() -> dict[str, str]:
    """Service banner."""
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": "/health",
    }
