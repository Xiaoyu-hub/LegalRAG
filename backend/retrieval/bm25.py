"""BM25 关键词检索（用 rank_bm25 库）。D-16：关键词通路选它，不自己实现。"""
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
        """BM25 分词：转小写，按词边界切。
        RESEARCH.md 第 5 个坑写得很明确——建库与查询必须共用同一个 tokenize()，否则分词口径不一致，关键词通路会静默失效。"""
        text = text.lower()
        return re.findall(r'\w+', text)

    def build_index(self, texts: list[str], chunk_ids: list[int] | None = None):
        """用一批 chunk 文本建 BM25 索引。
        参数：
        - texts：文本列表
        - chunk_ids：对应的业务主键（默认 range(len(texts))）"""
        self.corpus = texts
        self.chunk_ids = chunk_ids if chunk_ids is not None else list(range(len(texts)))
        tokenized_corpus = [self.tokenize(t) for t in texts]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def search(self, query: str, n: int = 10) -> list[tuple[int, float]]:
        """检索 BM25，返回若干 (chunk_id, score)，按分数降序。"""
        if self.bm25 is None:
            raise RuntimeError("BM25 index not built. Call build_index() first.")
        tokenized_query = self.tokenize(query)
        if not tokenized_query:
            return []
        scores = self.bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[::-1][:n]
        return [(self.chunk_ids[i], float(scores[i])) for i in top_indices]

    def get_scores(self, tokenized_query: list[str]) -> np.ndarray:
        """取全库每个文档的 BM25 分数，供混合检索使用。"""
        if self.bm25 is None:
            raise RuntimeError("BM25 index not built.")
        return np.array(self.bm25.get_scores(tokenized_query))

    def reset(self):
        """清空索引，重建时用。"""
        self.bm25 = None
        self.chunk_ids = []
        self.corpus = []
