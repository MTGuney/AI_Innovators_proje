# Architecture

## Why three services

Each service owns one kind of state, and nothing owns two.

| Service | Owns | Does not own |
|---|---|---|
| **Python AI service** | The vector index and everything about retrieval | Users, permissions, chat history |
| **ASP.NET Core backend** | Users, report metadata, conversations | Embeddings, chunking, prompts |
| **React frontend** | Presentation and interaction | Any business rule |

The split is what keeps the RAG pipeline swappable: the backend depends on the
AI service's HTTP contract (`app/models/schemas.py` ↔ `DTOs/AiServiceDtos.cs`),
not on ChromaDB or Foundry Local. Replacing the vector database or the inference
backend touches one Python module each.

Embeddings live **only** in ChromaDB. PostgreSQL stores a `DocumentId` string as
the join key. Duplicating vectors into Postgres would create two sources of truth
that could silently disagree.

---

## The RAG pipeline

```
Question
   │
   ├─ (follow-up?) rewrite into a standalone query      rag_service._resolve_query
   │
   ├─ detect companies named in the question            retriever.detect_companies
   │
   ▼
Embed the query (Foundry Local, CPU)                    embeddings.embed_query
   │
   ▼
ChromaDB nearest-neighbour search, cosine               vector_store.query
   │   • metadata filter (company / year / type / doc)
   │   • over-fetch 3× so thresholding does not starve top_k
   ▼
Drop passages below SIMILARITY_THRESHOLD                retriever.retrieve
   │
   ├─ nothing left? → answer honestly, do not call the model
   ▼
Assemble numbered context [S1], [S2], ...               retriever.build_context
   │   • whole chunks only, within MAX_CONTEXT_CHARS
   ▼
Foundry Local generates structured JSON                 foundry_client.chat
   │
   ▼
Parse defensively, map tags → citations                 response_parser
   │
   ▼
Answer + key points + sources + every retrieved chunk
```

### Retrieval details

**Over-fetching.** `SIMILARITY_THRESHOLD` filters *after* the search, so the
store is asked for `max(top_k × 3, 15)` candidates. Without this, a strict
threshold would routinely return fewer than `top_k` passages.

**Relevance.** The collection is configured with `hnsw:space: cosine`, so
Chroma returns a cosine *distance*. It is converted once, in `vector_store`, to
`relevance = clamp(1 − distance, 0, 1)` — a number that means the same thing in
the API, the UI and the threshold check.

**Multi-company balancing.** When two or more indexed companies are named in a
question, retrieval runs once per company with its own budget and the results are
merged. A single global top-k would let one verbose filing fill the entire
context and leave the comparison one-sided.

**Follow-up rewriting.** Retrieval embeds one string, so "How does that compare
to 2023?" would embed almost no signal. The prior turns are sent to the model to
produce a standalone query first. A failure here is never fatal — it falls back
to the original wording.

---

## Chunking

Financial filings have structure worth preserving, and citations are only
trustworthy if that structure survives.

1. **Load** the file into pages. Real pages for PDFs; ~3,000-character synthetic
   pages for TXT/HTML, split at paragraph then line boundaries so no "page" is
   an outlier in size.
2. **Segment** each page at `Item N` headings. Consecutive markers naming the
   same Item are merged first — filers repeat the current Item as a running page
   header, so a naive split would make every section one page long.
3. **Chunk** within each section using a recursive split over progressively
   weaker separators (`\n\n` → `\n` → `. ` → ` `), so paragraphs and table rows
   stay intact whenever they fit.
4. **Label** each chunk with its section and prepend that heading to the text, so
   an isolated fragment reads in context and embeds with the right signal.

A chunk therefore maps to exactly one page and one section. That is what lets a
citation say *"Apple Annual Report 2024 · page 32 · Item 7. MD&A"* and be right.

---

## Grounding and honesty

The behavioural rules live in one auditable place, `app/rag/prompts.py`:

- answer only from the numbered excerpts;
- never invent or extrapolate figures — copy numbers, units and dates exactly;
- say plainly when the reports do not cover the question;
- prefix inferences with `Interpretation:`;
- cite only excerpts actually used;
- never give investment advice.

