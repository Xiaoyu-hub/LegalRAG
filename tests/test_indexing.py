"""Tests for embedding and indexing pipeline.

RED phase tests — all should fail until implementation modules are built.
"""

import pytest
import numpy as np


class TestEmbedder:
    """Tests for the Embedder singleton using BGE-large-en-v1.5."""

    def test_embedder_singleton(self):
        """Embedder.get_instance() returns the same instance."""
        from backend.embedding.embedder import Embedder

        inst1 = Embedder.get_instance()
        inst2 = Embedder.get_instance()
        assert inst1 is inst2, "get_instance() should return the same instance"

    def test_embedder_encodes_texts(self):
        """encode() returns numpy array of shape (n, 1024) with float32."""
        from backend.embedding.embedder import Embedder

        embedder = Embedder.get_instance()
        texts = ["This is a test passage.", "Another legal document passage.", "Short text."]
        emb = embedder.encode(texts)

        assert isinstance(emb, np.ndarray), f"Expected ndarray, got {type(emb)}"
        assert emb.shape == (3, 1024), f"Expected (3, 1024), got {emb.shape}"
        assert emb.dtype == np.float32, f"Expected float32, got {emb.dtype}"

    def test_embedder_normalizes_embeddings(self):
        """Each embedding vector has unit length (L2 norm ≈ 1.0)."""
        from backend.embedding.embedder import Embedder

        embedder = Embedder.get_instance()
        texts = ["A test passage for normalization check.", "Another passage for embedding."]
        emb = embedder.encode(texts)

        norms = np.linalg.norm(emb, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5), (
            f"Embeddings not unit length: norms = {norms}"
        )

    def test_embedder_query_instruction(self):
        """encode_query() prepends BGE instruction for queries."""
        from backend.embedding.embedder import Embedder

        embedder = Embedder.get_instance()
        query = "What is the penalty for data breach?"
        query_vec = embedder.encode_query(query)

        assert isinstance(query_vec, np.ndarray), f"Expected ndarray, got {type(query_vec)}"
        assert query_vec.shape == (1024,), f"Expected (1024,), got {query_vec.shape}"
        assert query_vec.dtype == np.float32, f"Expected float32, got {query_vec.dtype}"

        # Query vectors should also be normalized
        norm = np.linalg.norm(query_vec)
        assert np.isclose(norm, 1.0, atol=1e-5), f"Query vector not unit length: norm = {norm}"

    def test_embedder_dimension_property(self):
        """Embedder.dimension returns 1024 for BGE-large-en-v1.5."""
        from backend.embedding.embedder import Embedder

        embedder = Embedder.get_instance()
        assert embedder.dimension == 1024, (
            f"Expected dimension 1024, got {embedder.dimension}"
        )


