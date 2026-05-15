"""Documents API router — upload, list, status, chunks.

Per D-01: Routes organized by resource.
Per D-05: Async document indexing via BackgroundTasks + polling endpoint.
Per D-06: Unified response wrapper: {"status": "ok"|"error", "data": ..., "error": null|str}.
"""
import logging
import os
import sqlite3

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile

from backend.pipeline.indexer import Indexer
from backend.models.document import Document
from backend.storage.metadata_store import MetadataStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# ── Constants ──────────────────────────────────────────────────────────────

UPLOAD_DIR = "data/documents"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB (T-3-01)

# ── Helpers ────────────────────────────────────────────────────────────────


def _unified_response(status: str, data, error: str = None) -> dict:
    """Unified response wrapper per D-06."""
    return {"status": status, "data": data, "error": error}


def _get_chunk_count_by_doc_id(db_path: str, doc_id: int) -> int:
    """Count chunks for a document via direct SQLite query."""
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,))
        row = c.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def _get_all_documents(db_path: str) -> list[dict]:
    """Fetch all documents via direct SQLite query.

    MetadataStore does not expose get_all_documents(), so we query
    SQLite directly per PLAN.md instructions.
    """
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("SELECT id, filename, title, page_count, file_path, file_size, created_at "
                   "FROM documents ORDER BY created_at DESC")
        rows = c.fetchall()
        return [
            {
                "id": row[0],
                "filename": row[1],
                "title": row[2],
                "page_count": row[3],
                "file_path": row[4],
                "file_size": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]
    finally:
        conn.close()


def _validate_filename(filename: str) -> str:
    """Sanitize and validate filename per T-3-05 (path traversal prevention)."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename: path traversal detected")
    return os.path.basename(filename)


# ── Background Task ────────────────────────────────────────────────────────


def process_document_task(doc_id: int, file_path: str, app_state):
    """Run full indexing pipeline as a background task.

    On success: marks status as "ready".
    On failure: marks status as "error" and logs the traceback.
    """
    logger.info("Starting background processing for doc_id=%d, file_path=%s", doc_id, file_path)
    try:
        indexer: Indexer = app_state.indexer
        indexer.process_document(file_path)
        app_state.processing_status[doc_id] = "ready"
        logger.info("Document %d processed successfully", doc_id)
    except Exception as exc:
        app_state.processing_status[doc_id] = "error"
        logger.error("Failed to process document %d: %s", doc_id, exc, exc_info=True)


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.post("/upload")
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Upload a PDF document for parsing and indexing.

    Threat mitigations:
      - T-3-01: Validate content_type is "application/pdf"; 50 MB limit.
      - T-3-05: Sanitise filename via os.path.basename(); reject path traversal.
    """
    # --- Validate content type (T-3-01) ---
    content_type = file.content_type or ""
    if not content_type.startswith("application/pdf"):
        return _unified_response("error", None, "Only PDF files are supported")

    # --- Validate and sanitise filename (T-3-05) ---
    try:
        filename = _validate_filename(file.filename or "document.pdf")
    except HTTPException as exc:
        return _unified_response("error", None, exc.detail)

    # --- Read content and enforce size limit ---
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return _unified_response("error", None, "File size exceeds 50 MB limit")

    # --- Save file to disk ---
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # --- Dedup: skip re-indexing if this filename already exists ---
    metadata_store: MetadataStore = request.app.state.metadata_store
    db_path = metadata_store.db_path
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM documents WHERE filename = ?", (filename,))
        row = c.fetchone()
        doc_id = row[0] if row else None
    finally:
        conn.close()

    if doc_id is None:
        doc = Document(filename=filename, file_path=file_path, file_size=len(content))
        doc_id = metadata_store.insert_document(doc)

    # --- Launch background indexing ---
    request.app.state.processing_status[doc_id] = "processing"
    background_tasks.add_task(process_document_task, doc_id, file_path, request.app.state)

    return _unified_response("ok", {
        "document_id": doc_id,
        "filename": filename,
        "status": "processing",
    }, None)


@router.get("/")
async def list_documents(request: Request):
    """List all uploaded documents with status and chunk count."""
    metadata_store: MetadataStore = request.app.state.metadata_store
    db_path = metadata_store.db_path
    documents = _get_all_documents(db_path)
    for doc in documents:
        doc_id = doc["id"]
        doc["status"] = request.app.state.processing_status.get(doc_id, "unknown")
        doc["chunk_count"] = _get_chunk_count_by_doc_id(db_path, doc_id)
    return _unified_response("ok", {"documents": documents}, None)


@router.get("/{doc_id}")
async def get_document(doc_id: int, request: Request):
    """Get a single document by ID with status and chunk count."""
    metadata_store: MetadataStore = request.app.state.metadata_store
    doc = metadata_store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return _unified_response("ok", {
        "id": doc.id,
        "filename": doc.filename,
        "title": doc.title,
        "page_count": doc.page_count,
        "file_size": doc.file_size,
        "created_at": str(doc.created_at),
        "status": request.app.state.processing_status.get(doc_id, "unknown"),
        "chunk_count": _get_chunk_count_by_doc_id(metadata_store.db_path, doc_id),
    }, None)


@router.get("/{doc_id}/status")
async def get_document_status(doc_id: int, request: Request):
    """Poll processing status for a document (D-05)."""
    metadata_store: MetadataStore = request.app.state.metadata_store
    doc = metadata_store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    status = request.app.state.processing_status.get(doc_id, "unknown")
    return _unified_response("ok", {
        "document_id": doc_id,
        "processing_status": status,
        "chunk_count": _get_chunk_count_by_doc_id(metadata_store.db_path, doc_id) if status == "ready" else 0,
    }, None)


@router.get("/{doc_id}/chunks")
async def get_document_chunks(doc_id: int, request: Request):
    """Get all chunks for a document preview (D-12)."""
    metadata_store: MetadataStore = request.app.state.metadata_store
    doc = metadata_store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    chunks = metadata_store.get_chunks_by_doc_id(doc_id)
    return _unified_response("ok", {
        "chunks": [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "text": c.text,
                "article": c.article,
                "section": c.section,
                "subsection": c.subsection,
                "title": c.title,
                "parent_article": c.parent_article,
            }
            for c in chunks
        ],
    }, None)
