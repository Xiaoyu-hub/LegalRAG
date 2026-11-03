"""Integration and unit tests for the document ingestion pipeline.

Tests cover PDF parsing, structure extraction, legal-aware chunking,
definition extraction, and SQLite metadata storage.
All tests in this file should fail until the implementation modules are built.
"""

import pytest


# ── PDF Parser Tests ──────────────────────────────────────────────────────────

class TestPDFParser:
    def test_pdf_parser_returns_text(self):
        """PDFParser should extract text from a PDF file."""
        from backend.pipeline.parser import PDFParser
        parser = PDFParser()
        # Without a real PDF, we cannot test the parser fully in Task 1.
        # This test validates the class can be instantiated.
        assert parser is not None
        assert hasattr(parser, "extract_text")


# ── Structure Extractor Tests ─────────────────────────────────────────────────

class TestStructureExtractor:
    def test_structure_extractor_detects_articles(self, sample_pdf_text):
        """Should detect Article I, Article II, Article III from the fixture."""
        from backend.pipeline.structure_extractor import StructureExtractor
        extractor = StructureExtractor()
        structure = extractor.extract(sample_pdf_text)
        articles = [e for e in structure if e["type"] == "article"]
        assert len(articles) >= 3, f"Expected at least 3 articles, got {len(articles)}"
        article_numbers = [a["number"] for a in articles]
        assert "I" in article_numbers, f"Article I not found: {article_numbers}"
        assert "II" in article_numbers, f"Article II not found: {article_numbers}"
        assert "III" in article_numbers, f"Article III not found: {article_numbers}"

    def test_structure_extractor_detects_sections(self, sample_pdf_text):
        """Should detect sections like Section 1, Section 2, etc."""
        from backend.pipeline.structure_extractor import StructureExtractor
        extractor = StructureExtractor()
        structure = extractor.extract(sample_pdf_text)
        sections = [e for e in structure if e["type"] == "section"]
        assert len(sections) >= 6, f"Expected at least 6 sections, got {len(sections)}"

    def test_structure_extractor_detects_subsections(self, sample_pdf_text):
        """Should detect subsections like (a), (b), (c), (d)."""
        from backend.pipeline.structure_extractor import StructureExtractor
        extractor = StructureExtractor()
        structure = extractor.extract(sample_pdf_text)
        subsections = [e for e in structure if e["type"] == "subsection"]
        assert len(subsections) >= 6, f"Expected at least 6 subsections, got {len(subsections)}"
        # Verify subsection labels
        labels = [s.get("label") for s in subsections]
        assert "a" in labels, f"Subsection (a) not found: {labels}"

    def test_structure_extractor_tracks_parent_article(self, sample_pdf_text):
        """Section and subsection elements should have parent_article populated."""
        from backend.pipeline.structure_extractor import StructureExtractor
        extractor = StructureExtractor()
        structure = extractor.extract(sample_pdf_text)
        sections = [e for e in structure if e["type"] == "section"]
        for section in sections:
            assert section.get("parent_article") is not None, \
                f"Section {section.get('number')} missing parent_article"
        subsections = [e for e in structure if e["type"] == "subsection"]
        for sub in subsections[:5]:
            assert sub.get("parent_article") is not None, \
                f"Subsection {sub.get('label')} missing parent_article"


# ── Legal Chunker Tests ───────────────────────────────────────────────────────

