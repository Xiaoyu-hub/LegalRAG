"""混合检索：BM25 与向量两路召回，再做分数归一化后融合。
- D-15：权重 0.7 向量 / 0.3 BM25
- D-18：重排前先取 10 条候选（重排池要大过最终条数）
关键（第 1 个坑）：BM25 分数无上界、向量余弦在 [-1,1]，两者量纲不可比。
每条 query 都要**两路各自**做 min-max 归一化，然后才能加权相加。"""
import logging

import numpy as np
from backend.embedding.embedder import Embedder
from backend.retrieval.bm25 import BM25Retriever
from backend.retrieval.vector_search import VectorSearch

logger = logging.getLogger(__name__)


def normalize_scores(scores: np.ndarray) -> np.ndarray:
    """把分数 min-max 归一化到 [0,1]。全部相等时返回全 0（避免除零）。"""
    min_s, max_s = scores.min(), scores.max()
    if max_s == min_s:
        return np.zeros_like(scores, dtype=np.float32)
    return (scores - min_s) / (max_s - min_s)


class HybridSearch:
    """混合检索：BM25 与向量结果归一化后融合。"""
    
    def __init__(self, alpha: float = 0.7, top_k: int = 10, vector_store=None,
                 tenant: str = "demo"):
        """Initialize hybrid search.

        Args:
            alpha: Vector weight (default 0.7 per D-15)
            top_k: Number of results to return (default 10 per D-18)
            vector_store: 任意满足 VectorStore 接口的后端（faiss / pgvector / 测试桩）
            tenant: 租户，决定用哪套向量索引与 BM25 倒排
        """
        self.alpha = alpha
        self.top_k = top_k
        self.tenant = tenant
        if vector_store is None:
            from backend.retrieval.stores import build_vector_store
            vector_store = build_vector_store(tenant=tenant)
        self.vector_store = vector_store
        self.vector_search = getattr(vector_store, "inner", vector_store)
        self.bm25 = BM25Retriever.get_instance(tenant)
    
    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[tuple[int, float]]:
        """Embed query string and run hybrid search.

        top_k 默认用 self.top_k（10，D-18 的重排池），不要写死 5：
        否则重排只能在 5 条里换顺序，无法把 6~10 名的候选提上来。
        """
        embedder = Embedder.get_instance()
        query_vec = embedder.encode_query(query)
        tokenized_query = BM25Retriever.tokenize(query)
        return self.search(query_vec, tokenized_query, top_k=top_k)

    def search(
        self,
        query_vec: np.ndarray,
        tokenized_query: list[str],
        alpha: float | None = None,
        top_k: int | None = None
    ) -> list[tuple[int, float]]:
        """混合检索入口，外面包一层 span 记录耗时与规模。"""
        from backend.observability import span as _span

        use_alpha = alpha if alpha is not None else self.alpha
        with _span("retrieval.hybrid", **{"tenant": self.tenant, "alpha": use_alpha,
                                          "top_k": top_k or self.top_k}) as sp:
            results = self._search_impl(query_vec, tokenized_query, alpha, top_k)
            sp.set_attribute("retrieval.n_total", len(self.vector_store.chunk_ids))
            sp.set_attribute("retrieval.returned", len(results))
            return results

    def _search_impl(
        self,
        query_vec: np.ndarray,
        tokenized_query: list[str],
        alpha: float | None = None,
        top_k: int | None = None
    ) -> list[tuple[int, float]]:
        """混合检索：向量 + BM25，分数先 min-max 归一化再融合。
        参数：
        - query_vec：L2 归一化后的查询向量（1024 维）
        - tokenized_query：BM25 用的分词结果
        - alpha：向量权重（默认 self.alpha）
        - top_k：返回条数（默认 self.top_k）
        返回：(chunk_id, 融合分数) 列表，按分数降序"""
        alpha = alpha if alpha is not None else self.alpha
        k = top_k if top_k is not None else self.top_k

        store = self.vector_store
        n_total = store.size
        if n_total == 0:
            return []

        # 向量库接口直接给 (chunk_id, score)，不再暴露内部位置
        vec_hits = store.search_ids(query_vec, k=k * 2)
        bm25_scores = self.bm25.get_scores(tokenized_query)

        all_ids = list(store.chunk_ids)
        pos_of = {cid: i for i, cid in enumerate(all_ids)}

        vec_scores = np.zeros(len(all_ids), dtype=np.float32)
        for cid, score in vec_hits:
            p = pos_of.get(cid)
            if p is not None:
                vec_scores[p] = score

        vec_norm = normalize_scores(vec_scores)
        bm25_norm = normalize_scores(bm25_scores)

        hybrid = alpha * vec_norm + (1.0 - alpha) * bm25_norm

        top_indices = np.argsort(hybrid)[::-1][:k]
        return [(int(all_ids[i]), float(hybrid[i])) for i in top_indices]
