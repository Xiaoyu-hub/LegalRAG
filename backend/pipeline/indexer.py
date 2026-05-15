"""Indexer orchestrator — chains parse → extract → chunk → embed → index → BM25.

Per architecture.md section 2.3 (Core Data Flow):
PDF → Parser → StructureExtractor → LegalChunker → Embedding → FAISS + BM25
"""
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
                 index_path: str = "data/index/vector.faiss"):
        self.chunk_strategy = chunk_strategy
        self.db_path = db_path
        self.index_path = index_path
        self.parser = PDFParser()
        self.structure_extractor = StructureExtractor()
        self.chunker = LegalChunker(strategy=chunk_strategy)
        self.embedder = Embedder.get_instance()
        self.vector_search = VectorSearch.get_instance()
        self.bm25 = BM25Retriever.get_instance()
        self.metadata_store = MetadataStore(db_path=db_path)

    def process_document(self, file_path: str, doc_id: int | None = None) -> int:
        """Process a single PDF document through the full pipeline.

        Args:
            file_path: Path to the PDF file.
            doc_id: Existing document ID (created by API layer). If None,
                     a new document record is created.

        Returns: doc_id from metadata store.
        """
        # 1. Parse PDF
        raw_text = self.parser.extract_text(file_path)

        # 2. Extract structure
        structure = self.structure_extractor.extract(raw_text)
        definitions = self.structure_extractor.extract_definitions(raw_text)

        # 3. Chunk
        chunks = self.chunker.chunk(structure, raw_text)

        # 4. Create or reuse document record
        if doc_id is None:
            filename = os.path.basename(file_path)
            doc = Document(
                filename=filename,
                file_path=file_path,
                file_size=os.path.getsize(file_path),
            )
            doc_id = self.metadata_store.insert_document(doc)

        # 5. Store chunks in SQLite
        self.metadata_store.insert_chunks(doc_id, chunks)
        if definitions:
            self.metadata_store.insert_definitions(doc_id, definitions)

        # 6. Retrieve stored chunks to get their assigned IDs
        stored_chunks = self.metadata_store.get_chunks_by_doc_id(doc_id)
        chunk_ids = [c.id for c in stored_chunks]
        chunk_texts = [c.text for c in stored_chunks]

        # 7. Embed chunks
        embeddings = self.embedder.encode(chunk_texts)

        # 8. Add to FAISS
        self.vector_search.add(embeddings, chunk_ids)

        # 9. Rebuild BM25 — rebuild from all chunks
        all_texts = self.metadata_store.get_chunk_texts()
        all_ids = [c.id for c in self.metadata_store.get_all_chunks()]
        self.bm25.build_index(all_texts, all_ids)

        # 10. Save FAISS index
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        self.vector_search.save(self.index_path)

        return doc_id
