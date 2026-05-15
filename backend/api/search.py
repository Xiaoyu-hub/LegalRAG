import logging

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from backend.embedding.embedder import Embedder
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
    tokenized_query = req.query.lower().split()

    hs = HybridSearch()
    results = hs.search(query_vec, tokenized_query, top_k=req.top_k)

    from backend.storage.metadata_store import MetadataStore

    store = MetadataStore()
    chunk_ids = [r[0] for r in results]
    chunks = store.get_chunks(chunk_ids)
    chunk_map = {c.id: c for c in chunks}

    return {
        "status": "ok",
        "data": {
            "results": [
                {
                    "chunk_id": idx,
                    "score": float(score),
                    "article": chunk_map.get(idx).article if chunk_map.get(idx) else None,
                    "section": chunk_map.get(idx).section if chunk_map.get(idx) else None,
                    "text": (chunk_map.get(idx).text or "")[:1000] if chunk_map.get(idx) else "",
                }
                for idx, score in results
                if idx in chunk_map
            ]
        },
        "error": None,
    }
