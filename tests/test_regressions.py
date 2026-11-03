"""契约回归测试：把 2026-11-03 修过的缺陷钉死。

每条用例对应一个真实故障，注释里写清「不修会怎样」，避免以后改动悄悄回退。
"""
import numpy as np
import pytest

from backend.models.chunk import Chunk
from backend.models.document import Document
from backend.retrieval.bm25 import BM25Retriever
from backend.retrieval.hybrid_search import HybridSearch
from backend.retrieval.vector_search import VectorSearch
from backend.storage.metadata_store import MetadataStore

DIM = 4


# ── 公共件 ────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    st = MetadataStore(db_path=str(tmp_path / "t.db"))
    st.insert_document(Document(filename="a.txt"))
    return st


@pytest.fixture
def seeded(store):
    """建一个 3 chunk 的小库，并把同 id 的向量塞进 FAISS。

    VectorSearch 是全局单例，本文件用 4 维向量加速；测完必须把维度恢复成
    默认 1024，否则后面 test_retrieval 里的 1024 维用例会挂在 faiss 的 d != self.d。
    """
    doc_id = store.get_all_documents()[0].id
    store.insert_chunks(doc_id, [
        Chunk(doc_id=doc_id, chunk_index=i, text=f"Section {i + 1}. rule {i + 1}",
              article="I", section=str(i + 1))
        for i in range(3)
    ])
    chunks = store.get_chunks_by_doc_id(doc_id)
    ids = [c.id for c in chunks]
    texts = [c.text for c in chunks]

    vs = VectorSearch.get_instance(DIM)
    vs.reset(DIM)
    vs.add(np.eye(DIM, dtype=np.float32)[:3], ids)

    bm = BM25Retriever.get_instance()
    bm.build_index(texts, ids)
    yield chunks, ids, texts

    vs.reset(1024)
    bm.reset()


# ── 1. 返回的必须是 SQLite 主键，而不是 FAISS 位置 ─────────────────────────

def test_search_returns_chunk_ids_not_positions(store, seeded):
    chunks, ids, _ = seeded
    hs = HybridSearch()
    results = hs.search(np.eye(DIM, dtype=np.float32)[0],
                        BM25Retriever.tokenize("Section 1"), top_k=3)

    got = [r[0] for r in results]
    # 旧缺陷：返回 0/1/2（位置），SQLite 主键是 1/2/3 ⇒ 每条偏一条、top-1 丢失
    assert set(got) <= set(ids), f"返回的 id 必须落在库内 id 集合，实际 {got} vs {ids}"
    assert got[0] == ids[0], "最相似的 chunk 必须是第 1 条结果"


# ── 2. get_chunks 必须保持传入顺序 ─────────────────────────────────────────

def test_get_chunks_preserves_requested_order(store, seeded):
    chunks, ids, _ = seeded
    want = [ids[2], ids[0], ids[1]]
    got = [c.id for c in store.get_chunks(want)]
    # 旧缺陷：WHERE id IN (...) 无 ORDER BY，实测按 rowid 返回 [1,2,3]
    assert got == want, f"重排分数顺序不能在取回时被抹平，期望 {want}，实际 {got}"


def test_get_chunks_drops_unknown_ids(store, seeded):
    chunks, ids, _ = seeded
    got = [c.id for c in store.get_chunks([ids[0], 9999])]
    assert got == [ids[0]]


# ── 3. 位置→chunk_id 映射必须落盘 ──────────────────────────────────────────

def test_save_and_load_persist_id_mapping(tmp_path, store, seeded):
    chunks, ids, _ = seeded
    path = str(tmp_path / "idx" / "vector.faiss")
    vs = VectorSearch.get_instance()
    vs.save(path)
    assert (path + ".ids.npy").replace(".tmp", "").startswith(path) or True

    import os
    assert os.path.exists(path + ".ids.npy"), "映射文件必须与索引一起落盘"

    vs.reset()
    vs.load(path, chunk_ids=None)
    # 旧缺陷：load 不传 chunk_ids 就回退 range(ntotal)，重启后映射退化成恒等
    assert vs.chunk_ids == ids, f"重启后映射退化，期望 {ids}，实际 {vs.chunk_ids}"
    assert vs.mapping_trusted is True


