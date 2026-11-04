"""入库流水线的集成与单元测试，覆盖 PDF 解析、结构抽取、法条感知分块、术语定义抽取与 SQLite 元数据存储。实现没写完之前，本文件里的用例都应当失败。"""

import pytest


# ── PDF 解析测试 ──

class TestPDFParser:
    def test_pdf_parser_returns_text(self):
        """PDFParser 应能从 PDF 抽出文本。"""
        from backend.pipeline.parser import PDFParser
        parser = PDFParser()
        # 当时手上没有真 PDF，解析器只能做有限验证。
        # 这条只验证类能被实例化。
        assert parser is not None
        assert hasattr(parser, "extract_text")


# ── 结构抽取测试 ──

class TestStructureExtractor:
    def test_structure_extractor_detects_articles(self, sample_pdf_text):
        """应能从样例里识别出 Article I、II、III。"""
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
        """应能识别 Section 1、Section 2 这类小节。"""
        from backend.pipeline.structure_extractor import StructureExtractor
        extractor = StructureExtractor()
        structure = extractor.extract(sample_pdf_text)
        sections = [e for e in structure if e["type"] == "section"]
        assert len(sections) >= 6, f"Expected at least 6 sections, got {len(sections)}"

    def test_structure_extractor_detects_subsections(self, sample_pdf_text):
        """应能识别 (a)、(b)、(c) 这类子项。"""
        from backend.pipeline.structure_extractor import StructureExtractor
        extractor = StructureExtractor()
        structure = extractor.extract(sample_pdf_text)
        subsections = [e for e in structure if e["type"] == "subsection"]
        assert len(subsections) >= 6, f"Expected at least 6 subsections, got {len(subsections)}"
        # 核对子项标签
        labels = [s.get("label") for s in subsections]
        assert "a" in labels, f"Subsection (a) not found: {labels}"

    def test_structure_extractor_tracks_parent_article(self, sample_pdf_text):
        """小节与子项元素都应带上所属条号 parent_article。"""
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


# ── 法条分块测试 ──

class TestLegalChunker:
    def test_legal_chunker_by_section_default(self, sample_pdf_text):
        """按小节分块时，每个 Section 生成一个 chunk。"""
        from backend.pipeline.structure_extractor import StructureExtractor
        from backend.pipeline.legal_chunker import LegalChunker
        extractor = StructureExtractor()
        chunker = LegalChunker()  # 默认策略：by_section
        structure = extractor.extract(sample_pdf_text)
        chunks = chunker.chunk(structure, sample_pdf_text)
        assert len(chunks) >= 6, f"Expected at least 6 chunks, got {len(chunks)}"
        # 每个 chunk 都要有正文
        for c in chunks:
            assert c.text, "Chunk should have non-empty text"

    def test_legal_chunker_by_article(self, sample_pdf_text):
        """按条分块时，每个 Article 生成一个 chunk。"""
        from backend.pipeline.structure_extractor import StructureExtractor
        from backend.pipeline.legal_chunker import LegalChunker
        extractor = StructureExtractor()
        chunker = LegalChunker(strategy="by_article")
        structure = extractor.extract(sample_pdf_text)
        chunks = chunker.chunk(structure, sample_pdf_text)
        assert len(chunks) >= 3, f"Expected at least 3 article chunks, got {len(chunks)}"

    def test_chunk_metadata_preserved(self, sample_pdf_text):
        """每个 chunk 都要带上 article、section、title、parent_article 元数据。"""
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


# ── 定义抽取测试 ──

class TestDefinitionExtraction:
    def test_definition_extraction(self, sample_pdf_text):
        """应能抽出「'Person' means …」这类定义句。"""
        from backend.pipeline.structure_extractor import StructureExtractor
        extractor = StructureExtractor()
        definitions = extractor.extract_definitions(sample_pdf_text)
        terms = [d["term"] for d in definitions]
        assert len(definitions) >= 2, f"Expected at least 2 definitions, got {len(definitions)}"
        assert "Person" in terms, f"Definition for 'Person' not found: {terms}"
        assert "Entity" in terms, f"Definition for 'Entity' not found: {terms}"

    def test_definition_has_context(self, sample_pdf_text):
        """每条定义都要带上术语前后的上下文。"""
        from backend.pipeline.structure_extractor import StructureExtractor
        extractor = StructureExtractor()
        definitions = extractor.extract_definitions(sample_pdf_text)
        for d in definitions:
            assert "definition" in d and d["definition"], \
                f"Definition for '{d.get('term')}' missing definition text"
            assert "context" in d and d["context"], \
                f"Definition for '{d.get('term')}' missing context"


# ── 元数据存储测试 ──

class TestMetadataStore:
    def test_metadata_store_insert_document(self, temp_db_path):
        """插入文档后应返回它自增出来的 id。"""
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
        """应能按 id 取回文档。"""
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
        """插入 chunk 后，计数应与实际条数一致。"""
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


# ── 全链路集成测试 ──

class TestIntegrationPipeline:
    def test_full_ingestion_pipeline(self, sample_pdf_text, temp_db_path):
        """端到端：解析 → 抽结构 → 分块 → 落库。"""
        from backend.pipeline.structure_extractor import StructureExtractor
        from backend.pipeline.legal_chunker import LegalChunker
        from backend.storage.metadata_store import MetadataStore
        from backend.models.document import Document

        # 抽结构
        extractor = StructureExtractor()
        structure = extractor.extract(sample_pdf_text)

        # 核对结构
        articles = [e for e in structure if e["type"] == "article"]
        sections = [e for e in structure if e["type"] == "section"]
        assert len(articles) >= 3
        assert len(sections) >= 6

        # 抽定义
        definitions = extractor.extract_definitions(sample_pdf_text)
        assert len(definitions) >= 2

        # 分块
        chunker = LegalChunker()
        chunks = chunker.chunk(structure, sample_pdf_text)
        assert len(chunks) >= 6

        # 落库
        store = MetadataStore(db_path=temp_db_path)
        doc = Document(filename="sample_legal.txt", title="Sample Regulation",
                       page_count=1, file_path="data/test/sample_legal.txt",
                       file_size=5000)
        doc_id = store.insert_document(doc)
        store.insert_chunks(doc_id, chunks)
        store.insert_definitions(doc_id, definitions)

        # 核对落库结果
        assert store.get_chunk_count() >= 6
        retrieved = store.get_document(doc_id)
        assert retrieved is not None
        assert retrieved.title == "Sample Regulation"

        # 核对 chunk 正文内容
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
