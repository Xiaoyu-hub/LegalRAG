"""向量库抽象：接口只交换 chunk_id，不交换内部位置。

设计要点（别再踩的坑）：原 `VectorSearch.search()` 返回 FAISS 位置，业务侧拿去
查 SQLite 主键，导致「每条命中偏一条、top-1 丢失」。所以这层接口**直接返回
chunk_id**，把位置关在实现内部——换后端也不会重现该缺陷。
"""
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class VectorStore(Protocol):
    """最小向量库接口。"""

    @property
    def size(self) -> int:
        ...

    @property
    def chunk_ids(self) -> list[int]:
        ...

    def add(self, embeddings: np.ndarray, chunk_ids: list[int]) -> None:
        ...

    def search_ids(self, query_vec: np.ndarray, k: int) -> list[tuple[int, float]]:
        """返回 [(chunk_id, score)]，score 越大越相似（内积/余弦口径统一）。"""
        ...

    def reset(self, dimension: int | None = None) -> None:
        ...

    def save(self, path: str) -> None:
        """持久化（不支持持久化的实现可 no-op）。"""
        ...

    def load(self, path: str) -> bool:
        """载入；返回 True 表示内部映射可信。"""
        ...
