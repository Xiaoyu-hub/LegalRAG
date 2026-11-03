"""VectorStore 契约测试：两个实现（FAISS / pgvector）必须给出同一批 top-k id。

验收三件套（吸取本项目历史教训）：
  1. 接口存在；
  2. 有假实现/可替换实现，单测不依赖外部服务；
  3. 换实现后业务结果不变——否则抽象只是摆设，代码仍然是死码。

pgvector 用例在拿不到数据库时 skip（不把环境问题算成代码问题）。
"""
import os

import numpy as np
import pytest

from backend.retrieval.bm25 import BM25Retriever
from backend.retrieval.hybrid_search import HybridSearch
from backend.retrieval.stores import FaissStore, build_vector_store
from backend.retrieval.stores.base import VectorStore
from backend.retrieval.vector_search import VectorSearch

DIM = 8

# 固定随机向量（seed 固定）+ L2 归一化：两两相似度互不相同，
# 这样 top-k 顺序是良定义的（单位阵会有大量平局，FAISS 与 pgvector 的平局
# 打破规则不同，比出来的差异是假的）。
_rng = np.random.default_rng(20261103)
VECS = _rng.normal(size=(DIM, DIM)).astype(np.float32)
VECS /= np.linalg.norm(VECS, axis=1, keepdims=True)
IDS = [11, 22, 33, 44, 55, 66, 77, 88]


def _pg_store():
    from backend.retrieval.stores.pgvector_store import PgVectorStore, build_dsn
    dsn = os.getenv("PG_DSN") or build_dsn()
    try:
        store = PgVectorStore(dsn=dsn, dimension=DIM)
        store.reset(DIM)
        return store
    except Exception as exc:  # pragma: no cover - 环境缺失
        pytest.skip(f"pgvector 不可用: {exc}")


@pytest.fixture(autouse=True)
def _clean_faiss():
    vs = VectorSearch.get_instance(DIM)
    vs.reset(DIM)
    yield
    vs.reset(1024)
    BM25Retriever.get_instance().reset()


def test_faiss_store_satisfies_protocol():
    assert isinstance(FaissStore(DIM), VectorStore)


def test_faiss_returns_chunk_ids_not_positions():
    s = FaissStore(DIM)
    s.add(VECS, IDS)
    hits = s.search_ids(VECS[0], k=3)
    # 最相似的是 IDS[0]（同一个向量，余弦 1.0）
    assert hits[0][0] == IDS[0]
    assert set(cid for cid, _ in hits) <= set(IDS)


def test_faiss_mapping_matches():
    s = FaissStore(DIM)
    s.add(VECS[:3], IDS[:3])
    assert s.mapping_matches(IDS[:3])
    assert not s.mapping_matches(IDS[:4])


def test_build_vector_store_factory(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE", "faiss")
    assert isinstance(build_vector_store(dimension=DIM), FaissStore)
    with pytest.raises(ValueError):
        build_vector_store("nope", dimension=DIM)


def test_factory_env_pgvector(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE", "pgvector")
    try:
        store = build_vector_store(dimension=DIM)
    except Exception as exc:
        pytest.skip(f"pgvector 不可用: {exc}")
    assert store.name == "pgvector"


# ── 核心：换实现后结果不变 ────────────────────────────────────────────────

def test_same_topk_across_implementations():
    faiss_store = FaissStore(DIM)
    faiss_store.add(VECS, IDS)

    pg = _pg_store()
    pg.add(VECS, IDS)

    for q_idx in (0, 3, 7):
        a = [cid for cid, _ in faiss_store.search_ids(VECS[q_idx], k=3)]
        b = [cid for cid, _ in pg.search_ids(VECS[q_idx], k=3)]
        assert a == b, f"query {q_idx}: faiss {a} vs pgvector {b}"


def test_hybrid_search_works_with_pgvector():
    """整条混合检索换 pgvector 后，返回的 id 仍是业务主键。"""
    pg = _pg_store()
    pg.add(VECS, IDS)

    bm = BM25Retriever.get_instance()
    bm.build_index([f"Section {i} text" for i in range(len(IDS))], IDS)

    hs = HybridSearch(alpha=0.7, top_k=3, vector_store=pg)
    results = hs.search(VECS[2], ["section"], top_k=3)
    got = [cid for cid, _ in results]
    assert set(got) <= set(IDS)
    assert got[0] == IDS[2], f"最相似向量对应的 chunk 应排第一，实际 {got}"


def test_pgvector_upsert_is_idempotent():
    pg = _pg_store()
    pg.add(VECS, IDS)
    before = pg.size
    pg.add(VECS, IDS)   # 重复写入同一批 id
    assert pg.size == before, "重复写入应 upsert 而不是产生重复行"