class TestLegalChunker:
    def test_legal_chunker_by_section_default(self, sample_pdf_text):
        """By-section chunking should create one chunk per section."""
        from backend.pipeline.structure_extractor import StructureExtractor
        from backend.pipeline.legal_chunker import LegalChunker
        extractor = StructureExtractor()
        chunker = LegalChunker()  # default: by_section
        structure = extractor.extract(sample_pdf_text)
        chunks = chunker.chunk(structure, sample_pdf_text)
        assert len(chunks) >= 6, f"Expected at least 6 chunks, got {len(chunks)}"
        # Each chunk should have text
        for c in chunks:
            assert c.text, "Chunk should have non-empty text"

    def test_legal_chunker_by_article(self, sample_pdf_text):
        """By-article chunking should create one chunk per article."""
        from backend.pipeline.structure_extractor import StructureExtractor
        from backend.pipeline.legal_chunker import LegalChunker
        extractor = StructureExtractor()
        chunker = LegalChunker(strategy="by_article")
        structure = extractor.extract(sample_pdf_text)
        chunks = chunker.chunk(structure, sample_pdf_text)
        assert len(chunks) >= 3, f"Expected at least 3 article chunks, got {len(chunks)}"

    def test_chunk_metadata_preserved(self, sample_pdf_text):
        """Each chunk should have article, section, title, parent_article metadata."""
        from backend.pipeline.structure_extractor import StructureExtractor
        from backend.pipeline.legal_chunker import LegalChunker
        extractor = StructureExtractor()
        chunker = LegalChunker()
        structure = extractor.extract(sample_pdf_text)
        chunks = chunker.chunk(structure, sample_pdf_text)
        for chunk in chunks:
            assert chunk.article is not None, "Chunk missing article"
            assert chunk.section is not None, "Chunk missing section"
            assert chunk.title, "Chunk missing title"
            assert chunk.parent_article is not None, "Chunk missing parent_article"
            assert chunk.strategy == "by_section", \
                f"Expected strategy by_section, got {chunk.strategy}"


# ── Definition Extraction Tests ───────────────────────────────────────────────

class TestDefinitionExtraction:
    def test_definition_extraction(self, sample_pdf_text):
        """Should extract legal term definitions like 'Person' means..."""
        from backend.pipeline.structure_extractor import StructureExtractor
        extractor = StructureExtractor()
        definitions = extractor.extract_definitions(sample_pdf_text)
        terms = [d["term"] for d in definitions]
        assert len(definitions) >= 2, f"Expected at least 2 definitions, got {len(definitions)}"
        assert "Person" in terms, f"Definition for 'Person' not found: {terms}"
        assert "Entity" in terms, f"Definition for 'Entity' not found: {terms}"

    def test_definition_has_context(self, sample_pdf_text):
        """Each definition should include context around the term."""
        from backend.pipeline.structure_extractor import StructureExtractor
        extractor = StructureExtractor()
        definitions = extractor.extract_definitions(sample_pdf_text)
        for d in definitions:
            assert "definition" in d and d["definition"], \
                f"Definition for '{d.get('term')}' missing definition text"
            assert "context" in d and d["context"], \
                f"Definition for '{d.get('term')}' missing context"


# ── Metadata Store Tests ──────────────────────────────────────────────────────

class TestMetadataStore:
    def test_metadata_store_insert_document(self, temp_db_path):
        """Should insert a document into SQLite and return its ID."""
        from backend.storage.metadata_store import MetadataStore
        from backend.models.document import Document
        store = MetadataStore(db_path=temp_db_path)
        doc = Document(
            filename="test.pdf", title="Test Document",
            page_count=10, file_path="/tmp/test.pdf", file_size=1024
        )
        doc_id = store.insert_document(doc)
        assert doc_id > 0, f"Expected positive doc_id, got {doc_id}"

    def test_metadata_store_retrieve_document(self, temp_db_path):
        """Should retrieve a document by its ID."""
        from backend.storage.metadata_store import MetadataStore
        from backend.models.document import Document
        store = MetadataStore(db_path=temp_db_path)
        doc = Document(filename="test.pdf", title="Test Document",
                       page_count=10, file_path="/tmp/test.pdf", file_size=1024)
        doc_id = store.insert_document(doc)
        retrieved = store.get_document(doc_id)
        assert retrieved is not None
        assert retrieved.filename == "test.pdf"
        assert retrieved.title == "Test Document"

    def test_metadata_store_chunk_count(self, temp_db_path):
        """After inserting chunks, chunk count should reflect them."""
        from backend.storage.metadata_store import MetadataStore
        from backend.models.document import Document
        from backend.models.chunk import Chunk
        store = MetadataStore(db_path=temp_db_path)
        doc = Document(filename="test.pdf")
        doc_id = store.insert_document(doc)
        chunks = [
            Chunk(doc_id=doc_id, chunk_index=i, text=f"chunk {i}",
                  article="I", section=str(i), title=f"Section {i}",
                  parent_article="I")
            for i in range(3)
        ]
        store.insert_chunks(doc_id, chunks)
        assert store.get_chunk_count() == 3