Four mechanisms enforce this beyond the prompt, because a prompt alone does not
hold. During development the model was observed asserting a plausible but
entirely invented revenue figure, with "high" confidence, when the retrieved
context contained no figures at all.

1. **No context → no call.** If nothing passes the threshold the model is never
   invoked, so it cannot answer from parametric memory.
2. **Numeric grounding check** (`app/services/grounding.py`). Every figure in the
   answer is looked for in the context the model was shown. Anything missing is
   returned in `unsupported_figures` and forces confidence to "low". The check is
   conservative by design: it skips years and small integers, and it cannot
   recognise a restated unit (`416,161` → `$416.2 billion`), so its output is
   presented as "verify this", never as proof of fabrication.
3. **Confidence is capped by evidence.** A "high" self-report is downgraded when
   the best retrieved passage is weak, and forced to "low" when the reply could
   not be parsed or contains unverifiable figures.
4. **Uncited answers still get provenance.** If the model cites nothing, the
   top-ranked passages it was shown are attached anyway — an answer with no
   traceable source would be unverifiable.

The same root cause had a data-side fix. Financial statements live in HTML
tables, and the first version of the extractor discarded `<table>` elements
entirely — leaving a corpus of narrative that discussed *changes* without ever
stating the *amounts*. Tables are now flattened to `label | value | value` lines,
so `Total net sales | 416,161 | 391,035 | 383,285` is retrievable and quotable.
Better grounding is mostly a data problem, not a prompting problem.

---

## Foundry Local integration

`app/llm/foundry_client.py` is the only module that knows Foundry exists. It
exposes `generate`, `chat`, `embed` and `health`, and absorbs three awkward
realities of Foundry Local 0.10:

- **The daemon picks a new random port on every restart.** On a connection
  failure the client asks `foundry server status -o json` for the live URL and
  retries once (`FOUNDRY_AUTO_DISCOVER`).
- **Models are not auto-loaded over HTTP.** Loading goes through the CLI's native
  interop layer, so a "not loaded" error is translated into a message naming the
  exact command to run — or, with `FOUNDRY_AUTO_LOAD=true`, the client runs it.
- **Errors arrive as a JSON `error` object, sometimes with HTTP 200.** Every
  response body is inspected, not just the status code.

---

## Error handling

Both services share one contract: `{ "error": "...", "detail": "..." }`, and
neither ever returns a stack trace.

| Condition | Status | User sees |
|---|---|---|
| Foundry unreachable | 503 | "AI service is currently unavailable..." |
| Model not loaded | 503 | "...Start it with: `foundry model load X`" |
| Unsupported file type | 415 | The supported formats, listed |
| Unparseable document | 400 | "Unable to process this document..." |
| Vector store down | 503 | "The document index is unavailable." |
| Anything else | 500 | A generic sentence; the cause is logged server-side |

Ingestion never raises for an expected failure. A malformed document returns
`status: "failed"` with a readable message so a batch of 200 filings is not lost
to one bad file.

---

## Data flow for an upload

```
Browser ──POST /api/reports/upload──► Backend
                                        │ writes the file to the shared volume
                                        ├──POST /documents/ingest──► AI service
                                        │                              │ load → chunk → embed
                                        │                              ▼
                                        │                          ChromaDB
                                        ◄── IngestResult (document_id, counts)
                                        │
                                        └─ writes FinancialReport row → PostgreSQL
```

The backend and AI service share the uploads volume **at the same absolute
path**, because the handoff is a path, not a byte stream. In `docker-compose.yml`
both mount `report-uploads` at `/app/uploads`.

Documents indexed by the CLI bypass this flow entirely, which is why
`POST /api/reports/sync` exists: it reads the vector index and back-fills the
catalogue.

---

## Security notes

- Passwords are BCrypt-hashed; the plaintext is never stored or logged.
- Login returns the same message and does the same work for an unknown email as
  for a wrong password, so the endpoint cannot be used to enumerate accounts.
- The API refuses to start if `Jwt:Secret` is shorter than 32 characters.
- Conversations are always loaded scoped to their owner, so an id alone does not
  grant access.
- Logs record document *names*, counts and timings — never document contents.
