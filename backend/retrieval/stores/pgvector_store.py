"""pgvector 后端：把向量存进 PostgreSQL（`vector` 类型 + 余弦距离 `<=>`）。

为什么要有它：FAISS 是进程内索引，多实例/重启要靠文件同步；pgvector 把向量和
元数据放同一个库，天然支持按文档/租户过滤。两套实现共用 `VectorStore` 接口，
上层无感。
"""
import logging

import numpy as np

logger = logging.getLogger(__name__)

# 表名固定，带维度后缀避免不同维度互撞
TABLE_PREFIX = "lg_vec"


class PgVectorStore:
    """基于 pgvector 的向量库实现。"""

    name = "pgvector"

    def __init__(self, dsn: str, dimension: int = 1024, table: str | None = None,
                 tenant: str = "demo"):
        self.dsn = dsn
        self.dimension = dimension
        self.tenant = tenant
        # 每个租户一张表：隔离最简单、不靠 WHERE 过滤，索引用得上、也不会串
        self.table = table or f"{TABLE_PREFIX}_{self._safe(tenant)}_{dimension}"
        self._ensure_schema()

    @staticmethod
    def _safe(name: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in name.lower())[:32]

    # ── 内部 ────────────────────────────────────────────────────────────
    def _connect(self):
        import psycopg2
        return psycopg2.connect(self.dsn, connect_timeout=10)

    def _ensure_schema(self):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(
                    f"""CREATE TABLE IF NOT EXISTS {self.table} (
                        chunk_id BIGINT PRIMARY KEY,
                        embedding vector({self.dimension})
                    )"""
                )
                # 余弦距离索引；HNSW 在 0.7.x 已稳定
                cur.execute(
                    f"""CREATE INDEX IF NOT EXISTS {self.table}_hnsw
                        ON {self.table} USING hnsw (embedding vector_cosine_ops)"""
                )

    @staticmethod
    def _to_pg(vec: np.ndarray) -> str:
        return "[" + ",".join(f"{x:.7f}" for x in vec.tolist()) + "]"

    # ── 接口 ────────────────────────────────────────────────────────────
    @property
    def size(self) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {self.table}")
            return int(cur.fetchone()[0])

    @property
    def chunk_ids(self) -> list[int]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT chunk_id FROM {self.table} ORDER BY chunk_id")
            return [r[0] for r in cur.fetchall()]

    def add(self, embeddings: np.ndarray, chunk_ids: list[int]):
        if len(chunk_ids) != len(embeddings):
            raise ValueError("embeddings 与 chunk_ids 数量不一致")
        emb = self._normalize(embeddings)
        with self._connect() as conn, conn.cursor() as cur:
            for vec, cid in zip(emb, chunk_ids):
                cur.execute(
                    f"""INSERT INTO {self.table} (chunk_id, embedding)
                        VALUES (%s, %s::vector)
                        ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding""",
                    (int(cid), self._to_pg(vec)),
                )

    def search_ids(self, query_vec: np.ndarray, k: int = 10) -> list[tuple[int, float]]:
        q = self._normalize(np.asarray(query_vec, dtype=np.float32).reshape(1, -1))[0]
        with self._connect() as conn, conn.cursor() as cur:
            # 余弦距离 1 - cos；转成「越大越相似」与 FAISS 内积口径一致
            cur.execute(
                f"""SELECT chunk_id, 1 - (embedding <=> %s::vector) AS score
                    FROM {self.table}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s""",
                (self._to_pg(q), self._to_pg(q), k),
            )
            return [(int(cid), float(score)) for cid, score in cur.fetchall()]

    def reset(self, dimension: int | None = None):
        if dimension is not None and dimension != self.dimension:
            self.dimension = dimension
            self.table = f"{TABLE_PREFIX}_{self._safe(self.tenant)}_{dimension}"
            self._ensure_schema()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"TRUNCATE {self.table}")

    # pgvector 本身就在数据库里，没有独立索引文件
    def save(self, path: str) -> None:
        return None

    def load(self, path: str) -> bool:
        return True

    # ── 工具 ────────────────────────────────────────────────────────────
    def _normalize(self, embeddings: np.ndarray) -> np.ndarray:
        emb = np.asarray(embeddings, dtype=np.float32)
        if emb.ndim == 1:
            emb = emb.reshape(1, -1)
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return emb / norms

    def mapping_matches(self, expected_ids: list[int]) -> bool:
        return sorted(self.chunk_ids) == sorted(expected_ids)


def build_dsn(host: str = "127.0.0.1", port: int = 5432, user: str = "legalrag",
              password: str = "legalrag", dbname: str = "legalrag_vectors") -> str:
    return f"host={host} port={port} user={user} password={password} dbname={dbname}"
