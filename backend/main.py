"""FastAPI application entry point for LegalRAG.

Per CONTEXT.md D-01~D-08:
  - D-01: Routes organized by resource (documents router registered here).
  - D-02: Engine instances as app.state singletons.
  - D-03: API prefix /api/v1.
  - D-04: Global exception handlers.
  - D-05: Async document indexing via BackgroundTasks.
  - D-06: Unified response wrapper.
  - D-07: Health check endpoint.
  - D-08: CORS permissive in development.
"""
import logging
import os
import sqlite3

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.chat import router as chat_router
from backend.api.documents import router as documents_router
from backend.api.search import router as search_router

logger = logging.getLogger(__name__)

# ── App Factory ────────────────────────────────────────────────────────────

app = FastAPI(
    title="LegalRAG API",
    version="1.0.0",
    description="Backend API for LegalRAG — Legal Document Q&A System",
)

# ── CORS (D-08) ────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Unified Error Response ─────────────────────────────────────────────────


def _error_response(status_code: int, detail: str) -> JSONResponse:
    """Return a unified error response per D-06."""
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "data": None, "error": detail},
    )


# ── Exception Handlers (D-04) ──────────────────────────────────────────────


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return unified error response."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return _error_response(500, f"Internal server error: {exc}")


# ── Lifecycle Events ───────────────────────────────────────────────────────


@app.on_event("startup")
async def startup():
    """Initialise app-level singletons (D-02, D-05)."""
    from backend.storage.metadata_store import MetadataStore
    from backend.pipeline.indexer import Indexer
    from backend.retrieval.vector_search import VectorSearch
    from backend.retrieval.bm25 import BM25Retriever

    logger.info("Starting LegalRAG API — initialising singletons")

    # Engine singletons
    app.state.metadata_store = MetadataStore()
    app.state.indexer = Indexer()

    # Pre-initialise retrieval singletons so their first use is fast
    vs = VectorSearch.get_instance()
    bm = BM25Retriever.get_instance()

    # Restore FAISS index from disk if it exists
    faiss_path = "data/index/vector.faiss"
    if os.path.exists(faiss_path):
        try:
            vs.load(faiss_path)
            logger.info("Loaded FAISS index from %s (%d vectors)", faiss_path, vs.size)
        except Exception as exc:
            logger.warning("Could not load FAISS index: %s", exc)

    # Rebuild BM25 index from existing chunks in the database
    try:
        all_chunks = app.state.metadata_store.get_all_chunks()
        if all_chunks:
            texts = [c.text for c in all_chunks]
            ids = [c.id for c in all_chunks]
            bm.build_index(texts, ids)
            logger.info("Rebuilt BM25 index with %d chunks", len(texts))
    except Exception as exc:
        logger.warning("Could not rebuild BM25 index: %s", exc)

    # Per-document async processing status (D-05)
    app.state.processing_status = {}
    # Mark documents that already have chunks as "ready"
    try:
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(app.state.metadata_store.db_path)
        c = conn.cursor()
        c.execute("SELECT id FROM documents")
        doc_ids = [row[0] for row in c.fetchall()]
        conn.close()
        for doc_id in doc_ids:
            chunks = app.state.metadata_store.get_chunks_by_doc_id(doc_id)
            if chunks:
                app.state.processing_status[doc_id] = "ready"
        if doc_ids:
            ready_count = sum(1 for d in doc_ids if d in app.state.processing_status)
            logger.info("Restored processing status: %d/%d documents ready", ready_count, len(doc_ids))
    except Exception as exc:
        logger.warning("Could not restore document statuses: %s", exc)

    # Citation retrieval buffer for Plan 2 (chat endpoint)
    app.state.last_chat_sources = []

    logger.info("LegalRAG API startup complete")


@app.on_event("shutdown")
async def shutdown():
    """Log shutdown event."""
    logger.info("LegalRAG API shutting down")


# ── Routes (D-03) ──────────────────────────────────────────────────────────

app.include_router(documents_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")


# ── Health Endpoint (D-07) ─────────────────────────────────────────────────


@app.get("/api/v1/health")
async def health(request: Request):
    """Check system health: Ollama, SQLite, FAISS, BM25, Embedder."""
    # --- SQLite ---
    try:
        conn = sqlite3.connect(request.app.state.metadata_store.db_path)
        conn.execute("SELECT 1")
        conn.close()
        sqlite_status = "ok"
    except Exception:
        sqlite_status = "error"

    # --- FAISS index ---
    from backend.retrieval.vector_search import VectorSearch
    faiss_path = "data/index/vector.faiss"
    faiss_has_file = os.path.exists(faiss_path)
    faiss_has_vectors = VectorSearch.get_instance().size > 0
    faiss_status = "ok" if faiss_has_file and faiss_has_vectors else "error"

    # --- Ollama ---
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            ollama_status = "ok" if resp.status_code == 200 else "error"
    except Exception:
        ollama_status = "error"

    # --- BM25 ---
    from backend.retrieval.bm25 import BM25Retriever
    try:
        bm25 = BM25Retriever.get_instance()
        bm25_status = "ok" if bm25.bm25 is not None and len(bm25.corpus) > 0 else "error"
    except Exception:
        bm25_status = "error"

    # --- Embedder ---
    from backend.embedding.embedder import Embedder
    try:
        embedder = Embedder.get_instance()
        embedder.model.encode(["health check"], batch_size=1)
        embedder_status = "ok"
    except Exception:
        embedder_status = "error"

    return {
        "status": "ok",
        "data": {
            "ollama": ollama_status,
            "sqlite": sqlite_status,
            "faiss": faiss_status,
            "bm25": bm25_status,
            "embedder": embedder_status,
        },
        "error": None,
    }
