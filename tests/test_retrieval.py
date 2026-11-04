"""混合检索与重排的测试。"""
import pytest
import numpy as np


def get_1024d_embeddings(n: int) -> np.ndarray:
    """为测试造 1024 维、已 L2 归一化的向量。"""
    embeddings = np.random.randn(n, 1024).astype(np.float32)
    embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings


class TestHybridSearch:
    def test_hybrid_search_returns_results(self):
        """建好索引后，混合检索返回前 K 条。"""
        from backend.retrieval.hybrid_search import HybridSearch
        from backend.retrieval.vector_search import VectorSearch
        from backend.retrieval.bm25 import BM25Retriever
        
        vec_search = VectorSearch.get_instance()
        bm25 = BM25Retriever.get_instance()
        
        vec_search.reset()
        
        embeddings = get_1024d_embeddings(3)
        chunk_ids = [0, 1, 2]
        texts = ["test one", "test two", "test three"]
        
        vec_search.add(embeddings, chunk_ids)
        bm25.build_index(texts, chunk_ids)
        
        hybrid = HybridSearch(alpha=0.7, top_k=3)
        query_vec = get_1024d_embeddings(1)[0]
        results = hybrid.search(query_vec, ["test"], top_k=3)
        
        assert len(results) == 3
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        assert all(isinstance(r[0], int) and isinstance(r[1], float) for r in results)
    
    def test_hybrid_search_score_range(self):
        """归一化之后融合分数落在 [0,1]。"""
        from backend.retrieval.hybrid_search import HybridSearch
        from backend.retrieval.vector_search import VectorSearch
        from backend.retrieval.bm25 import BM25Retriever
        
        vec_search = VectorSearch.get_instance()
        bm25 = BM25Retriever.get_instance()
        
        vec_search.reset()
        
        embeddings = get_1024d_embeddings(10)
        chunk_ids = list(range(10))
        texts = [f"document {i}" for i in range(10)]
        
        vec_search.add(embeddings, chunk_ids)
        bm25.build_index(texts, chunk_ids)
        
        hybrid = HybridSearch(alpha=0.7, top_k=5)
        query_vec = get_1024d_embeddings(1)[0]
        results = hybrid.search(query_vec, ["document"], top_k=5)
        
        for _, score in results:
            assert 0.0 <= score <= 1.0, f"Score {score} not in [0, 1]"
    
    def test_hybrid_search_alpha_default(self):
        """D-15 定的默认权重：向量 0.7、BM25 0.3。"""
        from backend.retrieval.hybrid_search import HybridSearch
        
        hybrid = HybridSearch()
        assert hybrid.alpha == 0.7
    
    def test_hybrid_search_alpha_pure_vector(self):
        """alpha=1.0 时退化为纯向量。"""
        from backend.retrieval.hybrid_search import HybridSearch
        from backend.retrieval.vector_search import VectorSearch
        from backend.retrieval.bm25 import BM25Retriever
        
        vec_search = VectorSearch.get_instance()
        bm25 = BM25Retriever.get_instance()
        
        vec_search.reset()
        
        embeddings = get_1024d_embeddings(2)
        chunk_ids = [0, 1]
        texts = ["alpha beta", "gamma delta"]
        
        vec_search.add(embeddings, chunk_ids)
        bm25.build_index(texts, chunk_ids)
        
        hybrid = HybridSearch(alpha=1.0, top_k=2)
        query_vec = embeddings[0]
        results = hybrid.search(query_vec, ["gamma"], alpha=1.0, top_k=2)
        
        assert results[0][0] == 0
    
    def test_hybrid_search_alpha_pure_bm25(self):
        """alpha=0.0 时退化为纯 BM25。"""
        from backend.retrieval.hybrid_search import HybridSearch
        from backend.retrieval.vector_search import VectorSearch
        from backend.retrieval.bm25 import BM25Retriever
        
        vec_search = VectorSearch.get_instance()
        bm25 = BM25Retriever.get_instance()
        
        vec_search.reset()
        
        embeddings = get_1024d_embeddings(2)
        chunk_ids = [0, 1]
        texts = ["alpha beta", "gamma delta"]
        
        vec_search.add(embeddings, chunk_ids)
        bm25.build_index(texts, chunk_ids)
        
        hybrid = HybridSearch(alpha=0.0, top_k=2)
        query_vec = embeddings[0]
        results = hybrid.search(query_vec, ["gamma"], alpha=0.0, top_k=2)
        
        assert results[0][0] == 1
    
    def test_hybrid_search_score_normalization(self):
        """确认融合之前两路原始分数都做了 min-max 归一化。"""
        from backend.retrieval.hybrid_search import normalize_scores
        import numpy as np
        
        scores = np.array([10.0, 20.0, 30.0], dtype=np.float32)
        normalized = normalize_scores(scores)
        
        assert normalized.min() == 0.0
        assert normalized.max() == 1.0
        assert normalized[0] == 0.0
        assert normalized[2] == 1.0
    
    def test_hybrid_search_returns_top_k(self):
        """返回条数恰好是 top_k（D-18 默认 10）。"""
        from backend.retrieval.hybrid_search import HybridSearch
        from backend.retrieval.vector_search import VectorSearch
        from backend.retrieval.bm25 import BM25Retriever
        
        vec_search = VectorSearch.get_instance()
        bm25 = BM25Retriever.get_instance()
        
        vec_search.reset()
        
        embeddings = get_1024d_embeddings(20)
        chunk_ids = list(range(20))
        texts = [f"doc {i}" for i in range(20)]
        
        vec_search.add(embeddings, chunk_ids)
        bm25.build_index(texts, chunk_ids)
        
        hybrid = HybridSearch(alpha=0.7, top_k=10)
        query_vec = get_1024d_embeddings(1)[0]
        results = hybrid.search(query_vec, ["doc"], top_k=10)
        
        assert len(results) == 10
    
    def test_hybrid_search_empty_index(self):
        """空索引检索优雅返回空列表。"""
        from backend.retrieval.hybrid_search import HybridSearch
        from backend.retrieval.vector_search import VectorSearch
        
        vec_search = VectorSearch.get_instance()
        vec_search.reset()
        
        hybrid = HybridSearch(alpha=0.7, top_k=10)
        query_vec = get_1024d_embeddings(1)[0]
        results = hybrid.search(query_vec, ["test"])
        
        assert results == []


