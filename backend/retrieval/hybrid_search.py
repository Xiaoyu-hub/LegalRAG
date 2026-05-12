"""Hybrid search combining BM25 and vector search with score normalization.

Per D-15: Alpha weighting 0.7 vector / 0.3 BM25.
Per D-18: Return top-10 before reranking.

CRITICAL (Pitfall 1): BM25 and FAISS scores are on incompatible scales.
Min-max normalize BOTH per query before weighted combination.
"""
import numpy as np
from backend.retrieval.bm25 import BM25Retriever
from backend.retrieval.vector_search import VectorSearch


def normalize_scores(scores: np.ndarray) -> np.ndarray:
    """Min-max normalize scores to [0, 1].
    
    Handles edge case where all scores are equal (returns zeros).
    """
    min_s, max_s = scores.min(), scores.max()
    if max_s == min_s:
        return np.zeros_like(scores, dtype=np.float32)
    return (scores - min_s) / (max_s - min_s)


class HybridSearch:
    """Hybrid search combining BM25 and vector results with score normalization."""
    
    def __init__(self, alpha: float = 0.7, top_k: int = 10):
        """Initialize hybrid search.
        
        Args:
            alpha: Vector weight (default 0.7 per D-15)
            top_k: Number of results to return (default 10 per D-18)
        """
        self.alpha = alpha
        self.top_k = top_k
        self.vector_search = VectorSearch.get_instance()
        self.bm25 = BM25Retriever.get_instance()
    
    def search(
        self,
        query_vec: np.ndarray,
        tokenized_query: list[str],
        alpha: float | None = None,
        top_k: int | None = None
    ) -> list[tuple[int, float]]:
        """Hybrid search: vector + BM25 with min-max normalized score fusion.
        
        Args:
            query_vec: L2-normalized query embedding (1024,)
            tokenized_query: Tokenized query for BM25
            alpha: Vector weight (default: self.alpha)
            top_k: Number of results to return (default: self.top_k)
            
        Returns:
            List of (chunk_index, hybrid_score) tuples sorted by score descending
        """
        alpha = alpha if alpha is not None else self.alpha
        k = top_k if top_k is not None else self.top_k
        
        n_total = self.vector_search.size
        if n_total == 0:
            return []
        
        vec_distances, vec_indices = self.vector_search.search(query_vec, k=k * 2)
        bm25_scores = self.bm25.get_scores(tokenized_query)
        
        vec_scores = np.zeros(n_total, dtype=np.float32)
        for dist, idx in zip(vec_distances[0], vec_indices[0]):
            if idx != -1:
                vec_scores[idx] = dist
        
        vec_norm = normalize_scores(vec_scores)
        bm25_norm = normalize_scores(bm25_scores)
        
        hybrid = alpha * vec_norm + (1.0 - alpha) * bm25_norm
        
        top_indices = np.argsort(hybrid)[::-1][:k]
        return [(int(idx), float(hybrid[idx])) for idx in top_indices]
