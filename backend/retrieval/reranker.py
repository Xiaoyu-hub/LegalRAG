"""Cross-encoder reranker for improving top-K result quality.

Per D-17: cross-encoder/ms-marco-MiniLM-L-6-v2 (lightweight, CPU-friendly).
Per D-18: Takes top-10 from hybrid, returns top-5 after reranking.

CRITICAL (Pitfall 4): Cross-encoder has 512-token max length.
Chunks exceeding this get truncated by the tokenizer.
"""
import os
import urllib.request
import ssl
from sentence_transformers import CrossEncoder


class Reranker:
    """Cross-encoder reranker using ms-marco-MiniLM-L-6-v2."""
    
    _instance = None
    _model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """Initialize reranker with cross-encoder model.
        
        Handles SSL certificate issues by downloading model to local cache
        if hub download fails.
        """
        if Reranker._instance is not None:
            raise RuntimeError("Use Reranker.get_instance() instead")
        
        try:
            self.model = CrossEncoder(model_name, max_length=512)
        except Exception:
            cache_dir = os.path.expanduser(
                "~/.cache/huggingface/hub/models--cross-encoder--ms-marco-MiniLM-L-6-v2"
            )
            if os.path.exists(f"{cache_dir}/snapshots/main"):
                self.model = CrossEncoder(f"{cache_dir}/snapshots/main", max_length=512)
            else:
                raise
        
        self.model_name = model_name
    
    @classmethod
    def get_instance(cls, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """Get singleton instance of Reranker."""
        if cls._instance is None:
            cls._instance = cls(model_name)
        return cls._instance
    
    def rerank(
        self,
        query: str,
        passages: list[str],
        top_k: int = 5
    ) -> list[dict]:
        """Rank passages by relevance to query using cross-encoder.
        
        Args:
            query: The user's search query
            passages: List of passage text strings to rerank
            top_k: Number of top results to return (default 5 per D-18)
            
        Returns:
            List of dicts with keys: corpus_id, score, text
            Sorted by score descending
        """
        if not passages:
            return []
        
        results = self.model.rank(query, passages, top_k=top_k)
        
        return [
            {
                "corpus_id": r["corpus_id"],
                "score": float(r["score"]),
                "text": passages[r["corpus_id"]]
            }
            for r in results
        ]