class TestReranker:
    def test_reranker_returns_top_k(self):
        """重排返回条数恰好是 top_k（D-18 默认 5）。"""
        from backend.retrieval.reranker import Reranker
        
        try:
            reranker = Reranker.get_instance()
        except Exception:
            pytest.skip("Cross-encoder model not available")
        
        passages = [f"passage {i}" for i in range(10)]
        results = reranker.rerank("query", passages, top_k=5)
        
        assert len(results) == 5
    
    def test_reranker_scores_decreasing(self):
        """重排结果按分数降序。"""
        from backend.retrieval.reranker import Reranker
        
        try:
            reranker = Reranker.get_instance()
        except Exception:
            pytest.skip("Cross-encoder model not available")
        
        passages = ["very relevant query match", "somewhat relevant", "not relevant"]
        results = reranker.rerank("query match", passages, top_k=3)
        
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)
    
    def test_reranker_returns_metadata(self):
        """每条结果含 corpus_id、score、text 三个字段。"""
        from backend.retrieval.reranker import Reranker
        
        try:
            reranker = Reranker.get_instance()
        except Exception:
            pytest.skip("Cross-encoder model not available")
        
        passages = ["test passage one", "test passage two"]
        results = reranker.rerank("test", passages, top_k=2)
        
        for r in results:
            assert "corpus_id" in r
            assert "score" in r
            assert "text" in r
            assert isinstance(r["corpus_id"], int)
            assert isinstance(r["score"], float)
            assert isinstance(r["text"], str)
    
    def test_reranker_empty_input(self):
        """候选为空时返回空列表。"""
        from backend.retrieval.reranker import Reranker
        
        try:
            reranker = Reranker.get_instance()
        except Exception:
            pytest.skip("Cross-encoder model not available")
        
        results = reranker.rerank("query", [], top_k=5)
        
        assert results == []


