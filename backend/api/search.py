import logging

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from backend.embedding.embedder import Embedder
from backend.retrieval.bm25 import BM25Retriever
from backend.retrieval.hybrid_search import HybridSearch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10


@router.post("/")
async def search(req: SearchRequest):
    if req.top_k > 50:
        req.top_k = 50

    embedder = Embedder.get_instance()
    query_vec = embedder.encode_query(req.query)
    # 建库与查询必须用同一个分词器：旧版这里写 q.lower().split()，
    # 「Article 5, Section 2」会得到 '5,' 这种永远匹配不上的 token。
    tokenized_query = BM25Retriever.tokenize(req.query)

    hs = HybridSearch()
    results = hs.search(query_vec, tokenized_query, top_k=max(req.top_k * 2, 10))

    from backend.storage.metadata_store import MetadataStore

    store = MetadataStore()
    chunk_ids = [r[0] for r in results]
    chunks = store.get_chunks(chunk_ids)  # 已按传入顺序重排

    # cross-encoder 重排：尽量把 top_k 条真正相关的提上来
    try:
        from backend.retrieval.reranker import Reranker
        reranker = Reranker.get_instance()
        ranked = reranker.rerank(req.query, [c.text for c in chunks], top_k=req.top_k)
        ordered = [chunks[r["corpus_id"]] for r in ranked]
        score_map = {chunks[r["corpus_id"]].id: float(r["score"]) for r in ranked}
    except Exception as exc:
        logger.warning("Reranker unavailable, returning hybrid order: %s", exc)
        ordered = chunks[: req.top_k]
        score_map = {c.id: 0.0 for c in ordered}

    return {
        "status": "ok",
        "data": {
            "results": [
                {
                    "chunk_id": c.id,
                    "score": score_map.get(c.id, 0.0),
                    "article": c.article,
                    "section": c.section,
                    "text": (c.text or "")[:1000],
                }
                for c in ordered
            ]
        },
        "error": None,
    }
