"""BM25 keyword retrieval using rank_bm25.

Per D-16: Use rank_bm25 library for keyword retrieval.
"""
import re
import numpy as np
from rank_bm25 import BM25Okapi


class BM25Retriever:
    # 按租户隔离：每个 tenant 一套 BM25 倒排，否则 A 租户的文档会进 B 租户的召回
    _instances: dict[str, "BM25Retriever"] = {}

    def __init__(self, tenant: str = "demo"):
        if tenant in BM25Retriever._instances:
            raise RuntimeError("Use BM25Retriever.get_instance() instead")
        self.tenant = tenant
        self.bm25 = None
        self.chunk_ids = []
        self.corpus = []

    @classmethod
    def get_instance(cls, tenant: str = "demo"):
        if tenant not in cls._instances:
            cls._instances[tenant] = cls(tenant)
        return cls._instances[tenant]

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """Tokenize text for BM25. Lowercase, split on word boundaries.
        Per RESEARCH.md Pitfall 5: Define a single tokenize() used for both
        corpus building and querying. Use same tokenizer consistently.
        """
        text = text.lower()
        return re.findall(r'\w+', text)

    def build_index(self, texts: list[str], chunk_ids: list[int] | None = None):
        """Build BM25 index from chunk texts.

        Args:
            texts: List of chunk text strings
            chunk_ids: Corresponding chunk IDs (default: range(len(texts)))
        """
        self.corpus = texts
        self.chunk_ids = chunk_ids if chunk_ids is not None else list(range(len(texts)))
        tokenized_corpus = [self.tokenize(t) for t in texts]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def search(self, query: str, n: int = 10) -> list[tuple[int, float]]:
        """Search BM25 index, return top-n (chunk_id, score) pairs."""
        if self.bm25 is None:
            raise RuntimeError("BM25 index not built. Call build_index() first.")
        tokenized_query = self.tokenize(query)
        if not tokenized_query:
            return []
        scores = self.bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[::-1][:n]
        return [(self.chunk_ids[i], float(scores[i])) for i in top_indices]

    def get_scores(self, tokenized_query: list[str]) -> np.ndarray:
        """Get BM25 scores for all documents. Used by hybrid search."""
        if self.bm25 is None:
            raise RuntimeError("BM25 index not built.")
        return np.array(self.bm25.get_scores(tokenized_query))

    def reset(self):
        """Clear the index. Used when re-indexing."""
        self.bm25 = None
        self.chunk_ids = []
        self.corpus = []