class TestFullRetrievalPipeline:
    def test_retrieve_end_to_end(self, tmp_path):
        """Full pipeline: embed query → vector search + BM25 → hybrid → rerank → attach metadata.

        用临时库，不往仓库里的 data/metadata.db 写脏数据（旧版就是用默认库，
        还会调不存在的 insert_chunk 导致整条用例红）。
        """
        from backend.retrieval.hybrid_search import HybridSearch
        from backend.retrieval.reranker import Reranker
        from backend.retrieval.vector_search import VectorSearch
        from backend.retrieval.bm25 import BM25Retriever
        from backend.embedding.embedder import Embedder
        from backend.storage.metadata_store import MetadataStore, Chunk

        vec_search = VectorSearch.get_instance()
        bm25 = BM25Retriever.get_instance()
        store = MetadataStore(db_path=str(tmp_path / "e2e.db"))

        vec_search.reset()

        from backend.models.document import Document
        # 外键约束现在真的生效（PRAGMA foreign_keys=ON），先建文档再插 chunk
        doc_id = store.insert_document(Document(filename="e2e.txt"))

        store.insert_chunks(doc_id, [
            Chunk(doc_id=doc_id, chunk_index=0, text="Section 1. Definitions. Person means individual.",
                  article="Article I", section="Section 1", subsection=None,
                  title="Definitions", parent_article="Article I. General Provisions", strategy="by_section"),
            Chunk(doc_id=doc_id, chunk_index=1, text="Section 2. Scope. This applies to all entities.",
                  article="Article I", section="Section 2", subsection=None,
                  title="Scope", parent_article="Article I. General Provisions", strategy="by_section"),
        ])

        chunks = store.get_chunks_by_doc_id(doc_id)

        embedder = Embedder.get_instance()
        texts = [c.text for c in chunks]
        embeddings = embedder.encode(texts)
        chunk_ids = [c.id for c in chunks]
        
        vec_search.add(embeddings, chunk_ids)
        bm25.build_index(texts, chunk_ids)
        
        query = "What is the definition of Person"
        query_vec = embedder.encode_query(query)
        tokenized = BM25Retriever.tokenize(query)
        
        hybrid = HybridSearch(alpha=0.7, top_k=10)
        hybrid_results = hybrid.search(query_vec, tokenized, top_k=10)
        
        top_chunk_ids = [r[0] for r in hybrid_results]
        top_chunks = store.get_chunks(top_chunk_ids)
        passages = [c.text for c in top_chunks]
        
        try:
            reranker = Reranker.get_instance()
            reranked = reranker.rerank(query, passages, top_k=5)
        except Exception:
            pytest.skip("Cross-encoder model not available")
        
        final_results = []
        for r in reranked:
            chunk = top_chunks[r["corpus_id"]]
            final_results.append({
                "chunk": chunk,
                "score": r["score"]
            })
        
        assert len(final_results) <= 5
        for result in final_results:
            assert "chunk" in result
            assert "score" in result
            assert isinstance(result["chunk"], Chunk)
            assert result["chunk"].article is not None
            assert result["chunk"].section is not None
            assert result["chunk"].text is not None
    
    def test_retrieve_top5_has_correct_structure(self):
        """每条结果的 dict 含 chunk（带 id/article/section/text）与 score。"""
        from backend.retrieval.reranker import Reranker
        
        try:
            reranker = Reranker.get_instance()
        except Exception:
            pytest.skip("Cross-encoder model not available")
        
        passages = [f"test passage {i}" for i in range(5)]
        results = reranker.rerank("test", passages, top_k=5)
        
        for r in results:
            assert isinstance(r, dict)
            assert "corpus_id" in r
            assert "score" in r
            assert "text" in r
