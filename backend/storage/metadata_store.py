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

    def _connect(self):
        """开连接时显式打开外键约束。

        SQLite 的 foreign_keys 是**连接级**开关且默认 OFF：建表时写了
        ON DELETE CASCADE 也不会生效，删文档后会留一堆孤儿 chunks。
        busy_timeout 给写锁一点重试时间，避免并发写直接报 database is locked。
        """
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_db(self):
        conn = self._connect()
        c = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant TEXT NOT NULL DEFAULT 'demo',
                filename TEXT NOT NULL,
                title TEXT DEFAULT '',
                page_count INTEGER DEFAULT 0,
                file_path TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant TEXT NOT NULL DEFAULT 'demo',
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
        self._migrate(conn)
        conn.close()

    def _migrate(self, conn):
        """老库升级：给已有表补 tenant 列（默认 'demo'）。

        CREATE TABLE IF NOT EXISTS 不会给旧表加列，所以升级路径必须显式 ALTER。
        注意：tenant 索引用建在 ALTER 之后，否则旧库会报 no such column: tenant。
        """
        for table in ("documents", "chunks"):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            if "tenant" not in cols:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN tenant TEXT NOT NULL DEFAULT 'demo'"
                )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON chunks(tenant)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant)")
        conn.commit()

    def insert_document(self, doc: Document) -> int:
        conn = self._connect()
        c = conn.cursor()
        c.execute(
            "INSERT INTO documents (tenant, filename, title, page_count, file_path, file_size) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (doc.tenant, doc.filename, doc.title, doc.page_count,
             doc.file_path, doc.file_size),
        )
        conn.commit()
        doc_id = c.lastrowid
        conn.close()
        return doc_id

    def insert_chunks(self, doc_id: int, chunks: list[Chunk], tenant: str | None = None):
        """写入 chunk。tenant 不传时继承所属文档的租户，避免调用方漏传导致串租户。"""
        if tenant is None:
            tenant = self.document_tenant(doc_id) or "demo"
        conn = self._connect()
        c = conn.cursor()
        for chunk in chunks:
            c.execute(
                "INSERT INTO chunks "
                "(tenant, doc_id, chunk_index, text, article, section, subsection,"
                " title, parent_article, strategy) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (tenant, doc_id, chunk.chunk_index, chunk.text, chunk.article,
                 chunk.section, chunk.subsection, chunk.title,
                 chunk.parent_article, chunk.strategy),
            )
        conn.commit()
        conn.close()

    def insert_definitions(self, doc_id: int, definitions: list[dict]):
        conn = self._connect()
        c = conn.cursor()
        for d in definitions:
            c.execute(
                "INSERT INTO definitions (doc_id, term, definition, context) VALUES (?, ?, ?, ?)",
                (doc_id, d["term"], d["definition"], d.get("context", "")),
            )
        conn.commit()
        conn.close()

    def document_tenant(self, doc_id: int) -> Optional[str]:
        conn = self._connect()
        row = conn.execute("SELECT tenant FROM documents WHERE id = ?", (doc_id,)).fetchone()
        conn.close()
        return row[0] if row else None

    def get_document(self, doc_id: int, tenant: str | None = None) -> Optional[Document]:
        conn = self._connect()
        c = conn.cursor()
        if tenant is None:
            c.execute(f"SELECT {_DOC_COLS} FROM documents WHERE id = ?", (doc_id,))
        else:
            c.execute(f"SELECT {_DOC_COLS} FROM documents WHERE id = ? AND tenant = ?",
                      (doc_id, tenant))
        row = c.fetchone()
        conn.close()
        return _row_to_document(row) if row else None

    def get_all_documents(self, tenant: str | None = None) -> list[Document]:
        """Retrieve documents ordered by created_at DESC.

        Per D-11: Encapsulate document listing in MetadataStore
        instead of exposing raw SQLite to API layer.
        tenant=None 表示不隔离（管理/调试用）。
        """
        conn = self._connect()
        c = conn.cursor()
        if tenant is None:
            c.execute(
                f"SELECT {_DOC_COLS}, created_at FROM documents ORDER BY created_at DESC"
            )
        else:
            c.execute(
                f"SELECT {_DOC_COLS}, created_at FROM documents WHERE tenant = ?"
                " ORDER BY created_at DESC",
                (tenant,),
            )
        rows = c.fetchall()
        conn.close()
        return [_row_to_document(r, with_created=True) for r in rows]

    def get_chunks(self, chunk_ids: list[int]) -> list[Chunk]:
        """按传入 id 顺序取回 Chunk。

        `WHERE id IN (...)` 本身不保证顺序（实测按 rowid 返回），而调用方拿到的是
        重排后的 top-1..top-5；不重排回去，cross-encoder 的打分顺序就在这一步被抹平。
        """
        if not chunk_ids:
            return []
        conn = self._connect()
        c = conn.cursor()
        placeholders = ",".join("?" * len(chunk_ids))
        c.execute(
            f"SELECT {_CHUNK_COLS} FROM chunks WHERE id IN ({placeholders})", chunk_ids
        )
        rows = c.fetchall()
        conn.close()
        by_id = {r[0]: _row_to_chunk(r) for r in rows}
        return [by_id[i] for i in chunk_ids if i in by_id]

    def delete_document(self, doc_id: int) -> bool:
        """删文档，连带删它的 chunks / definitions（依赖外键 CASCADE）。

        返回是否真的删到了行。CASCADE 生效的前提是 _connect() 里那句
        PRAGMA foreign_keys = ON；否则 chunks 会变成孤儿。
        """
        conn = self._connect()
        c = conn.cursor()
        c.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        deleted = c.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def get_document_by_filename(self, filename: str,
                                 tenant: str | None = None) -> Optional[Document]:
        conn = self._connect()
        c = conn.cursor()
        if tenant is None:
            c.execute(f"SELECT {_DOC_COLS} FROM documents WHERE filename = ?"
                      " ORDER BY id LIMIT 1", (filename,))
        else:
            c.execute(f"SELECT {_DOC_COLS} FROM documents WHERE filename = ?"
                      " AND tenant = ? ORDER BY id LIMIT 1", (filename, tenant))
        row = c.fetchone()
        conn.close()
        return _row_to_document(row) if row else None

    def get_all_chunk_ids(self, tenant: str | None = None) -> list[int]:
        conn = self._connect()
        c = conn.cursor()
        if tenant is None:
            c.execute("SELECT id FROM chunks ORDER BY id")
        else:
            c.execute("SELECT id FROM chunks WHERE tenant = ? ORDER BY id", (tenant,))
        ids = [r[0] for r in c.fetchall()]
        conn.close()
        return ids

    def get_all_chunks(self, tenant: str | None = None) -> list[Chunk]:
        conn = self._connect()
        c = conn.cursor()
        if tenant is None:
            c.execute(f"SELECT {_CHUNK_COLS} FROM chunks ORDER BY doc_id, chunk_index")
        else:
            c.execute(f"SELECT {_CHUNK_COLS} FROM chunks WHERE tenant = ?"
                      " ORDER BY doc_id, chunk_index", (tenant,))
        rows = c.fetchall()
        conn.close()
        return [_row_to_chunk(r) for r in rows]

    def get_chunk_texts(self, tenant: str | None = None) -> list[str]:
        return [c.text for c in self.get_all_chunks(tenant)]

    def get_chunks_by_doc_id(self, doc_id: int) -> list[Chunk]:
        """Retrieve all chunks for a given document, ordered by chunk_index."""
        conn = self._connect()
        c = conn.cursor()
        c.execute(
            f"SELECT {_CHUNK_COLS} FROM chunks WHERE doc_id = ? ORDER BY chunk_index",
            (doc_id,),
        )
        rows = c.fetchall()
        conn.close()
        return [_row_to_chunk(r) for r in rows]

    def list_tenants(self) -> list[str]:
        """列出库里出现过的租户（启动时按租户恢复索引）。"""
        conn = self._connect()
        rows = conn.execute("SELECT DISTINCT tenant FROM documents ORDER BY tenant").fetchall()
        conn.close()
        return [r[0] for r in rows]

    def get_chunk_count(self, tenant: str | None = None) -> int:
        conn = self._connect()
        c = conn.cursor()
        if tenant is None:
            c.execute("SELECT COUNT(*) FROM chunks")
        else:
            c.execute("SELECT COUNT(*) FROM chunks WHERE tenant = ?", (tenant,))
        count = c.fetchone()[0]
        conn.close()
        return count


# 列名写死，不用 SELECT *：加 tenant 列后位置会错位，不显式列举就会穿错列
_CHUNK_COLS = ("id, doc_id, chunk_index, text, article, section, subsection, "
               "title, parent_article, strategy")
_DOC_COLS = "id, tenant, filename, title, page_count, file_path, file_size"


def _row_to_chunk(r) -> Chunk:
    return Chunk(
        id=r[0], doc_id=r[1], chunk_index=r[2], text=r[3],
        article=r[4], section=r[5], subsection=r[6],
        title=r[7], parent_article=r[8], strategy=r[9],
    )


def _row_to_document(r, with_created: bool = False) -> Document:
    doc = Document(
        id=r[0], tenant=r[1], filename=r[2], title=r[3],
        page_count=r[4], file_path=r[5], file_size=r[6],
    )
    if with_created and len(r) > 7 and r[7]:
        doc.created_at = r[7]
    return doc
