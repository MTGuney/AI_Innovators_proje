"""Shared fixtures.

Tests never call Foundry Local or a real vector database: the RAG pipeline is
exercised against fakes so the suite is fast, deterministic and runnable in CI
without a GPU.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schemas import RetrievedChunk  # noqa: E402


SAMPLE_REPORT = """ACME CORPORATION
ANNUAL REPORT ON FORM 10-K

PART I

Item 1. Business

Acme Corporation designs and sells industrial robotics and factory automation
software. The Company operates in three reportable segments.

Item 1A. Risk Factors

Supply chain concentration. We source over 60% of our precision actuators from a
single supplier, and a disruption would materially harm our ability to fulfil
orders. Customer concentration. Our three largest customers accounted for 41% of
total revenue in fiscal 2024.

PART II

Item 7. Management's Discussion and Analysis

Total revenue for fiscal 2024 was $4,820 million, an increase of 12.4% compared
with $4,288 million in fiscal 2023. Operating income was $853 million in fiscal
2024, compared with $671 million in fiscal 2023.
"""


@pytest.fixture
def sample_report(tmp_path: Path) -> Path:
    """A small filing on disk, named to the dataset's metadata convention."""
    path = tmp_path / "ACME_Acme-Corp_10-K_2024.txt"
    path.write_text(SAMPLE_REPORT, encoding="utf-8")
    return path


class FakeEmbedder:
    """Deterministic embedder: no model, no network, stable vectors.

    Vectors are a tiny bag-of-words over a fixed vocabulary, which is enough for
    nearest-neighbour ordering to be meaningful in tests.
    """

    VOCAB = ("revenue", "risk", "income", "supplier", "customer", "software")

    def __init__(self) -> None:
        self.calls = 0

    def embed_documents(self, texts):
        self.calls += 1
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)

    @classmethod
    def _vector(cls, text: str) -> list[float]:
        lowered = text.lower()
        vector = [float(lowered.count(word)) for word in cls.VOCAB]
        # Always non-zero so cosine distance stays defined.
        vector.append(1.0)
        return vector


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def vector_store(tmp_path, monkeypatch):
    """A real Chroma collection backed by a throwaway directory."""
    import chromadb

    from app.rag import vector_store as module

    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    monkeypatch.setattr(module, "_store", None)
    return module.VectorStore(client=client, collection_name="test_reports")


def make_chunk(
    text: str = "Total revenue was $4,820 million.",
    chunk_id: str = "doc::p1::c0",
    relevance: float = 0.8,
    **overrides,
) -> RetrievedChunk:
    """Build a RetrievedChunk without repeating every field in each test."""
    fields = {
        "chunk_id": chunk_id,
        "document_id": "acme-2024",
        "source_file": "ACME_Acme-Corp_10-K_2024.txt",
        "company": "Acme Corp",
        "year": 2024,
        "report_type": "10-K",
        "title": "Acme Annual Report",
        "section": "Item 7. MD&A",
        "page_number": 1,
        "chunk_index": 0,
        "relevance": relevance,
        "text": text,
    }
    fields.update(overrides)
    return RetrievedChunk(**fields)
