"""Centralised configuration for the AI/RAG service.

Every tunable value lives here and is sourced from environment variables so the
service can be reconfigured without code changes (see `.env.example`).
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ai-service/app/config.py -> ai-service/
SERVICE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SERVICE_ROOT.parent


class Settings(BaseSettings):
    """Runtime settings. Values come from the environment or a `.env` file."""

    model_config = SettingsConfigDict(
        # Repo-level .env is the shared source of truth; a service-local .env wins.
        env_file=(REPO_ROOT / ".env", SERVICE_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Service identity ---
    app_name: str = "Financial Report RAG Assistant - AI Service"
    log_level: str = "INFO"

    # --- Foundry Local (local LLM inference + embeddings) ---
    foundry_local_url: str = "http://127.0.0.1:52527"
    foundry_model: str = "qwen2.5-1.5b"
    foundry_embedding_model: str = "qwen3-embedding-0.6b-generic-cpu"
    foundry_timeout_seconds: float = 180.0
    foundry_max_tokens: int = 500
    foundry_temperature: float = 0.1
    # Foundry Local does not auto-load models over HTTP. When true (and the
    # service shares a host with the CLI) we shell out to `foundry model load`
    # once on demand instead of failing the request.
    foundry_auto_load: bool = False
    # The daemon picks a new random port on every restart; when true we ask the
    # CLI for the current one instead of failing on a stale FOUNDRY_LOCAL_URL.
    foundry_auto_discover: bool = True

    # --- ChromaDB ---
    # Empty CHROMA_URL => embedded persistent client (simplest local setup).
    chroma_url: str = ""
    chroma_persist_dir: Path = SERVICE_ROOT / "data" / "chroma"
    chroma_collection: str = "financial_reports"

    # --- RAG tuning ---
    top_k: int = Field(default=5, ge=1, le=50)
    chunk_size: int = Field(default=1200, ge=200, le=8000)
    chunk_overlap: int = Field(default=200, ge=0, le=2000)
    similarity_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    max_context_chars: int = Field(default=8000, ge=1000)
    embedding_batch_size: int = Field(default=8, ge=1, le=256)

    # --- Storage ---
    data_dir: Path = SERVICE_ROOT / "data"
    upload_dir: Path = SERVICE_ROOT / "data" / "uploads"

    # --- Dataset downloader ---
    sec_user_agent: str = "FinRAG-Research contact@example.com"

    @field_validator("chroma_persist_dir", "data_dir", "upload_dir", mode="after")
    @classmethod
    def _resolve_against_service_root(cls, value: Path) -> Path:
        """Relative paths in `.env` are interpreted relative to `ai-service/`."""
        return value if value.is_absolute() else (SERVICE_ROOT / value).resolve()

    @field_validator("foundry_local_url", "chroma_url", mode="after")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("chunk_overlap", mode="after")
    @classmethod
    def _overlap_must_be_smaller_than_chunk(cls, value: int, info) -> int:
        chunk_size = info.data.get("chunk_size")
        if chunk_size is not None and value >= chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return value

    @property
    def use_remote_chroma(self) -> bool:
        return bool(self.chroma_url)

    def ensure_directories(self) -> None:
        """Create the directories the service writes to."""
        for directory in (self.data_dir, self.upload_dir, self.chroma_persist_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()
