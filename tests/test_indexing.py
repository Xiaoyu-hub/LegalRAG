"""向量化与索引流水线的测试。属于先写测试的「红灯阶段」——实现没写之前这些都应当失败。"""

import pytest
import numpy as np


class TestEmbedder:
    """Embedder 单例的测试（模型 BGE-large-en-v1.5）。"""

    def test_embedder_singleton(self):
        """get_instance() 每次返回同一个实例。"""
        from backend.embedding.embedder import Embedder

        inst1 = Embedder.get_instance()
        inst2 = Embedder.get_instance()
        assert inst1 is inst2, "get_instance() should return the same instance"

    def test_embedder_encodes_texts(self):
        """encode() 返回 (n, 1024) 的 float32 数组。"""
        from backend.embedding.embedder import Embedder

        embedder = Embedder.get_instance()
        texts = ["This is a test passage.", "Another legal document passage.", "Short text."]
        emb = embedder.encode(texts)

        assert isinstance(emb, np.ndarray), f"Expected ndarray, got {type(emb)}"
        assert emb.shape == (3, 1024), f"Expected (3, 1024), got {emb.shape}"
        assert emb.dtype == np.float32, f"Expected float32, got {emb.dtype}"

    def test_embedder_normalizes_embeddings(self):
        """每个向量都是单位长度（L2 范数≈1.0）。"""
        from backend.embedding.embedder import Embedder

        embedder = Embedder.get_instance()
        texts = ["A test passage for normalization check.", "Another passage for embedding."]
        emb = embedder.encode(texts)

        norms = np.linalg.norm(emb, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5), (
            f"Embeddings not unit length: norms = {norms}"
        )

    def test_embedder_query_instruction(self):
        """encode_query() 会给查询加上 BGE 指令前缀。"""
        from backend.embedding.embedder import Embedder

        embedder = Embedder.get_instance()
        query = "What is the penalty for data breach?"
        query_vec = embedder.encode_query(query)

        assert isinstance(query_vec, np.ndarray), f"Expected ndarray, got {type(query_vec)}"
        assert query_vec.shape == (1024,), f"Expected (1024,), got {query_vec.shape}"
        assert query_vec.dtype == np.float32, f"Expected float32, got {query_vec.dtype}"

        # 查询向量同样要归一化
        norm = np.linalg.norm(query_vec)
        assert np.isclose(norm, 1.0, atol=1e-5), f"Query vector not unit length: norm = {norm}"

    def test_embedder_dimension_property(self):
        """BGE-large 的维度是 1024。"""
        from backend.embedding.embedder import Embedder

        embedder = Embedder.get_instance()
        assert embedder.dimension == 1024, (
            f"Expected dimension 1024, got {embedder.dimension}"
        )


