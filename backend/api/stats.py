"""运营视角的统计接口：前端仪表盘用。

和 /health 的分工：/health 回答「各组件活没活」，这里回答「库里到底有多少东西」。
两者都从数据库算，不做内存计数——重启后数字必须还对。
"""
import logging
import os

from fastapi import APIRouter, Depends, Request

from backend.api.deps import resolve_tenant
from backend.storage.conversation_store import ConversationStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["stats"])


def _dir_size(path: str) -> int:
    total = 0
    if not os.path.isdir(path):
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


@router.get("")
async def stats(request: Request, tenant: str = Depends(resolve_tenant)):
    metadata_store = request.app.state.metadata_store

    documents = metadata_store.get_all_documents(tenant)
    chunk_count = metadata_store.get_chunk_count(tenant)
    status_map = getattr(request.app.state, "processing_status", {}) or {}
    ready = sum(1 for d in documents if status_map.get(d.id) == "ready")
    processing = sum(1 for d in documents if status_map.get(d.id) == "processing")
    failed = sum(1 for d in documents if status_map.get(d.id) == "error")

    conv_store = getattr(request.app.state, "conversation_store", None)
    if conv_store is None:
        conv_store = ConversationStore()
        request.app.state.conversation_store = conv_store
    chat = conv_store.count(tenant)

    # 向量条数按租户取：索引与库不一致时这个数字会说话
    vectors = {}
    try:
        from backend.retrieval.vector_search import VectorSearch
        for t in (metadata_store.list_tenants() or ["demo"]):
            vectors[t] = VectorSearch.get_instance(tenant=t).size
    except Exception as exc:
        logger.warning("vector size unavailable: %s", exc)

    return {
        "status": "ok",
        "data": {
            "tenant": tenant,
            "documents": len(documents),
            "documents_ready": ready,
            "documents_processing": processing,
            "documents_failed": failed,
            "chunks": chunk_count,
            "vectors": vectors.get(tenant, 0),
            "conversations": chat["conversations"],
            "messages": chat["messages"],
            "storage_bytes": _dir_size(os.path.join("data", "documents", tenant)),
            "recent_documents": [
                {
                    "id": d.id,
                    "filename": d.filename,
                    "page_count": d.page_count,
                    "file_size": d.file_size,
                    "status": status_map.get(d.id, "unknown"),
                }
                for d in documents[:5]
            ],
        },
        "error": None,
    }
