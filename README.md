# FinRAG — Financial Report RAG Assistant

A local-first, retrieval-augmented research assistant for financial reports. Ask
questions in natural language about real SEC annual reports and get answers that
are grounded in — and traceable to — the passages they came from.

Inference and embeddings both run **locally through Foundry Local**. No report
text is sent to a cloud LLM.

```
React (Vite + TS)          Browse reports, chat, compare, inspect retrieval
        │
        ▼
ASP.NET Core 9 API         Report metadata, chat history, business logic
        │
        ├── PostgreSQL     Companies, reports, conversations, messages
        │
        └── Python AI service (FastAPI)
                  ├── Chunking + embeddings
                  ├── ChromaDB          Vector index + chunk metadata
                  └── Foundry Local     Local LLM inference + embeddings
```

---

## What it does

- **Grounded question answering.** Every answer is built only from retrieved
  report passages, and states plainly when the reports do not cover a question.
- **Traceable citations.** Each source shows document, company, fiscal year,
  page, section (`Item 1A. Risk Factors`) and a relevance score. Expand any
  citation to read the exact passage the answer was built from.
- **Inspectable retrieval.** Every answer carries the full set of passages
  retrieval considered — including ones the model did not cite — so the pipeline
  is auditable rather than a black box.
- **Multi-document questions.** "Compare Tesla and Ford's revenue growth"
  detects both companies and gives each its own retrieval budget, so one verbose
  filing cannot crowd out the other.
- **Comparison mode.** Retrieved facts, the AI summary and any arithmetic are
  labelled separately, so it is always clear which is which.
- **Follow-up questions.** "How does that compare to 2023?" is rewritten into a
  standalone query before retrieval, so pronouns resolve correctly.

---

## Prerequisites

