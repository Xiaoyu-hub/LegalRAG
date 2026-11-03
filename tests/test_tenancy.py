"""多租户隔离（tenant isolation）契约测试。

对应 OpenHex JD 原词「多租户数据隔离」。隔离必须发生在三层，任何一层漏了都算串数据：
  1. 元数据（SQLite）：文档与 chunk 带 tenant 列，查询按租户过滤
  2. 向量索引（FAISS）：每个租户一套索引与目录
  3. 关键词索引（BM25）：每个租户一套倒排
"""
import numpy as np
import pytest

from backend.models.chunk import Chunk
from backend.models.document import Document
from backend.pipeline.indexer import Indexer
from backend.retrieval.bm25 import BM25Retriever
from backend.retrieval.hybrid_search import HybridSearch
from backend.retrieval.vector_search import VectorSearch
from backend.storage.metadata_store import MetadataStore

DIM = 4


@pytest.fixture
def store(tmp_path):
    return MetadataStore(db_path=str(tmp_path / "t.db"))


@pytest.fixture(autouse=True)
def _clean(store=None):
    for t in ("tenant-a", "tenant-b", "demo"):
        VectorSearch.drop_tenant(t)
        BM25Retriever._instances.pop(t, None)
    yield
    for t in ("tenant-a", "tenant-b", "demo"):
        VectorSearch.drop_tenant(t)
        BM25Retriever._instances.pop(t, None)


# ── 1. 元数据隔离 ────────────────────────────────────────────────────────

def test_same_filename_in_two_tenants_are_separate_documents(store):
    a = store.insert_document(Document(filename="law.pdf", tenant="tenant-a"))
    b = store.insert_document(Document(filename="law.pdf", tenant="tenant-b"))
    assert a != b

    assert [d.id for d in store.get_all_documents("tenant-a")] == [a]
    assert [d.id for d in store.get_all_documents("tenant-b")] == [b]
    # tenant=None 是管理视角，能看到全部
    assert {d.id for d in store.get_all_documents()} == {a, b}


def test_chunks_inherit_document_tenant(store):
    a = store.insert_document(Document(filename="a.pdf", tenant="tenant-a"))
    store.insert_chunks(a, [Chunk(doc_id=a, chunk_index=0, text="alpha")])

    assert store.get_chunk_count("tenant-a") == 1
    assert store.get_chunk_count("tenant-b") == 0
    assert store.get_chunk_count() == 1


def test_list_tenants(store):
    store.insert_document(Document(filename="a.pdf", tenant="tenant-a"))
    store.insert_document(Document(filename="b.pdf", tenant="tenant-b"))
    assert store.list_tenants() == ["tenant-a", "tenant-b"]


def test_other_tenant_cannot_read_document_by_id(store):
    a = store.insert_document(Document(filename="a.pdf", tenant="tenant-a"))
    assert store.get_document(a, tenant="tenant-a") is not None
    assert store.get_document(a, tenant="tenant-b") is None


# ── 2. 向量索引隔离 ──────────────────────────────────────────────────────

def test_vector_indexes_are_separate_per_tenant():
    va = VectorSearch.get_instance(DIM, "tenant-a")
    vb = VectorSearch.get_instance(DIM, "tenant-b")
    va.reset(DIM)
    vb.reset(DIM)

    va.add(np.eye(DIM, dtype=np.float32)[:2], [101, 102])
    vb.add(np.eye(DIM, dtype=np.float32)[2:4], [201, 202])

    assert va.size == 2 and vb.size == 2
    assert va.chunk_ids == [101, 102]
    assert vb.chunk_ids == [201, 202]

    hits = [cid for cid, _ in va.search_ids(np.eye(DIM, dtype=np.float32)[0], k=4)]
    assert set(hits) <= {101, 102}, "A 租户的检索不能出现 B 租户的 chunk"


def test_bm25_indexes_are_separate_per_tenant():
    ba = BM25Retriever.get_instance("tenant-a")
    bb = BM25Retriever.get_instance("tenant-b")
    ba.build_index(["apple banana"], [101])
    bb.build_index(["cherry date"], [201])

    hits_a = ba.search("cherry", n=5)
    assert all(cid == 101 for cid, _ in hits_a), "B 租户的关键词不能进 A 的倒排"


def test_indexer_uses_per_tenant_index_path(tmp_path):
    ia = Indexer(tenant="tenant-a", db_path=str(tmp_path / "a.db"),
                 index_path=str(tmp_path / "idx" / "a" / "vector.faiss"))
    ib = Indexer(tenant="tenant-b", db_path=str(tmp_path / "b.db"),
                 index_path=str(tmp_path / "idx" / "b" / "vector.faiss"))
    assert ia.index_path != ib.index_path
    assert "tenant-a" in ia.vector_search.tenant


# ── 3. 混合检索端到端不串租户 ────────────────────────────────────────────

def test_hybrid_search_only_returns_own_tenant(store):
    a = store.insert_document(Document(filename="a.pdf", tenant="tenant-a"))
    b = store.insert_document(Document(filename="b.pdf", tenant="tenant-b"))
    store.insert_chunks(a, [Chunk(doc_id=a, chunk_index=0, text="Section 1. alpha rule")])
    store.insert_chunks(b, [Chunk(doc_id=b, chunk_index=0, text="Section 1. alpha rule")])

    ids_a = store.get_all_chunk_ids("tenant-a")
    ids_b = store.get_all_chunk_ids("tenant-b")
    assert set(ids_a).isdisjoint(ids_b)

    va = VectorSearch.get_instance(DIM, "tenant-a")
    va.reset(DIM)
    va.add(np.eye(DIM, dtype=np.float32)[:1], ids_a)

    ba = BM25Retriever.get_instance("tenant-a")
    ba.build_index(store.get_chunk_texts("tenant-a"), ids_a)

    hs = HybridSearch(tenant="tenant-a")
    results = hs.search(np.eye(DIM, dtype=np.float32)[0], ["alpha"], top_k=5)
    got = {cid for cid, _ in results}
    assert got <= set(ids_a), f"返回了别的租户的 chunk：{got - set(ids_a)}"