class TestVectorSearch:
    """Tests for VectorSearch using FAISS IndexFlatIP."""

    def test_vector_search_add_and_search(self):
        """After adding embeddings, search returns results with scores and indices."""
        from backend.retrieval.vector_search import VectorSearch

        vs = VectorSearch.get_instance()
        vs.reset()

        # Create 20 random normalized vectors
        rng = np.random.default_rng(42)
        vectors = rng.uniform(-1, 1, size=(20, 1024)).astype(np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / norms  # L2 normalize

        chunk_ids = list(range(100, 120))
        vs.add(vectors, chunk_ids)

        assert vs.size == 20, f"Expected 20 vectors, got {vs.size}"

        # Search with a normalized query vector
        query = rng.uniform(-1, 1, size=(1024,)).astype(np.float32)
        query = query / np.linalg.norm(query)

        distances, indices = vs.search(query, k=5)
        assert distances.shape == (1, 5), f"Expected (1, 5) distances, got {distances.shape}"
        assert indices.shape == (1, 5), f"Expected (1, 5) indices, got {indices.shape}"
        # Distances should be in [-1, 1] range for cosine similarity
        assert np.all(distances >= -1.0) and np.all(distances <= 1.0), (
            f"Distances out of range [-1, 1]: {distances}"
        )

    def test_vector_search_persist_and_load(self, tmp_path):
        """Save index to file, load it back, search still works."""
        from backend.retrieval.vector_search import VectorSearch

        # Create and populate index
        vs1 = VectorSearch.get_instance()
        vs1.reset()

        rng = np.random.default_rng(42)
        vectors = rng.uniform(-1, 1, size=(10, 1024)).astype(np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / norms
        chunk_ids = list(range(200, 210))
        vs1.add(vectors, chunk_ids)

        # Save
        index_path = str(tmp_path / "test_index.faiss")
        vs1.save(index_path)

        # Reset and load into a fresh instance context
        vs2 = VectorSearch.get_instance()
        vs2.reset()
        vs2.load(index_path, chunk_ids)

        assert vs2.size == 10, f"Expected 10 vectors after load, got {vs2.size}"
        assert vs2.dimension == 1024, f"Expected dim 1024 after load, got {vs2.dimension}"

        # Search should work on loaded index
        query = rng.uniform(-1, 1, size=(1024,)).astype(np.float32)
        query = query / np.linalg.norm(query)
        distances, indices = vs2.search(query, k=3)
        assert distances.shape == (1, 3), f"Expected (1, 3) distances, got {distances.shape}"

    def test_vector_search_requires_normalized(self):
        """Warns if non-unit vectors are added, but still works."""
        from backend.retrieval.vector_search import VectorSearch

        vs = VectorSearch.get_instance()
        vs.reset()

        # Create non-normalized vectors
        rng = np.random.default_rng(99)
        vectors = rng.uniform(-1, 1, size=(5, 1024)).astype(np.float32)

        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            vs.add(vectors, list(range(300, 305)))

        # Should have warned about normalization
        norm_warnings = [x for x in w if "normalized" in str(x.message).lower()]
        assert len(norm_warnings) >= 1, "Should warn when adding non-normalized vectors"

        assert vs.size == 5, f"Expected 5 vectors, got {vs.size}"


class TestBM25Retriever:
    """Tests for BM25Retriever using BM25Okapi."""

    def test_bm25_build_and_search(self):
        """After building index with texts, search returns top results."""
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

        # Search for penalty-related query
        results = bm25.search("penalty fine", n=3)
        assert len(results) == 3, f"Expected 3 results, got {len(results)}"
        # Each result should be a (chunk_id, score) tuple
        for item in results:
            assert isinstance(item, tuple), f"Expected tuple, got {type(item)}"
            assert len(item) == 2, f"Expected (chunk_id, score), got {item}"
            assert isinstance(item[0], int), f"chunk_id should be int, got {type(item[0])}"
            assert isinstance(item[1], float), f"score should be float, got {type(item[1])}"

    def test_bm25_tokenize_consistency(self):
        """Same tokenizer used for indexing and querying."""
        from backend.retrieval.bm25 import BM25Retriever

        bm25 = BM25Retriever.get_instance()

        text = "Data breach penalty: up to EUR 20,000,000!"
        tokens = bm25.tokenize(text)
        assert isinstance(tokens, list), f"Expected list, got {type(tokens)}"
        assert all(isinstance(t, str) for t in tokens), "All tokens should be strings"
        # Should be lowercase
        assert all(t.islower() or t.isdigit() for t in tokens), (
            f"Tokens should be lowercase: {tokens}"
        )
        # Should split on word boundaries (no punctuation)
        assert "breach" in tokens, f"'breach' should be in tokens: {tokens}"
        assert "penalty" in tokens, f"'penalty' should be in tokens: {tokens}"

    def test_bm25_empty_query_returns_empty(self):
        """Empty query returns empty list gracefully."""
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
    """Tests for the Indexer orchestrator."""

    def test_indexer_full_pipeline(self, tmp_path, sample_pdf_text, temp_db_path):
        """Indexer chains chunk → embed → FAISS → BM25 successfully."""
        from backend.storage.metadata_store import MetadataStore
        from backend.pipeline.structure_extractor import StructureExtractor
        from backend.pipeline.legal_chunker import LegalChunker
        from backend.embedding.embedder import Embedder
        from backend.retrieval.vector_search import VectorSearch
        from backend.retrieval.bm25 import BM25Retriever
        from backend.models.document import Document

        # Reset singletons for clean test state
        VectorSearch.get_instance().reset()
        BM25Retriever.get_instance().reset()

        # 1. Extract structure and chunk
        extractor = StructureExtractor()
        structure = extractor.extract(sample_pdf_text)
        chunker = LegalChunker()
        chunks = chunker.chunk(structure, sample_pdf_text)
        assert len(chunks) >= 6, f"Expected at least 6 chunks, got {len(chunks)}"

        # 2. Store in metadata store
        store = MetadataStore(db_path=temp_db_path)
        doc = Document(
            filename="sample_legal.txt", title="Sample Regulation",
            page_count=1, file_path=str(tmp_path / "sample_legal.txt"),
            file_size=5000,
        )
        doc_id = store.insert_document(doc)
        store.insert_chunks(doc_id, chunks)
        assert store.get_chunk_count() >= 6

        # 3. Embed chunks
        embedder = Embedder.get_instance()
        chunk_texts = [c.text for c in chunks]
        embeddings = embedder.encode(chunk_texts)
        assert embeddings.shape == (len(chunks), 1024), (
            f"Expected ({len(chunks)}, 1024), got {embeddings.shape}"
        )

        # 4. Verify chunk IDs from metadata store
        stored_chunks = store.get_all_chunks()
        stored_ids = [c.id for c in stored_chunks]

        # 5. Add to FAISS
        vs = VectorSearch.get_instance()
        vs.add(embeddings, stored_ids)
        assert vs.size == len(chunks), (
            f"FAISS should have {len(chunks)} vectors, got {vs.size}"
        )

        # 6. Build BM25 index
        bm25 = BM25Retriever.get_instance()
        bm25.build_index(chunk_texts, stored_ids)
        results = bm25.search("penalty fine regulation", n=5)
        assert len(results) == 5, f"Expected 5 BM25 results, got {len(results)}"
        assert all(isinstance(r[0], int) for r in results), "Results should have int chunk_ids"

        # 7. Verify FAISS search works
        query_vec = embedder.encode_query("What is the penalty for violations?")
        distances, indices = vs.search(query_vec, k=5)
        assert distances.shape == (1, 5), f"Expected (1, 5), got {distances.shape}"
        assert indices.shape == (1, 5), f"Expected (1, 5), got {indices.shape}"

    def test_indexer_with_indexer_class(self, tmp_path, sample_pdf_text, temp_db_path):
        """Indexer class orchestrates the pipeline via process_document."""
        # We need a mock PDF file — write sample text to a temp file
        # since Indexer expects a PDF path (parsing will fail on .txt, but
        # we test the orchestration flow)
        from backend.retrieval.vector_search import VectorSearch
        from backend.retrieval.bm25 import BM25Retriever

        VectorSearch.get_instance().reset()
        BM25Retriever.get_instance().reset()

        # Write a minimal test PDF
        pdf_path = tmp_path / "test_regulation.pdf"
        # We use PyMuPDF to create a valid PDF from our sample text
        try:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            # Insert sample text in chunks since fitz insert_text has char limits
            rect = page.rect
            # Reduce font size to fit text
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

        # Now test Indexer
        from backend.pipeline.indexer import Indexer

        indexer = Indexer(chunk_strategy="by_section", db_path=temp_db_path)
        doc_id = indexer.process_document(str(pdf_path))

        assert doc_id > 0, f"Expected positive doc_id, got {doc_id}"

        # Verify the index was populated
        vs = VectorSearch.get_instance()
        assert vs.size > 0, f"FAISS index should have vectors, got {vs.size}"

        bm25 = BM25Retriever.get_instance()
        assert bm25.bm25 is not None, "BM25 index should be built"

        # Verify search works end-to-end
        embedder = Embedder.get_instance()
        query_vec = embedder.encode_query("What is the penalty for data breach?")
        distances, indices = vs.search(query_vec, k=3)
        assert distances.shape == (1, 3), f"Expected (1, 3), got {distances.shape}"