class TestVectorSearch:
    """VectorSearch 的测试（FAISS IndexFlatIP）。"""

    def test_vector_search_add_and_search(self):
        """写入向量后，检索能返回分数与下标。"""
        from backend.retrieval.vector_search import VectorSearch

        vs = VectorSearch.get_instance()
        vs.reset()

        # 造 20 个随机但已归一化的向量
        rng = np.random.default_rng(42)
        vectors = rng.uniform(-1, 1, size=(20, 1024)).astype(np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / norms  # 做 L2 归一化

        chunk_ids = list(range(100, 120))
        vs.add(vectors, chunk_ids)

        assert vs.size == 20, f"Expected 20 vectors, got {vs.size}"

        # 用归一化后的查询向量检索
        query = rng.uniform(-1, 1, size=(1024,)).astype(np.float32)
        query = query / np.linalg.norm(query)

        distances, indices = vs.search(query, k=5)
        assert distances.shape == (1, 5), f"Expected (1, 5) distances, got {distances.shape}"
        assert indices.shape == (1, 5), f"Expected (1, 5) indices, got {indices.shape}"
        # 余弦相似度的取值范围应在 [-1, 1]
        assert np.all(distances >= -1.0) and np.all(distances <= 1.0), (
            f"Distances out of range [-1, 1]: {distances}"
        )

    def test_vector_search_persist_and_load(self, tmp_path):
        """索引存盘再读回后，检索仍然可用。"""
        from backend.retrieval.vector_search import VectorSearch

        # 建索引并写入数据
        vs1 = VectorSearch.get_instance()
        vs1.reset()

        rng = np.random.default_rng(42)
        vectors = rng.uniform(-1, 1, size=(10, 1024)).astype(np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / norms
        chunk_ids = list(range(200, 210))
        vs1.add(vectors, chunk_ids)

        # 存盘
        index_path = str(tmp_path / "test_index.faiss")
        vs1.save(index_path)

        # 重置后在一个干净实例里加载
        vs2 = VectorSearch.get_instance()
        vs2.reset()
        vs2.load(index_path, chunk_ids)

        assert vs2.size == 10, f"Expected 10 vectors after load, got {vs2.size}"
        assert vs2.dimension == 1024, f"Expected dim 1024 after load, got {vs2.dimension}"

        # 在加载回来的索引上检索应当可用
        query = rng.uniform(-1, 1, size=(1024,)).astype(np.float32)
        query = query / np.linalg.norm(query)
        distances, indices = vs2.search(query, k=3)
        assert distances.shape == (1, 3), f"Expected (1, 3) distances, got {distances.shape}"

    def test_vector_search_requires_normalized(self):
        """写入非单位向量时给告警，但功能正常。"""
        from backend.retrieval.vector_search import VectorSearch

        vs = VectorSearch.get_instance()
        vs.reset()

        # 造一批未归一化的向量
        rng = np.random.default_rng(99)
        vectors = rng.uniform(-1, 1, size=(5, 1024)).astype(np.float32)

        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            vs.add(vectors, list(range(300, 305)))

        # 应当已经给出归一化告警
        norm_warnings = [x for x in w if "normalized" in str(x.message).lower()]
        assert len(norm_warnings) >= 1, "Should warn when adding non-normalized vectors"

        assert vs.size == 5, f"Expected 5 vectors, got {vs.size}"


class TestBM25Retriever:
    """BM25Retriever 的测试（BM25Okapi）。"""

    def test_bm25_build_and_search(self):
        """用文本建好索引后，检索能返回结果。"""
        from backend.retrieval.bm25 import BM25Retriever

        bm25 = BM25Retriever.get_instance()
        bm25.reset()

        texts = [
            "The penalty for data breach is a fine of up to 20 million euros.",
            "Data controllers must implement appropriate security measures.",
            "The Regulatory Authority has the power to investigate violations.",
            "Section 3 specifies the administrative fines for violations.",
            "Data subjects have the right to access their personal data.",
        ]
        chunk_ids = [10, 11, 12, 13, 14]
        bm25.build_index(texts, chunk_ids)

        # 用处罚相关的查询做检索
        results = bm25.search("penalty fine", n=3)
        assert len(results) == 3, f"Expected 3 results, got {len(results)}"
        # 每条结果都是 (chunk_id, score) 元组
        for item in results:
            assert isinstance(item, tuple), f"Expected tuple, got {type(item)}"
            assert len(item) == 2, f"Expected (chunk_id, score), got {item}"
            assert isinstance(item[0], int), f"chunk_id should be int, got {type(item[0])}"
            assert isinstance(item[1], float), f"score should be float, got {type(item[1])}"

    def test_bm25_tokenize_consistency(self):
        """建索引与查询必须用同一个分词器。"""
        from backend.retrieval.bm25 import BM25Retriever

        bm25 = BM25Retriever.get_instance()

        text = "Data breach penalty: up to EUR 20,000,000!"
        tokens = bm25.tokenize(text)
        assert isinstance(tokens, list), f"Expected list, got {type(tokens)}"
        assert all(isinstance(t, str) for t in tokens), "All tokens should be strings"
        # 应转成小写
        assert all(t.islower() or t.isdigit() for t in tokens), (
            f"Tokens should be lowercase: {tokens}"
        )
        # 应按词边界切分，不带标点
        assert "breach" in tokens, f"'breach' should be in tokens: {tokens}"
        assert "penalty" in tokens, f"'penalty' should be in tokens: {tokens}"

    def test_bm25_empty_query_returns_empty(self):
        """空查询优雅返回空列表。"""
        from backend.retrieval.bm25 import BM25Retriever

        bm25 = BM25Retriever.get_instance()
        bm25.reset()

        texts = ["Some text about legal provisions.", "More text about data protection."]
        bm25.build_index(texts, [1, 2])

        results = bm25.search("", n=5)
        assert results == [], f"Expected empty list for empty query, got {results}"

        results2 = bm25.search("   ", n=5)
        assert results2 == [], f"Expected empty list for whitespace query, got {results2}"


class TestIndexer:
    """索引编排器的测试。"""

    def test_indexer_full_pipeline(self, tmp_path, sample_pdf_text, temp_db_path):
        """索引器把「分块 → 向量化 → FAISS → BM25」串起来了。"""
        from backend.storage.metadata_store import MetadataStore
        from backend.pipeline.structure_extractor import StructureExtractor
        from backend.pipeline.legal_chunker import LegalChunker
        from backend.embedding.embedder import Embedder
        from backend.retrieval.vector_search import VectorSearch
        from backend.retrieval.bm25 import BM25Retriever
        from backend.models.document import Document

        # 重置单例，保证测试从干净状态开始
        VectorSearch.get_instance().reset()
        BM25Retriever.get_instance().reset()

        # 第 1 步：抽结构并分块
        extractor = StructureExtractor()
        structure = extractor.extract(sample_pdf_text)
        chunker = LegalChunker()
        chunks = chunker.chunk(structure, sample_pdf_text)
        assert len(chunks) >= 6, f"Expected at least 6 chunks, got {len(chunks)}"

        # 第 2 步：写入元数据库
        store = MetadataStore(db_path=temp_db_path)
        doc = Document(
            filename="sample_legal.txt", title="Sample Regulation",
            page_count=1, file_path=str(tmp_path / "sample_legal.txt"),
            file_size=5000,
        )
        doc_id = store.insert_document(doc)
        store.insert_chunks(doc_id, chunks)
        assert store.get_chunk_count() >= 6

        # 第 3 步：把 chunk 编码成向量
        embedder = Embedder.get_instance()
        chunk_texts = [c.text for c in chunks]
        embeddings = embedder.encode(chunk_texts)
        assert embeddings.shape == (len(chunks), 1024), (
            f"Expected ({len(chunks)}, 1024), got {embeddings.shape}"
        )

        # 第 4 步：核对元数据库分配的主键
        stored_chunks = store.get_all_chunks()
        stored_ids = [c.id for c in stored_chunks]

        # 第 5 步：写入 FAISS
        vs = VectorSearch.get_instance()
        vs.add(embeddings, stored_ids)
        assert vs.size == len(chunks), (
            f"FAISS should have {len(chunks)} vectors, got {vs.size}"
        )

        # 第 6 步：建 BM25 索引
        bm25 = BM25Retriever.get_instance()
        bm25.build_index(chunk_texts, stored_ids)
        results = bm25.search("penalty fine regulation", n=5)
        assert len(results) == 5, f"Expected 5 BM25 results, got {len(results)}"
        assert all(isinstance(r[0], int) for r in results), "Results should have int chunk_ids"

        # 第 7 步：验证 FAISS 检索可用
        query_vec = embedder.encode_query("What is the penalty for violations?")
        distances, indices = vs.search(query_vec, k=5)
        assert distances.shape == (1, 5), f"Expected (1, 5), got {distances.shape}"
        assert indices.shape == (1, 5), f"Expected (1, 5), got {indices.shape}"

    def test_indexer_with_indexer_class(self, tmp_path, sample_pdf_text, temp_db_path):
        """Indexer 通过 process_document 编排整条流水线。"""
        # 需要一个假 PDF：先把样例文本写进临时文件
        # 因为 Indexer 要的是 PDF 路径（传 .txt 解析会失败，但这里
        # 我们只验证编排流程）
        from backend.retrieval.vector_search import VectorSearch
        from backend.retrieval.bm25 import BM25Retriever

        VectorSearch.get_instance().reset()
        BM25Retriever.get_instance().reset()

        # 造一个最小可用 PDF
        pdf_path = tmp_path / "test_regulation.pdf"
        # 用 PyMuPDF 把样例文本写成合法 PDF
        try:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            # fitz 的 insert_text 有字符上限，所以分片插入
            rect = page.rect
            # 调小字号让文本放得下
            page.insert_text(
                (rect.x0 + 50, rect.y0 + 50),
                sample_pdf_text,
                fontsize=8,
                fontname="helv",
            )
            doc.save(str(pdf_path))
            doc.close()
        except Exception as e:
            pytest.skip(f"Cannot create test PDF: {e}")

        # 现在测 Indexer
        from backend.pipeline.indexer import Indexer
        from backend.embedding.embedder import Embedder

        indexer = Indexer(chunk_strategy="by_section", db_path=temp_db_path)
        doc_id = indexer.process_document(str(pdf_path))

        assert doc_id > 0, f"Expected positive doc_id, got {doc_id}"

        # 确认索引里确实有数据
        vs = VectorSearch.get_instance()
        assert vs.size > 0, f"FAISS index should have vectors, got {vs.size}"

        bm25 = BM25Retriever.get_instance()
        assert bm25.bm25 is not None, "BM25 index should be built"

        # 确认端到端检索可用
        embedder = Embedder.get_instance()
        query_vec = embedder.encode_query("What is the penalty for data breach?")
        distances, indices = vs.search(query_vec, k=3)
        assert distances.shape == (1, 3), f"Expected (1, 3), got {distances.shape}"