def test_load_without_ids_file_is_not_trusted(tmp_path, seeded):
    import os
    chunks, ids, _ = seeded
    path = str(tmp_path / "idx2" / "vector.faiss")
    vs = VectorSearch.get_instance()
    vs.save(path)
    os.remove(path + ".ids.npy")

    vs.reset()
    vs.load(path)
    assert vs.mapping_trusted is False, "映射文件缺失时必须标记不可信，交给启动校验重建"


def test_mapping_matches_detects_drift(store, seeded):
    chunks, ids, _ = seeded
    vs = VectorSearch.get_instance()
    assert vs.mapping_matches(ids) is True
    assert vs.mapping_matches(ids + [999]) is False


# ── 4. 建库与查询分词器必须一致 ────────────────────────────────────────────

def test_retrieve_uses_shared_tokenizer(monkeypatch, store, seeded):
    """retrieve() 必须用 BM25Retriever.tokenize，而不是 str.split()。"""
    captured = {}

    def fake_search(self, query_vec, tokenized_query, alpha=None, top_k=None):
        captured["tokens"] = tokenized_query
        return []

    monkeypatch.setattr(HybridSearch, "search", fake_search)
    monkeypatch.setattr(
        "backend.retrieval.hybrid_search.Embedder.get_instance",
        staticmethod(lambda: type("E", (), {"encode_query": lambda self, q: np.zeros(DIM)})( )),
    )

    HybridSearch().retrieve("Article 5, Section 2")
    assert captured["tokens"] == BM25Retriever.tokenize("Article 5, Section 2")
    assert "5," not in captured["tokens"], "带标点的数字 token 会让关键词通路永远匹配不上"


# ── 5. 外键真的生效（CASCADE 才不是摆设）─────────────────────────────────

def test_foreign_keys_cascade_on_delete(store, seeded):
    chunks, ids, _ = seeded
    doc_id = chunks[0].doc_id
    assert store.get_chunk_count() == 3

    assert store.delete_document(doc_id) is True
    # 旧缺陷：连接上没有 PRAGMA foreign_keys=ON，删文档后 chunks 变孤儿
    assert store.get_chunk_count() == 0, "删文档必须级联删掉它的 chunks"


def test_insert_chunk_without_document_is_rejected(store):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_chunks(9999, [Chunk(doc_id=9999, chunk_index=0, text="x")])


# ── 6. 流式路径也要跑引用校验 ──────────────────────────────────────────────

def test_answer_stream_validates_citations():
    from backend.generation.pipeline import GenerationPipeline

    chunk = Chunk(id=1, doc_id=1, chunk_index=0, text="ctx", article="I", section="1")
    p = GenerationPipeline(retriever=None, metadata_store=None)
    p._retrieve = lambda query, document_id=None: [chunk]
    p.generator.generate_stream = lambda s, u: iter(
        ["The fine is ", "[Article I, Section 1]", " and also ", "[Article X, Section 99]"]
    )

    out = "".join(p.answer_stream("q"))
    assert "[Article X, Section 99]" in out, "流内不改字"

    # 旧缺陷：answer_stream 直接 yield 完就结束，process() 从未执行
    cits = p.last_citations
    assert len(cits) == 2
    assert cits[0].valid is True
    assert cits[1].valid is False


# ── 7. 重排真的接进了链路 ────────────────────────────────────────────────

def test_pipeline_applies_reranker():
    from backend.generation.pipeline import GenerationPipeline

    class FakeRetriever:
        def retrieve(self, query, top_k=None):
            return [(i, 1.0 / i) for i in range(1, 6)]

    class FakeStore:
        def get_chunks(self, ids):
            return [Chunk(id=i, doc_id=1, chunk_index=i, text=f"t{i}") for i in ids]

    class FakeReranker:
        def __init__(self):
            self.calls = []

        def rerank(self, query, passages, top_k=5):
            self.calls.append((len(passages), top_k))
            # 反着排，证明结果确实按重排顺序走
            order = list(range(len(passages)))[::-1][:top_k]
            return [{"corpus_id": i, "score": float(len(passages) - i),
                     "text": passages[i]} for i in order]

    rr = FakeReranker()
    p = GenerationPipeline(retriever=FakeRetriever(), metadata_store=FakeStore(),
                           reranker=rr, recall_k=5, rerank_top_k=3)
    p.generator.generate = lambda s, u: "answer"

    p.answer("q")
    assert rr.calls == [(5, 3)], "召回 5 条交给重排、取 3 条；旧版 Reranker 根本没被调用"
    assert [c.id for c in p.last_chunks] == [5, 4, 3]
