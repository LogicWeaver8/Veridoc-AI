# VeriDox AI

**Enterprise Knowledge Assistant** — a full-stack application that ingests an organisation's PDF,
TXT and Markdown documents, retrieves the relevant evidence, and answers questions with
deterministic citations. Answers are restricted to the uploaded corpus: when the documents do not
cover a question, the assistant says so instead of guessing.

The repository contains a FastAPI backend, a React (Vite) single-page frontend, a demo corpus and
seeding script, 55 automated tests, a Postman collection, and Docker configuration.

---

## Contents

- [Features](#features)
- [Technology stack](#technology-stack)
- [Repository layout](#repository-layout)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [How it works](#how-it-works)
- [API reference](#api-reference)
- [Postman](#postman)
- [Docker](#docker)
- [Database](#database)
- [Implemented vs. not implemented](#implemented-vs-not-implemented)
- [Known limitations](#known-limitations)
- [Verification and test results](#verification-and-test-results)
- [Security notes](#security-notes)
- [Attribution](#attribution)

---

## Features

### Document management
- Upload one or many PDF, TXT or Markdown files, with optional effective date and version label.
- Background ingestion with live status (pending → processing → completed/failed).
- SHA-256 content deduplication, safe filenames, extension/size validation and path-traversal
  protection on every upload.
- Document library with search, type/status filters, version list, chunk preview and delete.
- **Document version intelligence**: effective dates, supersession, active/superseded status, and
  deterministic version selection (see [How it works](#how-it-works)). A newer upload never
  silently replaces an older policy without an effective date.

### Grounded question answering
- Hybrid retrieval: vector search (FAISS, NumPy fallback) + BM25, fused with Reciprocal Rank Fusion.
- Optional CrossEncoder reranking (enabled through configuration).
- Strict evidence validation before generation: if coverage or similarity is too low, the answer is
  reported as `not_covered`; weak coverage becomes `partially_answered`.
- Deterministic citations with document name, version, page, section, excerpt and a relevance score.
- Expandable citations in the UI and a source viewer that highlights the cited clause.
- Conversation history with follow-up questions; each conversation persists its messages.
- LLM provider abstraction: Gemini, OpenAI, Ollama, or a **clearly labelled offline mock provider**.

### Batch and operations
- CSV batch Q&A (up to 500 questions by default) with progress reporting and downloadable results.
- Dashboard metrics, ingestion pipeline status, recent documents and recent conversations.
- Settings page showing the active provider, embedding model, index backend and warnings.
- Index rebuild endpoint and startup recovery for interrupted ingestion/batch jobs.
- Structured JSON error responses; no stack traces or document contents are returned to clients.

---

## Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+ (validated on 3.14.0), FastAPI 0.162, Uvicorn, SQLAlchemy 2.1 (SQLite) |
| Retrieval | FAISS IndexFlatIP (NumPy cosine fallback), custom BM25, Reciprocal Rank Fusion |
| Embeddings | Offline `hashing` provider by default; optional `sentence-transformers` |
| Extraction | PyMuPDF; optional Tesseract OCR via pytesseract/Pillow |
| Frontend | React 19, Vite 7, hand-written CSS (no component library) |
| Tests | pytest 9, FastAPI TestClient |
| Packaging | Docker multi-stage build, Docker Compose |

No API key is required to run the application. The default `mock` provider is extractive and its
output is labelled as mock mode in the API response, the UI and the batch CSV.

---

## Repository layout

```
.
├── backend/
│   ├── app/
│   │   ├── api/               # FastAPI routers (documents, versions, chat, batch, system)
│   │   ├── core/              # errors, logging
│   │   ├── db/                # engine/session, UTC datetime type
│   │   ├── models/            # SQLAlchemy models
│   │   ├── repositories/      # query helpers
│   │   ├── schemas/           # Pydantic request/response models
│   │   ├── services/          # ingestion, extraction, embeddings, retrieval, generation,
│   │   │                      # validation, citations, versions, chat, batch, stats
│   │   ├── utils/             # files, text cleaning/chunking, time
│   │   ├── config.py          # environment-driven settings
│   │   ├── container.py       # dependency container
│   │   └── main.py            # app factory, SPA serving, exception handlers
│   ├── postman/               # Postman collection + local environment
│   ├── tests/                 # pytest suite (55 tests)
│   ├── pytest.ini
│   ├── requirements.txt       # core runtime (pinned)
│   ├── requirements-dev.txt   # + pytest
│   └── requirements-ai.txt    # optional neural embeddings / OCR
├── frontend/
│   ├── src/                   # React app (pages, components, styles)
│   ├── dist/                  # pre-built UI served by FastAPI
│   ├── package.json
│   └── vite.config.js
├── scripts/
│   ├── seed_demo.py           # idempotent demo corpus seeder
│   ├── demo_batch_questions.csv
│   ├── demo_documents/        # 9 demo policy documents (incl. a 2-page PDF)
│   └── generate_facilities_pdf.py
├── data/                      # created at runtime: SQLite DB, uploads, indexes, batch results
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Quick start

### Prerequisites
- Python 3.12 or newer (validated on Python 3.14.0)
- Node.js 20 or newer and npm (validated on Node 24.18.0 / npm 11)
- Optional: Tesseract OCR binary for scanned PDFs

### 1. Backend

From the repository root:

```bash
# Windows (Git Bash / PowerShell)
python -m venv .venv
source .venv/Scripts/activate
pip install -r backend/requirements-dev.txt

cd backend
python -m uvicorn app.main:app --reload --port 8000
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt

cd backend
python -m uvicorn app.main:app --reload --port 8000
```

- API: <http://127.0.0.1:8000> (OpenAPI docs at `/docs`)
- Health: <http://127.0.0.1:8000/health>
- The database and storage directories are created automatically under `data/`.

### 2. Frontend

**Option A — development server (hot reload):**

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` and `/health` to port 8000.

**Option B — single server (pre-built UI):**

The repository already includes `frontend/dist`, so starting the backend alone serves the UI at
<http://127.0.0.1:8000>. To rebuild after changing frontend code:

```bash
cd frontend
npm install
npm run build
```

### 3. Load the demo corpus

With the backend running and the virtual environment active (from the repository root):

```bash
python scripts/seed_demo.py
```

This uploads nine policy documents (including a real 2-page PDF) and creates a second version of
the leave policy so version intelligence can be demonstrated. It is idempotent: existing documents
are reused instead of duplicated (duplicate content is detected by SHA-256).

Optional extras:

```bash
# Upload, ask a question and run the demo batch CSV
python scripts/seed_demo.py --ask --batch

# Custom server or question
python scripts/seed_demo.py --base-url http://127.0.0.1:8000 --question "How many sick leave days in 2025?"
```

Demo questions include: annual leave in 2026, the 2025 sick-leave figure, meal allowance, remote
days, learning budget, core hours, gifts, a lost badge (not covered) and weather in Bengaluru (not
covered — the assistant abstains).

### 4. Run the tests

```bash
cd backend
python -m pytest
```

Expected (latest run): `55 passed in 4.11s`. See
[Verification and test results](#verification-and-test-results) for details.

---

## Configuration

Copy `.env.example` to `.env` in the repository root (or `backend/.env`). All values are optional;
defaults work offline.

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | Environment label shown in settings |
| `DEBUG` | `false` | Debug logging |
| `API_PREFIX` | `/api` | Prefix for application routes |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins (`*` for local development) |
| `DATA_DIR` | `<repo>/data` | Database, uploads, indexes and batch results |
| `DATABASE_URL` | SQLite in `DATA_DIR` | SQLAlchemy database URL |
| `MAX_UPLOAD_MB` | `25` | Per-file upload limit |
| `MAX_BATCH_QUESTIONS` | `500` | Rows allowed per CSV batch |
| `CHUNK_SIZE_TOKENS` | `650` | Target chunk size |
| `CHUNK_OVERLAP_TOKENS` | `90` | Overlap within a section |
| `EMBEDDING_PROVIDER` | `hashing` | `hashing` or `sentence-transformers` |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Used by the neural provider |
| `EMBEDDING_DIM` | `384` | Hashing embedding dimension |
| `VECTOR_BACKEND` | `auto` | `auto`, `faiss` or `numpy` |
| `RETRIEVAL_CANDIDATES` | `15` | Candidates per retrieval arm |
| `FINAL_EVIDENCE_CHUNKS` | `6` | Evidence chunks passed to validation |
| `RRF_K` | `60` | Reciprocal Rank Fusion constant |
| `MIN_VECTOR_SIMILARITY` | `0.10` | Below this, questions are treated as not covered |
| `MIN_ANSWER_SIMILARITY` | `0.20` | Below this, answers become partially covered |
| `RERANKER_ENABLED` | `false` | Enable CrossEncoder reranking |
| `LLM_PROVIDER` | `mock` | `mock`, `gemini`, `openai` or `ollama` |
| `LLM_MODEL` | empty | Provider model name |
| `GEMINI_API_KEY` | empty | Gemini key (environment only) |
| `OPENAI_API_KEY` | empty | OpenAI key (environment only) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | `45` / `2` | Provider resilience |
| `OCR_ENABLED` | `true` | Try OCR when extracted text is sparse |
| `OCR_MIN_CHARS_PER_PAGE` | `40` | Threshold for OCR fallback |

**Secrets are never hardcoded.** API keys are read from the environment and are not exposed by the
settings endpoint. The settings page only reports the provider name, model, temperature and timeout.

### Switching to a real LLM

```bash
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=...
```

(or `openai` with `OPENAI_API_KEY`, or `ollama` with a local model). If the provider fails, the API
returns a provider error — it does not silently fall back to mock output.

### Switching to neural embeddings

```bash
pip install -r backend/requirements-ai.txt
EMBEDDING_PROVIDER=sentence-transformers
```

The first start downloads the model. Rebuild the index (`POST /api/index/rebuild`) after changing
the embedding provider or dimension.

---

## How it works

### Ingestion pipeline

1. **Upload validation** — extension allow-list, size limit, safe generated filename, SHA-256
   deduplication. TXT/Markdown payloads are decoded synchronously and rejected (422) if they are
   actually binary.
2. **Extraction** — PyMuPDF for PDFs, UTF-8 decoding for text/Markdown. Ligatures and non-breaking
   spaces are normalised.
3. **OCR fallback** — if a PDF page yields fewer than `OCR_MIN_CHARS_PER_PAGE` characters and
   pytesseract/Pillow/Tesseract are available, the page is rasterised and OCR'd.
4. **Cleaning and sections** — page boundaries and headings are detected; section titles are kept
   as metadata for citations.
5. **Chunking** — section-aware token chunking with overlap inside a section and a forced boundary
   between sections, so a citation never spans unrelated sections.
6. **Embedding** — batched, L2-normalised vectors (hashing provider or sentence-transformers).
7. **Indexing** — FAISS `IndexFlatIP` (NumPy cosine fallback) plus an in-memory BM25 index built
   from persisted token statistics. Index files are written to `data/indexes/`.
8. **Persistence** — document, version, chunk text and metadata are stored in SQLite. Each upload
   embeds only its own chunks; the index is not rebuilt for every document, and queries never load
   all documents into memory.

A startup hook marks interrupted documents/jobs as failed so they can be retried.

### Retrieval and grounding

1. The question is embedded and searched with vector + BM25 retrieval; results are fused with RRF.
2. Optional CrossEncoder reranking reorders the candidates.
3. Version filtering happens before generation (see below).
4. Evidence validation checks the best single chunk's term coverage, vector similarity and the
   presence of the question's primary subject. Off-topic questions (e.g. weather) are abstained.
5. Citation selection keeps chunks close to the best match and picks the most relevant section;
   citations are constructed deterministically from stored metadata — never generated by the LLM.
6. Only after validation does the provider generate an answer. The mock provider extracts sentences
   that overlap with the question and labels itself in the output.

### Version intelligence

- Each version has an `effective_from` date, an optional label, and a status
  (`active` / `superseded` / `draft` / `failed`).
- A year in the question ("in 2025") selects versions whose effective window contains that year —
  never simply the highest version number.
- Future-year questions are rejected when no version covers that year (`not_covered`), rather than
  silently answering with the latest policy.
- If multiple versions are equally valid and cannot be disambiguated deterministically, the
  assistant asks for clarification instead of choosing one.
- Adding a newer version refreshes supersession statuses for the document; historical questions can
  still retrieve superseded versions.

### Batch processing

CSV upload → row validation (a `question` column is required; optional `id` is preserved) → background
processing with periodic progress commits → results CSV with columns `question, answer, status,
source_document, document_version, page_number, section`. Failed rows are counted separately and do
not abort the job. Results are downloadable from the UI or API.

---

## API reference

Base URL: `http://127.0.0.1:8000`. All application routes are under `/api` except `/health`.

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness, provider and index summary |
| GET | `/api/stats` | Dashboard metrics |
| GET | `/api/system/settings` | Runtime configuration (no secrets) |
| GET | `/api/index/status` | Index backend, size, freshness |
| POST | `/api/index/rebuild` | Rebuild the vector/BM25 index from stored chunks |
| POST | `/api/documents/upload` | Upload one document (multipart; `effective_from`, `version_label`) |
| POST | `/api/documents/upload-multiple` | Upload up to 20 documents |
| GET | `/api/documents` | List/search documents (`search`, `status`, `file_type`, `limit`, `offset`) |
| GET | `/api/documents/{id}` | Document details, versions and chunks |
| DELETE | `/api/documents/{id}` | Delete document, versions, chunks and index entries |
| GET | `/api/documents/{id}/versions` | List versions (newest first) |
| POST | `/api/documents/{id}/versions` | Add a version (`effective_from`, `version_label`, `supersedes_version_id`) |
| POST | `/api/chat/ask` | Ask a question (`question`, optional `conversation_id`, `document_ids`, `version_ids`) |
| POST | `/api/chat/conversations` | Create a conversation |
| GET | `/api/chat/conversations` | List conversations |
| GET | `/api/chat/conversations/{id}` | Conversation with messages |
| DELETE | `/api/chat/conversations/{id}` | Delete a conversation |
| POST | `/api/batch/upload` | Upload a questions CSV |
| GET | `/api/batch/jobs` | List batch jobs |
| GET | `/api/batch/{id}/status` | Job progress |
| GET | `/api/batch/{id}/download` | Download the results CSV |

Answer statuses: `answered`, `partially_answered`, `not_covered`. `requires_clarification` is true
when a version ambiguity needs the user's input. Interactive docs: `/docs`.

---

## Postman

1. Start the backend.
2. In Postman, **Import** both files from `backend/postman/`:
   - `VeriDox AI.postman_collection.json`
   - `VeriDox AI - Local.postman_environment.json`
3. Select the **VeriDox AI - Local** environment.
4. Run the requests in order. The upload requests store `document_id`, the conversation request
   stores `conversation_id`, and the batch upload stores `batch_job_id` as collection variables.

The file pickers in the collection point at `scripts/demo_documents/...`; if Postman cannot resolve
a path, select the file manually in the form-data row.

---

## Docker

```bash
docker compose up --build
```

Then open <http://127.0.0.1:8000>. The SQLite database, uploads and indexes persist in `./data`
through a bind mount. Copy `.env.example` to `.env` to configure a real provider; the compose file
loads it when present.

The image is a multi-stage build: Node 22 builds the React app, and Python 3.13 installs the pinned
backend requirements and serves both the API and the built UI.

> The Docker configuration is provided but **was not built in this environment** (Docker was not
> installed). The equivalent process — frontend build + backend serving from `frontend/dist` — was
> verified locally on Windows.

---

## Database

- SQLite by default at `data/knowledge.db`; override with `DATABASE_URL`.
- Tables: `documents`, `document_versions`, `document_chunks`, `conversations`, `chat_messages`,
  `batch_jobs`.
- Tables are created on startup (`Base.metadata.create_all`). There is **no Alembic migration
  pipeline** in this build.
- Deleting the database file (with the backend stopped) resets all state. Uploaded files and index
  files remain under `data/`; remove those folders for a completely clean start.
- Datetimes are stored and returned as UTC.

---

## Implemented vs. not implemented

### Implemented
- PDF/TXT/Markdown upload, validation, deduplication, extraction, OCR fallback, cleaning, section
  detection, chunking, embeddings, FAISS/NumPy indexing, BM25, RRF fusion, optional reranking.
- Deterministic citation construction with document/version/page/section/excerpt/relevance.
- Three-state answer statuses and clarification flow.
- Effective-date based version selection, supersession, status refresh, historical queries.
- Conversation persistence and follow-ups.
- CSV batch processing with progress and downloadable results.
- Dashboard, document library, document detail drawer, source viewer with highlighted clause,
  batch page, settings page.
- Structured error envelope, request validation, configurable CORS, structured logging.
- pytest suite (55 tests) covering health, documents, versions, chat, citations, abstention, batch,
  index and unit services.
- Postman collection, demo seed script and demo corpus, Docker files.

### Not implemented
- **Server-side authentication / authorisation, SSO, tenants or RBAC.** The login screen is a
  client-side demo gate; it does not call the API and accepts any non-empty input. Do not deploy
  this build on an untrusted network.
- Database migrations (Alembic), task queue (Celery/RQ) or distributed workers — background jobs use
  FastAPI `BackgroundTasks` and run in-process.
- OCR is optional and depends on external Tesseract; it is not bundled.
- Real LLM calls are optional; the default mock provider is not a generative model.
- Streaming answers (responses are returned in one JSON payload).
- Docx/XLSX/HTML ingestion, web crawling or connectors.
- Analytics beyond the dashboard counters.

---

## Known limitations

- **Hashing embeddings are lexical.** They work offline and deterministically, but paraphrases and
  synonyms are matched poorly compared with neural embeddings. Use `sentence-transformers` for
  better semantic recall.
- **Extra citations are possible.** Retrieval can include a chunk that shares vocabulary with the
  question without containing the answer (for example, a study-leave clause mentioning annual
  leave). The excerpt and section are always real and deterministic; relevance is shown so users can
  judge. The mock answer only extracts sentences with question-term overlap.
- **Abstention thresholds are calibrated for the hashing provider.** With neural embeddings or a
  different corpus, review `MIN_VECTOR_SIMILARITY` and `MIN_ANSWER_SIMILARITY`; they are exposed in
  configuration on purpose.
- **Page/section metadata depends on extraction.** Scanned PDFs without OCR may have little metadata,
  and the page number falls back to the chunk's first page.
- **BM25 statistics live in memory** and are rebuilt at startup from stored chunks; very large
  corpora would need a persistent lexical index.
- **Single-process background work.** A restart marks in-flight jobs as failed (they can be
  re-uploaded); long batches occupy an in-process worker.
- **Mock provider output is extractive**, not generative. It is labelled in the answer text, the UI
  banner, the API `provider` field and the batch results.
- **Demo login is cosmetic.** No credentials are sent anywhere or stored server-side.

---

## Verification and test results

Executed in this workspace on **2026-10-30**:

| Check | Result |
|---|---|
| Backend test suite (`python -m pytest` in `backend/`) | **55 passed in 4.11s** |
| Environment | Python 3.14.0, Windows 10.0.26300, Node 24.18.0 |
| Frontend production build | Passed — 44 modules, `dist/assets` JS ~292 kB, CSS ~45.7 kB |
| Demo seeding | 9 files → 8 documents, 8 completed, 27 chunks; leave policy has 2 versions |
| Chat — annual leave 2026 | `answered`, cites the 2026.1 leave version |
| Chat — sick leave 2025 | `answered`, cites the 2025.1 version |
| Chat — notice period / lost badge | `not_covered` (not in corpus) |
| Chat — weather in Bengaluru | `not_covered` (off-topic abstention) |
| Batch — `scripts/demo_batch_questions.csv` | Completed 10/10; 6 answered, 1 partial, 3 not covered |
| Batch CSV download | Verified columns and content |
| Browser smoke test | Login, chat with citations/source viewer, library, document drawer (superseded version), dashboard, batch, settings; no console errors on a clean load |

The tests exercise the real application with a temporary SQLite database; they do not call paid
external APIs and do not require network access.

---

## Security notes

- Uploads are treated as untrusted: extension allow-list, size cap, generated safe filenames,
  resolved-path checks (no traversal), per-file error isolation, and content hashing for duplicates.
- Text-based uploads are decoded synchronously and binary payloads disguised as text are rejected.
- Answers are constructed only from retrieved chunks; the system prompt instructs the model to use
  only the supplied evidence and to state when it is insufficient. Citations are not model output.
- API errors return a structured envelope (`{"error": {"code", "message", "details"}}`) without
  stack traces, file paths or document contents. Unexpected errors are logged server-side.
- CORS is configurable via `CORS_ORIGINS`; `*` is a local-development default.
- Secrets are read from environment variables only and are excluded from responses, logs and
  `.env.example`.
- There is **no authentication**. Run locally or place the API behind an authenticating reverse proxy
  before exposing it.

---

## Attribution

This project is an original implementation. The ChatPDF ecosystem informed the general product idea
of "chat with documents"; no source code was copied from ChatPDF or any other repository (the
reference repository was not present in this workspace). If you adapt this project, keep this notice
and respect the licences of the dependencies listed in `backend/requirements*.txt` and
`frontend/package.json`.
