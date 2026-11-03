import logging

import numpy as np
from fastapi import APIRouter, Header
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
def search(req: SearchRequest,
           x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")):
    """向量+关键词混合检索。

    注意这里故意用 `def` 而不是 `async def`：内层是 CPU 密集的同步调用
   （torch 编码 + FAISS + cross-encoder），写成 async def 会把整个事件循环卡住。
    压测实测：async 版本并发 1→8 时吞吐恒为 3.1 rps、P99 从 596ms 涨到 4209ms。
    """
    tenant = x_tenant_id or "demo"
    if req.top_k > 50:
        req.top_k = 50

    embedder = Embedder.get_instance()
    query_vec = embedder.encode_query(req.query)
    # 建库与查询必须用同一个分词器：旧版这里写 q.lower().split()，
    # 「Article 5, Section 2」会得到 '5,' 这种永远匹配不上的 token。
    tokenized_query = BM25Retriever.tokenize(req.query)

    hs = HybridSearch(tenant=tenant)
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
