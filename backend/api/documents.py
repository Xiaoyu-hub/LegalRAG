"""Documents API router — upload, list, status, chunks.

Per D-01: Routes organized by resource.
Per D-05: Async document indexing via BackgroundTasks + polling endpoint.
Per D-06: Unified response wrapper: {"status": "ok"|"error", "data": ..., "error": null|str}.
"""
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, UploadFile

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


def _validate_filename(filename: str) -> str:
    """Sanitize and validate filename per T-3-05 (path traversal prevention)."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename: path traversal detected")
    return os.path.basename(filename)


# ── Background Task ────────────────────────────────────────────────────────


def process_document_task(doc_id: int, file_path: str, app_state, rebuild: bool = False,
                          tenant: str = "demo"):
    """Run full indexing pipeline as a background task.

    On success: marks status as "ready".
    On failure: marks status as "error" and logs the traceback.

    rebuild=True 时在索引完后从数据库全量重建 FAISS + BM25：替换/删除文档后，
    旧 chunk 的向量还留在索引里，不清掉会检索到已删除的条文。
    """
    logger.info("Starting background processing for doc_id=%d, file_path=%s, tenant=%s",
                doc_id, file_path, tenant)
    try:
        indexer: Indexer = app_state.indexers[tenant]
        indexer.process_document(file_path, doc_id=doc_id)
        if rebuild:
            n = indexer.rebuild_all()
            logger.info("[%s] Rebuilt indexes after replacement: %d chunks", tenant, n)
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
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
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
    tenant = x_tenant_id or "demo"
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return _unified_response("error", None, "File size exceeds 50 MB limit")

    # --- 文件按租户分目录保存，同名文件不会互相覆盖 ---
    upload_dir = os.path.join(UPLOAD_DIR, tenant)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # --- Dedup: 同名视为「替换」，先删旧记录（CASCADE 清 chunks）再当新文档 ---
    metadata_store: MetadataStore = request.app.state.metadata_store
    existing = metadata_store.get_document_by_filename(filename, tenant=tenant)
    replaced = False
    if existing is not None:
        # 文件已在上面覆盖写入，旧路径就是同一个 path
        metadata_store.delete_document(existing.id)
        request.app.state.processing_status.pop(existing.id, None)
        replaced = True
        logger.info("[%s] Replaced existing document %d (%s)", tenant, existing.id, filename)

    doc = Document(filename=filename, file_path=file_path, file_size=len(content),
                   tenant=tenant)
    doc_id = metadata_store.insert_document(doc)

    # --- Launch background indexing ---
    request.app.get_indexer(tenant)  # 确保该租户的 Indexer 已建
    request.app.state.processing_status[doc_id] = "processing"
    background_tasks.add_task(
        process_document_task, doc_id, file_path, request.app.state, replaced, tenant
    )

    return _unified_response("ok", {
        "document_id": doc_id,
        "filename": filename,
        "status": "processing",
        "replaced": replaced,
    }, None)


@router.get("/")
async def list_documents(request: Request,
                        x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")):
    """List all uploaded documents with status and chunk count（仅当前租户）。"""
    tenant = x_tenant_id or "demo"
    metadata_store: MetadataStore = request.app.state.metadata_store
    documents = []
    for doc in metadata_store.get_all_documents(tenant):
        doc_dict = {
            "id": doc.id,
            "filename": doc.filename,
            "title": doc.title,
            "page_count": doc.page_count,
            "file_path": doc.file_path,
            "file_size": doc.file_size,
            "created_at": str(doc.created_at) if doc.created_at else "",
            "status": request.app.state.processing_status.get(doc.id, "unknown"),
            "chunk_count": len(metadata_store.get_chunks_by_doc_id(doc.id)),
        }
        documents.append(doc_dict)
    return _unified_response("ok", {"documents": documents}, None)


@router.get("/{doc_id}")
async def get_document(doc_id: int, request: Request,
                       x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")):
    """Get a single document by ID with status and chunk count."""
    tenant = x_tenant_id or "demo"
    metadata_store: MetadataStore = request.app.state.metadata_store
    doc = metadata_store.get_document(doc_id, tenant=tenant)
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
        "chunk_count": len(metadata_store.get_chunks_by_doc_id(doc_id)),
    }, None)


@router.get("/{doc_id}/status")
async def get_document_status(doc_id: int, request: Request,
                              x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")):
    """Poll processing status for a document (D-05)."""
    tenant = x_tenant_id or "demo"
    metadata_store: MetadataStore = request.app.state.metadata_store
    doc = metadata_store.get_document(doc_id, tenant=tenant)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    status = request.app.state.processing_status.get(doc_id, "unknown")
    return _unified_response("ok", {
        "document_id": doc_id,
        "processing_status": status,
        "chunk_count": len(metadata_store.get_chunks_by_doc_id(doc_id)) if status == "ready" else 0,
    }, None)


@router.get("/{doc_id}/chunks")
async def get_document_chunks(doc_id: int, request: Request,
                              x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")):
    """Get all chunks for a document preview (D-12)."""
    tenant = x_tenant_id or "demo"
    metadata_store: MetadataStore = request.app.state.metadata_store
    doc = metadata_store.get_document(doc_id, tenant=tenant)
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
