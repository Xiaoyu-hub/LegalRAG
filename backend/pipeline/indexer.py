"""索引编排器：把「解析 → 抽结构 → 分块 → 向量化 → 入索引 → 建 BM25」串成一条流水线。
对应 architecture.md 2.3 节的核心数据流：PDF → Parser → StructureExtractor → LegalChunker → Embedding → FAISS + BM25"""
import os

from backend.pipeline.parser import PDFParser
from backend.pipeline.structure_extractor import StructureExtractor
from backend.pipeline.legal_chunker import LegalChunker
from backend.embedding.embedder import Embedder
from backend.retrieval.bm25 import BM25Retriever
from backend.retrieval.vector_search import VectorSearch
from backend.storage.metadata_store import MetadataStore
from backend.models.document import Document


class Indexer:
    def __init__(self, chunk_strategy: str = "by_section",
                 db_path: str = "data/metadata.db",
                 index_path: str | None = None,
                 tenant: str = "demo"):
        self.chunk_strategy = chunk_strategy
        self.db_path = db_path
        self.tenant = tenant
        # 每个租户一个索引目录：文件层面的隔离，租户之间不可能误加载对方的索引
        self.index_path = index_path or f"data/index/{tenant}/vector.faiss"
        self.parser = PDFParser()
        self.structure_extractor = StructureExtractor()
        self.chunker = LegalChunker(strategy=chunk_strategy)
        self.embedder = Embedder.get_instance()
        self.vector_search = VectorSearch.get_instance(tenant=tenant)
        self.bm25 = BM25Retriever.get_instance(tenant=tenant)
        self.metadata_store = MetadataStore(db_path=db_path)
        # 重排器延迟到首次对话时再加载模型，避免启动即吃 90MB + 几秒
        self._reranker = None

    @property
    def reranker(self):
        if self._reranker is None:
            try:
                from backend.retrieval.reranker import Reranker
                self._reranker = Reranker.get_instance()
            except Exception as exc:
                # 模型不可用时降级为不重排，但只降级一次，不每轮重试
                import logging
                logging.getLogger(__name__).warning(
                    "Reranker unavailable, falling back to hybrid order: %s", exc
                )
                self._reranker = False
        return None if self._reranker is False else self._reranker

    def process_document(self, file_path: str, doc_id: int | None = None) -> int:
        """把单个 PDF 走完整条流水线。
        参数：
        - file_path：PDF 路径
        - doc_id：已存在的文档 id（由接口层先建好）；为 None 时这里新建一条文档记录
        返回：元数据库里的 doc_id"""
        # 第 1 步：解析 PDF
        raw_text = self.parser.extract_text(file_path)

        # 第 2 步：抽取条文结构
        structure = self.structure_extractor.extract(raw_text)
        definitions = self.structure_extractor.extract_definitions(raw_text)

        # 第 3 步：分块
        chunks = self.chunker.chunk(structure, raw_text)

        # 第 4 步：新建或复用文档记录
        if doc_id is None:
            filename = os.path.basename(file_path)
            doc = Document(
                filename=filename,
                file_path=file_path,
                file_size=os.path.getsize(file_path),
                tenant=self.tenant,
            )
            doc_id = self.metadata_store.insert_document(doc)

        # 第 5 步：chunk 落 SQLite
        # 先清掉同一个 doc 的旧 chunk：重传同名文件时复用 doc_id，不先删就会
        # 在同一个文档下追加两套 chunk（旧 chunk 还留在 FAISS 里，检索出幽灵结果）。
        self._delete_chunks_of(doc_id)
        self.metadata_store.insert_chunks(doc_id, chunks, tenant=self.tenant)
        if definitions:
            self.metadata_store.insert_definitions(doc_id, definitions)

        # 第 6 步：取回落库后的 chunk，拿到数据库分配的主键
        stored_chunks = self.metadata_store.get_chunks_by_doc_id(doc_id)
        chunk_ids = [c.id for c in stored_chunks]
        chunk_texts = [c.text for c in stored_chunks]

        # 第 7 步：编码成向量
        embeddings = self.embedder.encode(chunk_texts)

        # 第 8 步：写入 FAISS
        self.vector_search.add(embeddings, chunk_ids)

        # 9. Rebuild BM25 — 只取本租户的 chunk
        all_texts = self.metadata_store.get_chunk_texts(self.tenant)
        all_ids = [c.id for c in self.metadata_store.get_all_chunks(self.tenant)]
        self.bm25.build_index(all_texts, all_ids)

        # 10. Save FAISS index（连同 position→chunk_id 映射一起落盘）
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        self.vector_search.save(self.index_path)

        return doc_id

    def _delete_chunks_of(self, doc_id: int):
        """删掉某个文档名下已有的 chunk（用于重传同名文件时重置）。"""
        conn = self.metadata_store._connect()
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        conn.commit()
        conn.close()

    def rebuild_all(self):
        """从 SQLite 重建全部索引（FAISS + BM25）。

        文档被删、重传、或者启动时发现索引与数据库不一致，都走这里。
        重建期间旧索引仍在服务，建好后一起切换，避免检索窗口为空。
        """
        chunks = self.metadata_store.get_all_chunks(self.tenant)
        if not chunks:
            self.vector_search.reset()
            self.bm25.reset()
            return 0

        texts = [c.text for c in chunks]
        ids = [c.id for c in chunks]

        embeddings = self.embedder.encode(texts)
        self.vector_search.reset()
        self.vector_search.add(embeddings, ids)
        self.bm25.build_index(texts, ids)

        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        self.vector_search.save(self.index_path)
        return len(chunks)