| Requirement | Version used | Notes |
|---|---|---|
| [Foundry Local](https://learn.microsoft.com/azure/ai-foundry/foundry-local/) | 0.10.3 | Required. Runs as a desktop service on the host. |
| Python | 3.12+ | 3.13 works; see note on ChromaDB below. |
| .NET SDK | 9.0 | |
| Node.js | 22 | |
| PostgreSQL | 16 | Backend persistence. |

---

## Quick start

### 1. Configure

```bash
cp .env.example .env
```

Then edit `.env`. The two values that always need attention:

```bash
foundry server status     # prints the port -> FOUNDRY_LOCAL_URL
```

- `FOUNDRY_LOCAL_URL` — **Foundry Local picks a new random port on every
  restart.** The AI service re-discovers it automatically via the CLI when
  `FOUNDRY_AUTO_DISCOVER=true`, but keeping this current avoids a slow first call.
- `SEC_USER_AGENT` — EDGAR rejects anonymous traffic. Use
  `"<project-name> <your-email>"`.

### 2. Start Foundry Local and load the models

Models are **not** auto-loaded by the HTTP API — load them explicitly:

```bash
foundry server start
foundry model load qwen2.5-1.5b                      # chat (GPU)
foundry model load qwen3-embedding-0.6b-generic-cpu  # embeddings (CPU)
```

See [Choosing models](#choosing-models) for why this particular pair.

### 3. Start the AI service

```bash
cd ai-service
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m uvicorn main:app --port 8000
```

Check it: <http://localhost:8000/health> should report `foundry_local` and
`chroma` as healthy.

### 4. Load the dataset

```bash
cd ai-service
.venv/Scripts/python scripts/download_sec_reports.py --years 2   # ~10 filings
.venv/Scripts/python scripts/ingest_reports.py                   # chunk + embed
.venv/Scripts/python scripts/ingest_reports.py --list            # verify
```

Ingestion takes roughly a minute per 60 passages on CPU embeddings; the full
default corpus is ~3,000 passages, so a cold build takes around 45 minutes.
Re-running without `--force` is cheap: unchanged files are skipped on a checksum.

To rebuild the index after changing chunking, extraction or embedding settings:

```bash
.venv/Scripts/python scripts/download_sec_reports.py --years 2   # refresh source text
.venv/Scripts/python scripts/ingest_reports.py --force           # re-embed everything
```

Run this with the AI service stopped — the embedded ChromaDB store is
single-writer, so the service and the ingestion script cannot hold it at once.

### 5. Start PostgreSQL and the backend

```bash
# One-time setup, run once as a PostgreSQL superuser:
psql -U postgres -c "CREATE ROLE finrag LOGIN PASSWORD 'finrag';"
psql -U postgres -c "CREATE DATABASE finrag OWNER finrag;"

cd backend/FinRag.Api
dotnet run
```

Migrations are applied on startup. Swagger is at
<http://localhost:5080/swagger>.

### 6. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. There is no sign-in — FinRAG is a single-user
local tool, so it opens straight on the question box.

On the **Reports** page click **Import indexed** once, to bring the documents
indexed by the CLI into the catalogue.

---

## Choosing models

Both roles are configurable, and the defaults are chosen for a **4 GB GPU**:

```bash
FOUNDRY_MODEL=qwen2.5-1.5b                       # generation, on the GPU
FOUNDRY_EMBEDDING_MODEL=qwen3-embedding-0.6b-generic-cpu   # embeddings, on the CPU
```

The split is deliberate. Generation is the latency bottleneck and gets the GPU;
embeddings are small, run fine on CPU, and would otherwise compete for VRAM.
On a 4 GB card a 3.6 GB chat model leaves no room for the KV cache of an
8,000-character context.

With ≥ 8 GB VRAM, move up:

```bash
FOUNDRY_MODEL=phi-4-mini
FOUNDRY_EMBEDDING_MODEL=qwen3-embedding-0.6b-cuda-gpu
```

> **Verify any replacement model actually produces coherent text.** Some Foundry
> execution-provider builds are broken — `phi-3.5-mini` on the TensorRT-RTX
> provider emits token soup, while the same model on CUDA is fine. A quick
> `foundry chat <model>` is enough to check.

---

## Configuration

All tuning lives in `.env` (see `.env.example` for the full annotated list).

| Variable | Default | Effect |
|---|---|---|
| `TOP_K` | 5 | Passages sent to the model per question. |
| `CHUNK_SIZE` | 1200 | Characters per chunk. |
| `CHUNK_OVERLAP` | 200 | Characters repeated between chunks. |
| `SIMILARITY_THRESHOLD` | 0.25 | Minimum relevance (`1 − cosine distance`). |
| `MAX_CONTEXT_CHARS` | 8000 | Context budget; raise for quality, lower for speed. |
| `FOUNDRY_MAX_TOKENS` | 500 | Answer length cap. Higher values need more VRAM. |
| `EMBEDDING_BATCH_SIZE` | 8 | Passages embedded per request. |

---

## Design decisions worth knowing

**Chunks never span pages or sections.** Text is segmented at `Item N` headings
first, then chunked within each section. A chunk that mixed *Risk Factors* with
*MD&A* would be mislabelled whichever heading was chosen for it, which would make
citations misleading.

**Filings repeat their `Item` heading as a running page header.** Consecutive
markers naming the same Item are merged, or every section would be one page long.

**Synthetic pagination.** HTML filings have no real pages, so text is sliced into
~3,000-character pseudo-pages. Oversized blocks are split rather than emitted
whole — a page number is only a useful citation anchor if pages are comparable
in size.

**Duplicate detection is content-addressed.** A SHA-256 of the file decides
whether it has already been indexed, so re-running ingestion is free. Re-ingesting
changed content under the same document id *replaces* the old chunks.

**Deleting a report is atomic across both stores.** If the vector index cannot be
updated, the metadata row is kept, rather than leaving answers citing a report the
catalogue no longer knows about.

**The model's JSON is parsed defensively.** Small local models wrap JSON in prose
or drop fields. The parser recovers what it can, falls back to treating the reply
as prose, and lowers the reported confidence when it does.

**Confidence is capped by evidence.** A model claiming "high" confidence is
downgraded when nothing retrieved was a strong match.

**Figures are checked against the context before the answer is returned.** Every
number in an answer is looked for in the passages the model was shown. Anything
missing is listed in `unsupportedFigures`, surfaced as a warning in the UI, and
forces confidence to "low". This was added after the model was observed
inventing a plausible revenue figure when the context contained none.

**Tables are kept, not dropped.** A 10-K states its revenue and income in tables,
so HTML tables are flattened to `label | value | value` lines rather than
discarded — otherwise the corpus could not answer the questions this system
exists for.

---

## Testing

```bash
cd ai-service && .venv/Scripts/python -m pytest    # 71 tests
cd backend    && dotnet test                       # 21 tests
cd frontend   && npm test                          # 21 tests
```

The AI-service suite uses a deterministic fake embedder and a scripted LLM, so it
runs in seconds with no GPU and no network.

---

## Project layout

```
ai-service/            Python RAG service (FastAPI)
  app/rag/             document_loader, chunker, embeddings, vector_store,
                       ingestion, retriever, prompts
  app/llm/             foundry_client.py — the only module that talks to Foundry
  app/services/        rag_service, comparison_service, response_parser
  app/api/             HTTP routes
  scripts/             download_sec_reports.py, ingest_reports.py
  tests/

backend/FinRag.Api/    ASP.NET Core 9
  Controllers/ Services/ Repositories/ Data/ Entities/ DTOs/ Middleware/

frontend/src/          React 19 + TypeScript
  components/ pages/ layouts/ services/ hooks/ context/ utils/ styles/
```

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `The local model 'X' is not loaded` | Run `foundry model load X`. The HTTP API never auto-loads. |
| `AI service is currently unavailable` | Foundry Local is not running, or the port changed. Run `foundry server status` and update `FOUNDRY_LOCAL_URL`. |
| Answers are token soup | The model's execution-provider build is broken. Try the CUDA variant, or a different model. |
| `out of memory` from the GPU | Lower `MAX_CONTEXT_CHARS` and `FOUNDRY_MAX_TOKENS`, or use a smaller chat model. Close other GPU applications. |
| `chroma-hnswlib` fails to build | You are on ChromaDB < 1.0 with Python 3.13. The pinned `chromadb==1.5.9` needs no C++ toolchain. |
| Reports page is empty after CLI ingestion | Click **Import indexed** — the vector index and the catalogue are separate stores. |

---

## Limitations

- Only the narrative `Item` sections (1, 1A, 7, 7A) are kept by default. Pass
  `--full` to `download_sec_reports.py` to index whole filings.
- Tables are flattened to `label | value | value` lines. This preserves the
  figures but loses column headers, so a row's years must be read from nearby
  text rather than from the row itself.
- Scanned/image-only PDFs are not supported (no OCR).
- Small local models sometimes restate figures in different units. The numeric
  grounding check flags anything not found verbatim, but cannot tell a
  legitimate restatement from an invented number — treat the flag as
  "verify this", not as proof of error.
- The assistant reports facts from reports. It does not give investment advice.
