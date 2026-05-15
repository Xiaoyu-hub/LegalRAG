import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    document_id: int
    history: list[dict] = []


@router.post("/")
async def chat(req: ChatRequest, request: Request):
    from backend.generation.pipeline import GenerationPipeline
    from backend.retrieval.hybrid_search import HybridSearch

    if len(req.question) > 4096:
        return {
            "status": "error",
            "data": None,
            "error": "Question exceeds maximum length of 4096 characters",
        }

    store = request.app.state.metadata_store
    retriever = HybridSearch()
    pipeline = GenerationPipeline(retriever=retriever, metadata_store=store)

    async def stream_answer():
        full_text = ""
        for token in pipeline.answer_stream(req.question):
            full_text += token
            yield token

        request.app.state.last_chat_sources = [
            {
                "article": c.article,
                "section": c.section,
                "text": c.text[:500],
                "chunk_id": c.id,
            }
            for c in pipeline.last_chunks
        ]

    return StreamingResponse(stream_answer(), media_type="text/plain")


@router.get("/sources")
async def get_last_sources(request: Request):
    sources = getattr(request.app.state, "last_chat_sources", [])
    return {"status": "ok", "data": {"sources": sources}, "error": None}