# ── Full Integration Pipeline Test ─────────────────────────────────────────────

class TestIntegrationPipeline:
    def test_full_ingestion_pipeline(self, sample_pdf_text, temp_db_path):
        """End-to-end test: parse → extract → chunk → store."""
        from backend.pipeline.structure_extractor import StructureExtractor
        from backend.pipeline.legal_chunker import LegalChunker
        from backend.storage.metadata_store import MetadataStore
        from backend.models.document import Document

        # Extract structure
        extractor = StructureExtractor()
        structure = extractor.extract(sample_pdf_text)

        # Verify structure
        articles = [e for e in structure if e["type"] == "article"]
        sections = [e for e in structure if e["type"] == "section"]
        assert len(articles) >= 3
        assert len(sections) >= 6

        # Extract definitions
        definitions = extractor.extract_definitions(sample_pdf_text)
        assert len(definitions) >= 2

        # Chunk
        chunker = LegalChunker()
        chunks = chunker.chunk(structure, sample_pdf_text)
        assert len(chunks) >= 6

        # Store
        store = MetadataStore(db_path=temp_db_path)
        doc = Document(filename="sample_legal.txt", title="Sample Regulation",
                       page_count=1, file_path="data/test/sample_legal.txt",
                       file_size=5000)
        doc_id = store.insert_document(doc)
        store.insert_chunks(doc_id, chunks)
        store.insert_definitions(doc_id, definitions)

        # Verify storage
        assert store.get_chunk_count() >= 6
        retrieved = store.get_document(doc_id)
        assert retrieved is not None
        assert retrieved.title == "Sample Regulation"

        # Verify chunk text content
        chunk_texts = store.get_chunk_texts()
        assert any("General Provisions" in t for t in chunk_texts), \
            "Chunks should contain 'General Provisions'"


# ── 分块覆盖率回归（2026-11-03 修 Article 边界不 flush 的缺陷）──────────────────

class TestChunkCoverage:
    """保证「每一个结构元素都被至少一个 chunk 覆盖」。

    旧缺陷：`_chunk_by_section` 遇到新的 article 时直接把 current_section_data
    置 None，不 flush 上一个待写的 section，导致每个 Article 的最后一个小节
    （含其全部子条款）被静默丢弃。实测 sample_legal.txt 丢 17.4% 正文字符。
    """

    @staticmethod
    def _structure():
        from pathlib import Path
        from backend.pipeline.structure_extractor import StructureExtractor
        text = (Path(__file__).parent.parent / "data" / "test" / "sample_legal.txt").read_text(
            encoding="utf-8"
        )
        return StructureExtractor().extract(text), text

    def test_every_element_is_covered_by_section_chunks(self):
        import re
        from backend.pipeline.legal_chunker import LegalChunker

        structure, text = self._structure()
        chunks = LegalChunker(strategy="by_section").chunk(structure, text)

        missing = [e for e in structure
                   if e["text"].strip()
                   and not any(e["text"].strip() in c.text for c in chunks)]
        assert missing == [], f"以下结构元素没有进入任何 chunk：{[e['text'][:40] for e in missing]}"

    def test_section_count_matches_structure(self):
        from backend.pipeline.legal_chunker import LegalChunker

        structure, text = self._structure()
        n_sections = sum(1 for e in structure if e["type"] == "section")
        chunks = LegalChunker(strategy="by_section").chunk(structure, text)
        assert len(chunks) == n_sections, (
            f"by_section 应每个 Section 一个 chunk：结构 {n_sections} 个 / chunk {len(chunks)} 个"
        )

    def test_last_section_of_each_article_present(self):
        from backend.pipeline.legal_chunker import LegalChunker

        structure, text = self._structure()
        chunks = LegalChunker(strategy="by_section").chunk(structure, text)
        joined = "\n".join(c.text for c in chunks)
        # 这两节历史上就是被丢掉的 Article I / II 末节
        assert "Section 3. Interpretation" in joined
        assert "Section 3. Data Processing Agreements" in joined
        # 父级 Article 标题要带回 chunk 作上下文
        assert "Article I. General Provisions" in joined
