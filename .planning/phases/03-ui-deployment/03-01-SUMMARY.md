---
phase: 03-ui-deployment
plan: 01
subsystem: api, ui
tags: [fastapi, streamlit, rest-api, pdf-upload, cors, background-tasks]

requires:
  - phase: 01-core-retrieval-engine
    provides: MetadataStore, Indexer, VectorSearch, BM25Retriever, Document/Chunk models
provides:
  - FastAPI backend application framework with CORS, exception handlers, health endpoint, lifecycle events
  - Documents REST API (upload, list, status, chunks) with async indexing via BackgroundTasks
  - Streamlit multi-page entry point with sidebar navigation and document selector
  - Streamlit Documents page with upload interface, polling status, document list cards
affects: [03-ui-deployment Plan 2 (chat, search, preview, docker)]

tech-stack:
  added: [fastapi, uvicorn, streamlit, requests, python-multipart]
  patterns:
    - D-06 Unified response wrapper: {"status": "ok"|"error", "data": ..., "error": null|str}
    - D-02 Engine instances registered as app.state singletons
    - D-05 Async document indexing via BackgroundTasks + polling endpoint
    - D-08 CORS permissive in development (allow_origins=["*"])

key-files:
  created:
    - backend/main.py (FastAPI entry point with CORS, health, lifecycle, documents router)
    - backend/api/__init__.py (package marker)
    - backend/api/documents.py (5-endpoint documents API router)
    - app/__init__.py (package marker)
    - app/main.py (Streamlit entry with sidebar navigation and document selector)
    - app/pages/__init__.py (package marker)
    - app/pages/1_Documents.py (Documents page with upload, list, status polling)
    - app/components/__init__.py (package marker)
  modified: []

key-decisions:
  - "POST /upload at /api/v1/documents/upload instead of POST /api/v1/documents/ to match Streamlit frontend contract"
  - "STREAMLIT FRONTEND calls /api/v1/documents/upload for upload; no sub-path conflict with GET /api/v1/documents/ for list"
  - "D-09: Three-page navigation (Documents, Chat, Preview) with st.sidebar.radio"
  - "D-11: Document selector populated via /api/v1/documents call in sidebar"
  - "UI-SPEC color palette applied via CSS injection in st.markdown"

patterns-established:
  - "API Router pattern: one router per resource (backend/api/documents.py)"
  - "Background task pattern: FastAPI BackgroundTasks + polling endpoint for async doc processing"
  - "Unified JSON response wrapper across all endpoints"
  - "Streamlit page structure: main.py with sidebar + pages/1_Documents.py"

requirements-completed: [API-01, API-02, API-05, UI-01, UI-02]

duration: 12min
completed: 2026-05-15
---

# Phase 3 Plan 1: Documents Vertical Slice Summary

**FastAPI backend framework with CORS, health check, lifecycle singletons, and 5-endpoint documents API; Streamlit multi-page frontend with sidebar navigation and Documents upload/list page**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-15T06:30:00Z
- **Completed:** 2026-05-15T06:42:00Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- **FastAPI backend** (backend/main.py): Application factory with CORS middleware (`allow_origins=["*"]` per D-08), global exception handler returning unified error responses (D-06), health endpoint checking Ollama/SQLite/FAISS status (D-07), startup event initialising MetadataStore, Indexer, VectorSearch, and BM25Retriever singletons (D-02) with `processing_status` dict for async status tracking (D-05) and `last_chat_sources` buffer for Plan 2
- **Documents API** (backend/api/documents.py): 5 endpoints — POST `/upload` with PDF content-type validation (T-3-01), filename sanitisation (T-3-05), 50 MB file size limit, dedup check, and BackgroundTasks-based async indexing; GET `/` listing all documents with status and chunk count; GET `/{id}` single document lookup; GET `/{id}/status` polling endpoint (D-05); GET `/{id}/chunks` chunk retrieval for preview (D-12). All endpoints use unified response wrapper
- **Streamlit entry point** (app/main.py): Page config with `page_title="LegalRAG"` and wide layout, UI-SPEC color palette CSS injection (`#1E3A5F` accent, `#F0F2F6` sidebar, `#1A202C` text), sidebar navigation radio (Documents/Chat/Preview per D-10), document selector dropdown populated from `/api/v1/documents` (D-11), API_BASE env-var-aware URL
- **Streamlit Documents page** (app/pages/1_Documents.py): Empty state with dashed-border upload area and UI-SPEC copy ("Upload a PDF legal document to begin"), file uploader widget restricting to PDF, upload flow with progress spinner and polling loop checking `/api/v1/documents/{id}/status` every 2 seconds, status badge rendering (amber Indexing → green Ready → red Error), document list cards with icon, filename, date, chunk count, and click-to-select
- **Threat model mitigations**: T-3-01 (content-type validation, 50 MB limit), T-3-05 (path traversal prevention via os.path.basename)

## Task Commits

Each task was committed atomically:

1. **Task 1: FastAPI backend framework with documents API** - `6435fc5` (feat)
2. **Task 2: Streamlit entry point with sidebar navigation and Documents page** - `7265d90` (feat)

**Plan metadata:** (pending — final commit at end)

## Files Created/Modified

- `backend/main.py` — FastAPI app factory, CORS middleware, exception handlers, health endpoint, lifecycle events, documents router registration
- `backend/api/__init__.py` — Package marker (empty)
- `backend/api/documents.py` — 5-endpoint documents API router with BackgroundTasks async indexing
- `app/__init__.py` — Package marker (empty)
- `app/main.py` — Streamlit entry point, sidebar navigation, document selector, CSS styling
- `app/pages/__init__.py` — Package marker (empty)
- `app/pages/1_Documents.py` — Document upload interface, polling, list cards, status badges
- `app/components/__init__.py` — Package marker (empty)

## Decisions Made

- **Upload endpoint at `/upload`** — POST `/api/v1/documents/upload` instead of bare POST `/api/v1/documents/` to match Streamlit frontend contract and avoid confusion with the list endpoint
- **Three-page navigation** — D-09 layout: Documents page first (`1_Documents.py`), Chat (`2_Chat.py`) and Preview (`3_Preview.py`) deferred to Plan 2
- **Health endpoint checks** — SQLite connectivity, FAISS index file existence, Ollama API reachability per D-07
- **Startup singleton order** — MetadataStore and Indexer created first, then VectorSearch/BM25Retriever singletons pre-initialised via `get_instance()` for fast first-use

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- FastAPI `TestClient` requires context manager (`with TestClient(app) as client:`) to trigger startup events — health endpoint worked directly, documents endpoint needed context-managed client. Verification updated accordingly.

## User Setup Required

None — no external service configuration required. Backend runs with `uvicorn backend.main:app`, frontend with `streamlit run app/main.py`.

## Next Phase Readiness

- FastAPI app framework ready for Plan 2 endpoints (chat, search, preview)
- Documents API fully functional — Plan 2 chat endpoint can consume MetadataStore and Indexer singletons already registered in app.state
- Streamlit pages for Chat and Preview (2_Chat.py, 3_Preview.py) need to be added in Plan 2
- Docker deployment can reference existing backend.main:app and app/main.py

---
*Phase: 03-ui-deployment*
*Plan: 01*
*Completed: 2026-05-15*
