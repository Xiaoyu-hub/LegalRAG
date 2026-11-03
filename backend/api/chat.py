import logging

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.deps import resolve_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    document_id: int
    history: list[dict] = []
    # 会话级槽位：旧版把 sources 放在全局单槽，两个会话同时提问会互相覆盖
    session_id: str = "default"


def _remember_sources(state, session_id: str, sources: list, citations: list):
    """把某会话的 sources / citations 写进有上限的字典，避免无界增长。"""
    if not hasattr(state, "last_chat_sources") or not isinstance(state.last_chat_sources, dict):
        state.last_chat_sources = {}
        state.last_chat_citations = {}
    state.last_chat_sources[session_id] = sources
    state.last_chat_citations[session_id] = citations
    if len(state.last_chat_sources) > 200:
        oldest = next(iter(state.last_chat_sources))
        state.last_chat_sources.pop(oldest, None)
        state.last_chat_citations.pop(oldest, None)


@router.post("/")
async def chat(req: ChatRequest, request: Request, tenant: str = Depends(resolve_tenant)):
    from backend.generation.pipeline import GenerationPipeline
    from backend.retrieval.hybrid_search import HybridSearch


    if len(req.question) > 4096:
        return {
            "status": "error",
            "data": None,
            "error": "Question exceeds maximum length of 4096 characters",
        }

    store = request.app.state.metadata_store
    retriever = HybridSearch(tenant=tenant)
    pipeline = GenerationPipeline(
        retriever=retriever,
        metadata_store=store,
        reranker=getattr(request.app.state, "reranker", None),
    )

    async def stream_answer():
        for token in pipeline.answer_stream(req.question, document_id=req.document_id):
            yield token

        # 流式输出不回头改字，但引用校验必须跑：把每个 chunk 对应的引用状态
        # 一并放进 sources，前端能标出「哪条引用没在检索片段里找到」。
        valid_by_chunk: dict[int, list[bool]] = {}
        for c in pipeline.last_chunks:
            valid_by_chunk.setdefault(c.id, [])
        for cit in getattr(pipeline, "last_citations", []):
            for c in pipeline.last_chunks:
                if (c.article or "").replace("Article ", "").strip() == cit.article and \
                   (c.section or "").replace("Section ", "").strip() == cit.section:
                    valid_by_chunk[c.id].append(cit.valid)

        sources = [
            {
                "article": c.article,
                "section": c.section,
                "text": c.text[:500],
                "chunk_id": c.id,
                "citation_valid": all(valid_by_chunk.get(c.id, [True])),
            }
            for c in pipeline.last_chunks
        ]
        citations = [
            {"text": cit.text, "article": cit.article,
             "section": cit.section, "valid": cit.valid}
            for cit in getattr(pipeline, "last_citations", [])
        ]
        _remember_sources(request.app.state, req.session_id, sources, citations)

    return StreamingResponse(stream_answer(), media_type="text/plain")


@router.get("/sources")
async def get_last_sources(request: Request, session_id: str = "default"):
    pools = getattr(request.app.state, "last_chat_sources", {})
    citations = getattr(request.app.state, "last_chat_citations", {})
    if not isinstance(pools, dict):
        # 向后兼容旧的内存结构
        return {"status": "ok", "data": {"sources": pools, "citations": []}, "error": None}
    return {
        "status": "ok",
        "data": {
            "sources": pools.get(session_id, []),
            "citations": citations.get(session_id, []),
        },
        "error": None,
    }
