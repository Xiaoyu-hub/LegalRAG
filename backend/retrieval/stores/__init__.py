"""向量库工厂：默认 FAISS，配了 PG_DSN 就可用 pgvector。"""
import os

from backend.retrieval.stores.base import VectorStore
from backend.retrieval.vector_search import VectorSearch


class FaissStore:
    """FAISS 适配器：把（按租户隔离的）`VectorSearch` 包成 `VectorStore` 接口。

    注意接口只暴露 chunk_id，位置映射留在 `VectorSearch` 内部。
    """

    name = "faiss"

    def __init__(self, dimension: int = 1024, tenant: str = "demo"):
        self.tenant = tenant
        self._vs = VectorSearch.get_instance(dimension, tenant)

    @property
    def inner(self) -> VectorSearch:
        return self._vs

    @property
    def size(self) -> int:
        return self._vs.size

    @property
    def chunk_ids(self) -> list[int]:
        return self._vs.chunk_ids

    def add(self, embeddings, chunk_ids):
        self._vs.add(embeddings, chunk_ids)

    def search_ids(self, query_vec, k: int = 10):
        return self._vs.search_ids(query_vec, k=k)

    def reset(self, dimension: int | None = None):
        self._vs.reset(dimension)

    def save(self, path: str):
        self._vs.save(path)

    def load(self, path: str) -> bool:
        self._vs.load(path)
        return self._vs.mapping_trusted

    def mapping_matches(self, expected_ids: list[int]) -> bool:
        return self._vs.mapping_matches(expected_ids)


def build_vector_store(kind: str | None = None, dimension: int = 1024,
                       tenant: str = "demo") -> VectorStore:
    """按名字造向量库。priority：显式参数 > 环境变量 VECTOR_STORE > faiss。"""
    kind = kind or os.getenv("VECTOR_STORE", "faiss")

    if kind == "faiss":
        return FaissStore(dimension, tenant)

    if kind == "pgvector":
        from backend.retrieval.stores.pgvector_store import PgVectorStore, build_dsn
        dsn = os.getenv("PG_DSN") or build_dsn()
        return PgVectorStore(dsn=dsn, dimension=dimension, tenant=tenant)

    raise ValueError(f"Unknown vector store {kind!r}; expected faiss / pgvector")


__all__ = ["VectorStore", "FaissStore", "build_vector_store"]
