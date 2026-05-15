# Phase 3: UI & Deployment - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers the user-facing frontend and backend API layer for LegalRAG, plus Docker deployment. It includes:
- FastAPI backend with RESTful endpoints for document management, chat, and search
- Streamlit multi-page frontend for document upload, Q&A, and document preview
- Citation display with interactive source references
- Multi-turn conversation support with streaming LLM output
- Docker + docker-compose for one-command deployment
- Documentation (README with setup instructions)

The backend core (pipeline, retrieval, generation) is already built in Phases 1 & 2. This phase wraps it with API endpoints and a UI.

</domain>

<decisions>
## Implementation Decisions

### FastAPI Backend Structure
- **D-01:** Routes organized by resource — `backend/api/documents.py`, `backend/api/chat.py`, `backend/api/search.py`
- **D-02:** Engine instances (MetadataStore, HybridSearch, GenerationPipeline) registered as app-level singletons via `app.state` — consistent with existing `get_instance()` pattern
- **D-03:** API prefix `/api/v1/xxx` — versioned path for future compatibility
- **D-04:** Global exception handlers via custom exception classes + `@app.exception_handler` — consistent error format
- **D-05:** Async document indexing via FastAPI `BackgroundTasks` + polling endpoint `GET /api/v1/documents/{id}/status` — zero extra dependencies
- **D-06:** Unified response wrapper: `{"status": "ok"|"error", "data": ..., "error": null|str}`
- **D-07:** Health check endpoint `GET /api/v1/health` — reports Ollama, SQLite, FAISS status
- **D-08:** CORS: permissive in development (allow Streamlit dev server origin), tighten in production via nginx reverse proxy

### Streamlit Page Layout
- **D-09:** Three-page structure using Streamlit native multi-page convention:
  - `1_Documents.py` — Document upload, list, and management
  - `2_Chat.py` — Q&A interface with answers and citations
  - `3_Preview.py` — Document structure preview (Article/Section hierarchy tree)
- **D-10:** Navigation via `st.sidebar.radio` — standard Streamlit pattern, clear to users
- **D-11:** Selected document state managed via `st.sidebar.selectbox` — dropdown of all indexed documents, globally visible, followed by Chat and Preview pages
- **D-12:** Document preview as independent page — suitable for thorough reading of parsed structure

### Chat Experience
- **D-13:** Multi-turn conversation — chat history maintained via `st.session_state`, supports follow-up questions with context carried forward
- **D-14:** Streaming output — LLM response displayed token-by-token via `st.write_stream` for lower perceived latency
- **D-15:** Retrieved chunk sources shown in collapsible expander below each answer — transparent and verifiable
- **D-16:** Citation markers rendered as clickable elements — expanding to show source chunk text inline

### Agent's Discretion
- Specific Streamlit component implementation details (citation box rendering, preview tree structure)
- Error message content and UX for API errors
- CSS/styling choices within Streamlit's capabilities
- Docker multi-stage build details (e.g., base image selection)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — Project overview, core value, constraints
- `.planning/REQUIREMENTS.md` — Full requirements with REQ-IDs (API-01~05, UI-01~06)
- `.planning/ROADMAP.md` — Phase 3 success criteria and technical notes

### Prior Phase Context
- `.planning/phases/01-core-retrieval-engine/01-CONTEXT.md` — Phase 1 decisions (chunk model, retrieval pipeline, evaluation)
- `.planning/phases/02-generation-citations/02-CONTEXT.md` — Phase 2 decisions (generation pipeline, citation format, prompt strategy)

### Architecture Reference
- `architecture.md` — System architecture, directory layout, data flow (section 2.2 for UI directory layout)

### No External Specs
No external specifications — requirements fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/generation/pipeline.py`: `GenerationPipeline` class with `answer(query)` method — ready for FastAPI chat endpoint to wrap
- `backend/pipeline/indexer.py`: `Indexer.process_document(file_path)` — full pipeline from PDF to indexed chunks, callable from document upload endpoint
- `backend/storage/metadata_store.py`: `MetadataStore` — document and chunk queries for API responses and document preview
- `backend/models/document.py`, `backend/models/chunk.py`, `backend/models/citation.py`: Dataclasses already structured for API serialization
- `configs/prompts.yaml` — Generation prompt templates, loaded by PromptBuilder

### Established Patterns
- Class-based modules with `__init__.py` re-exports — consistent import pattern
- Singleton via `get_instance()` for Embedder, VectorSearch, BM25Retriever — API layer should respect this pattern
- `logging.getLogger(__name__)` throughout — API layer should follow the same convention
- SQLite + FAISS storage model — API endpoints query both for responses

### Integration Points
- `/api/v1/documents/upload` → calls `Indexer.process_document()` in background task
- `/api/v1/documents` → calls `MetadataStore.get_document()` / `get_chunks_by_doc_id()`
- `/api/v1/chat` → instantiates `GenerationPipeline(retriever=HybridSearch(), metadata_store=MetadataStore())` and calls `.answer(query)`
- `/api/v1/search` → wraps `HybridSearch.search()` for raw retrieval results
- Streamlit Documents page → calls `/api/v1/documents/*` endpoints
- Streamlit Chat page → calls `/api/v1/chat` endpoint, displays streaming response + citations
- Streamlit Preview page → calls `/api/v1/documents/{id}/chunks` for structure display

</code_context>

<specifics>
## Specific Ideas

Based on the architecture document:
- Streamlit app directory structure follows `app/main.py` + `app/pages/1_Documents.py`, `2_Chat.py` + `app/components/citation_box.py`, `doc_preview.py`
- FastAPI backend follows `backend/main.py` + `backend/api/documents.py`, `chat.py`, `search.py`
- Generation pipeline already supports the `answer(query)` interface — no changes needed for chat integration
- Docker deployment includes Ollama as a separate service in docker-compose

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. All Phase 3 requirements are committed.

</deferred>

---

*Phase: 3-UI & Deployment*
*Context gathered: 2026-05-15*
