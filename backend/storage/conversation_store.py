"""会话与消息的持久化（SQLite）。

为什么单独一张库表而不是放在内存字典里：
- 内存版（旧版 `app.state.last_chat_sources`）一重启就没了，前端刷新一次就丢历史；
- 会话要按租户隔离，而租户隔离在数据库层只有加 `tenant` 列一种做法能和文档/分段保持一致；
- 「历史会话列表 + 重新打开某次对话」是前端最基本的功能，靠内存做不到。

设计约定：
- 一个 conversation 属于一个租户，可选绑定一个 document（问的是哪份文书）；
- message 只存 role / content 与两条 JSON（sources 召回片段、citations 引用校验结果），
  这样前端重开历史对话时不用再跑一次检索就能还原「答案 + 引用」；
- 外键 ON DELETE CASCADE：删会话连带删消息，和 documents→chunks 同一套口径。

为什么单独一个 ``data/conversations.db`` 而不往 ``data/metadata.db`` 里塞：
那个库是**随仓库提交的样本数据**，会话是纯运行时数据，混在一起每次聊天都会把
一个被跟踪的二进制文件改脏。分开以后「源码 / 样本数据 / 运行时数据」三类边界很清楚。
"""
import json
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 标题自动截断长度：再长侧栏就一行放不下
TITLE_MAX_CHARS = 40


class ConversationStore:
    """会话 / 消息两张表的最小 CRUD。

    与 MetadataStore 一样，每个方法自己开连接：SQLite 连接不是线程安全的，
    而 FastAPI 的同步端点会跑在线程池里，共用一个连接会踩
    「SQLite objects created in a thread can only be used in that same thread」。
    """

    def __init__(self, db_path: str = "data/conversations.db"):
        self.db_path = db_path
        self._init_db()

    # ── 连接 ──

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        # 外键是连接级开关且默认 OFF：不显式打开，ON DELETE CASCADE 等于没写
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_db(self):
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant TEXT NOT NULL DEFAULT 'demo',
                title TEXT NOT NULL DEFAULT '',
                document_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                sources TEXT NOT NULL DEFAULT '[]',
                citations TEXT NOT NULL DEFAULT '[]',
                latency_ms REAL NOT NULL DEFAULT 0,
                token_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_conversations_tenant
                ON conversations(tenant, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, id);
        """)
        conn.commit()
        conn.close()

    # ── 会话 ──

    def create(self, tenant: str = "demo", title: str = "",
               document_id: int | None = None) -> int:
        now = _now()
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO conversations (tenant, title, document_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (tenant, title, document_id, now, now),
        )
        conn.commit()
        conv_id = cur.lastrowid
        conn.close()
        return conv_id

    def list_conversations(self, tenant: str = "demo", limit: int = 50) -> list[dict]:
        """按最近活动倒序列出会话，顺带带上消息条数（侧栏要显示）。"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT c.id, c.title, c.document_id, c.created_at, c.updated_at,"
            "       (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id)"
            "  FROM conversations c"
            " WHERE c.tenant = ?"
            " ORDER BY c.updated_at DESC, c.id DESC LIMIT ?",
            (tenant, limit),
        ).fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "title": r[1],
                "document_id": r[2],
                "created_at": r[3],
                "updated_at": r[4],
                "message_count": r[5],
            }
            for r in rows
        ]

    def get(self, conversation_id: int, tenant: str = "demo") -> dict | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT id, title, document_id, created_at, updated_at"
            "  FROM conversations WHERE id = ? AND tenant = ?",
            (conversation_id, tenant),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return {
            "id": row[0],
            "title": row[1],
            "document_id": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }

    def rename(self, conversation_id: int, title: str, tenant: str = "demo") -> bool:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ? AND tenant = ?",
            (title.strip()[:120], _now(), conversation_id, tenant),
        )
        ok = cur.rowcount > 0
        conn.commit()
        conn.close()
        return ok

    def delete(self, conversation_id: int, tenant: str = "demo") -> bool:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM conversations WHERE id = ? AND tenant = ?",
            (conversation_id, tenant),
        )
        ok = cur.rowcount > 0
        conn.commit()
        conn.close()
        return ok

    # ── 消息 ──

    def append_message(self, conversation_id: int, role: str, content: str,
                       sources: list | None = None, citations: list | None = None,
                       latency_ms: float = 0.0, token_count: int = 0) -> int:
        """写一条消息，并把会话的 updated_at 顶到当前时间（侧栏排序靠它）。

        首条用户消息顺手当标题：前端不该为了起个名字多打一个请求。
        """
        now = _now()
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO messages (conversation_id, role, content, sources, citations,"
            " latency_ms, token_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                role,
                content,
                json.dumps(sources or [], ensure_ascii=False),
                json.dumps(citations or [], ensure_ascii=False),
                latency_ms,
                token_count,
                now,
            ),
        )
        msg_id = cur.lastrowid

        if role == "user":
            cur.execute(
                "UPDATE conversations SET updated_at = ?,"
                " title = CASE WHEN title = '' THEN ? ELSE title END"
                " WHERE id = ?",
                (now, _derive_title(content), conversation_id),
            )
        else:
            cur.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )

        conn.commit()
        conn.close()
        return msg_id

    def messages(self, conversation_id: int) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT id, role, content, sources, citations, latency_ms, token_count, created_at"
            "  FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "sources": _loads(r[3]),
                "citations": _loads(r[4]),
                "latency_ms": r[5],
                "token_count": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]

    # ── 统计（给前端仪表盘用）──

    def count(self, tenant: str = "demo") -> dict:
        conn = self._connect()
        conv = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE tenant = ?", (tenant,)
        ).fetchone()[0]
        msg = conn.execute(
            "SELECT COUNT(*) FROM messages m JOIN conversations c"
            " ON c.id = m.conversation_id WHERE c.tenant = ?",
            (tenant,),
        ).fetchone()[0]
        conn.close()
        return {"conversations": conv, "messages": msg}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _derive_title(content: str) -> str:
    """首条用户消息 → 会话标题：去掉换行、压掉多余空格、超长截断。"""
    flat = " ".join((content or "").split())
    if len(flat) <= TITLE_MAX_CHARS:
        return flat
    return flat[:TITLE_MAX_CHARS] + "…"


def _loads(raw: str):
    """JSON 解不开时返回空列表，而不是让一条脏数据把整个会话接口打成 500。"""
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []
