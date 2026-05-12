import sqlite3
from typing import Optional

from backend.models.document import Document
from backend.models.chunk import Chunk


class MetadataStore:
    """SQLite-backed metadata storage for documents, chunks, and definitions.

    Per D-14: Store document metadata in SQLite with foreign key relationships.
    Schema includes: documents, chunks, definitions tables with FK links.
    """

    def __init__(self, db_path: str = "data/metadata.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                title TEXT DEFAULT '',
                page_count INTEGER DEFAULT 0,
                file_path TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL,
                chunk_index INTEGER DEFAULT 0,
                text TEXT NOT NULL,
                article TEXT,
                section TEXT,
                subsection TEXT,
                title TEXT DEFAULT '',
                parent_article TEXT,
                strategy TEXT DEFAULT 'by_section',
                FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL,
                term TEXT NOT NULL,
                definition TEXT NOT NULL,
                context TEXT,
                FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
            CREATE INDEX IF NOT EXISTS idx_definitions_doc_id ON definitions(doc_id);
        """)
        conn.commit()
        conn.close()

    def insert_document(self, doc: Document) -> int:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO documents (filename, title, page_count, file_path, file_size) "
            "VALUES (?, ?, ?, ?, ?)",
            (doc.filename, doc.title, doc.page_count, doc.file_path, doc.file_size),
        )
        conn.commit()
        doc_id = c.lastrowid
        conn.close()
        return doc_id

    def insert_chunks(self, doc_id: int, chunks: list[Chunk]):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        for chunk in chunks:
            c.execute(
                "INSERT INTO chunks "
                "(doc_id, chunk_index, text, article, section, subsection, title, parent_article, strategy) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (doc_id, chunk.chunk_index, chunk.text, chunk.article,
                 chunk.section, chunk.subsection, chunk.title,
                 chunk.parent_article, chunk.strategy),
            )
        conn.commit()
        conn.close()

    def insert_definitions(self, doc_id: int, definitions: list[dict]):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        for d in definitions:
            c.execute(
                "INSERT INTO definitions (doc_id, term, definition, context) VALUES (?, ?, ?, ?)",
                (doc_id, d["term"], d["definition"], d.get("context", "")),
            )
        conn.commit()
        conn.close()

    def get_document(self, doc_id: int) -> Optional[Document]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return Document(
                id=row[0], filename=row[1], title=row[2],
                page_count=row[3], file_path=row[4], file_size=row[5],
            )
        return None

    def get_chunks(self, chunk_ids: list[int]) -> list[Chunk]:
        if not chunk_ids:
            return []
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        placeholders = ",".join("?" * len(chunk_ids))
        c.execute(
            f"SELECT * FROM chunks WHERE id IN ({placeholders})", chunk_ids
        )
        rows = c.fetchall()
        conn.close()
        return [
            Chunk(
                id=r[0], doc_id=r[1], chunk_index=r[2], text=r[3],
                article=r[4], section=r[5], subsection=r[6],
                title=r[7], parent_article=r[8], strategy=r[9],
            )
            for r in rows
        ]

    def get_all_chunks(self) -> list[Chunk]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM chunks ORDER BY doc_id, chunk_index")
        rows = c.fetchall()
        conn.close()
        return [
            Chunk(
                id=r[0], doc_id=r[1], chunk_index=r[2], text=r[3],
                article=r[4], section=r[5], subsection=r[6],
                title=r[7], parent_article=r[8], strategy=r[9],
            )
            for r in rows
        ]

    def get_chunk_texts(self) -> list[str]:
        return [c.text for c in self.get_all_chunks()]

    def get_chunk_count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM chunks")
        count = c.fetchone()[0]
        conn.close()
        return count
