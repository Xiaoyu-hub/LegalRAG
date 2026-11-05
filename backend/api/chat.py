import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.deps import resolve_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    # 不传则对整库检索；传了就只在这份文档的 chunk 里召回
    document_id: int | None = None
    history: list[dict] = []
    # 会话级槽位：旧版把 sources 放在全局单槽，两个会话同时提问会互相覆盖
    session_id: str = "default"
    # 传了就落库（前端侧栏的「历史对话」靠它）；不传则是一次性问答
    conversation_id: int | None = None


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


def _collect_sources(pipeline) -> tuple[list[dict], list[dict]]:
    """把「召回了哪些片段」与「引用校验结果」整理成可直接给前端的结构。

    流式输出不回头改字，但引用校验必须跑：每个 chunk 上挂一个
    `citation_valid`，前端就能标出「这条引用没在检索片段里找到」。
    """
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
            "title": c.title or "",
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
    return sources, citations


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

    # 会话校验先做：流式响应一旦开始就没法再返 404
    conv_store = getattr(request.app.state, "conversation_store", None)
    if req.conversation_id is not None:
        if conv_store is None:
            raise HTTPException(status_code=400, detail="conversation store unavailable")
        if conv_store.get(req.conversation_id, tenant=tenant) is None:
            raise HTTPException(status_code=404,
                                detail=f"Conversation {req.conversation_id} not found")

    store = request.app.state.metadata_store
    retriever = HybridSearch(tenant=tenant)

    # 有网关就走网关（配额 / 计量 / 主备降级都在那一层），没有才退回裸 Generator。
    # 旧版这里永远走裸 Generator ⇒ 问答消耗不进计量表，用量页面永远空白。
    gateway = getattr(request.app.state, "gateway", None)
    pipeline = GenerationPipeline(
        retriever=retriever,
        metadata_store=store,
        reranker=getattr(request.app.state, "reranker", None),
        gateway=gateway,
        tenant=tenant,
    )

    async def stream_answer():
        started = time.time()
        buffer: list[str] = []
        # 先把提问落库：流断了前端也还看得到自己问过什么
        if conv_store is not None and req.conversation_id is not None:
            conv_store.append_message(req.conversation_id, "user", req.question)

        try:
            for token in pipeline.answer_stream(req.question, document_id=req.document_id):
                buffer.append(token)
                yield token
        except Exception as exc:  # noqa: BLE001 —— 流已开始，只能记下来再往外抛
            logger.error("Streaming answer failed: %s", exc, exc_info=True)
            if conv_store is not None and req.conversation_id is not None:
                conv_store.append_message(
                    req.conversation_id, "assistant",
                    "".join(buffer) + f"\n\n[生成失败：{exc}]",
                    latency_ms=round((time.time() - started) * 1000, 1),
                )
            raise

        sources, citations = _collect_sources(pipeline)
        _remember_sources(request.app.state, req.session_id, sources, citations)

        if conv_store is not None and req.conversation_id is not None:
            conv_store.append_message(
                req.conversation_id,
                "assistant",
                "".join(buffer),
                sources=sources,
                citations=citations,
                latency_ms=round((time.time() - started) * 1000, 1),
                token_count=len("".join(buffer).split()),
            )

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
