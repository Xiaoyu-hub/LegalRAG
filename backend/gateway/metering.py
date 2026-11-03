"""计量账本：每次调用的 token、成本、延迟落到 SQLite，供配额判断与报表查询。

为什么不用内存计数器：配额要跨进程/跨重启生效，内存一重启就清零，等于预算形同虚设。
"""
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class UsageRecord:
    tenant: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: float
    ok: bool = True
    fallback_from: str = ""


class MeteringStore:
    def __init__(self, db_path: str = "data/usage.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_db(self):
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                month TEXT NOT NULL,
                day TEXT NOT NULL,
                tenant TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                latency_ms REAL NOT NULL DEFAULT 0,
                ok INTEGER NOT NULL DEFAULT 1,
                fallback_from TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_usage_tenant_month ON usage(tenant, month);
            CREATE INDEX IF NOT EXISTS idx_usage_tenant_day ON usage(tenant, day);
        """)
        conn.commit()
        conn.close()

    def record(self, rec: UsageRecord) -> int:
        now = time.time()
        month = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m")
        day = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO usage (ts, month, day, tenant, model, prompt_tokens,"
            " completion_tokens, cost_usd, latency_ms, ok, fallback_from)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (now, month, day, rec.tenant, rec.model, rec.prompt_tokens,
             rec.completion_tokens, rec.cost_usd, rec.latency_ms,
             1 if rec.ok else 0, rec.fallback_from),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    # ── 聚合查询（配额判断与报表都用这些）───────────────────────────────
    def month_cost(self, tenant: str) -> float:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        conn = self._connect()
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM usage WHERE tenant=? AND month=?",
            (tenant, month),
        ).fetchone()
        conn.close()
        return float(row[0])

    def recent_calls(self, tenant: str, window_sec: int = 60) -> int:
        since = time.time() - window_sec
        conn = self._connect()
        row = conn.execute(
            "SELECT COUNT(*) FROM usage WHERE tenant=? AND ts>=?",
            (tenant, since),
        ).fetchone()
        conn.close()
        return int(row[0])

    def summary(self, tenant: str) -> dict:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        conn = self._connect()
        rows = conn.execute(
            "SELECT model, COUNT(*), SUM(prompt_tokens), SUM(completion_tokens),"
            " SUM(cost_usd) FROM usage WHERE tenant=? AND month=? GROUP BY model",
            (tenant, month),
        ).fetchall()
        conn.close()
        return {
            "tenant": tenant,
            "month": month,
            "models": [
                {
                    "model": r[0],
                    "calls": r[1],
                    "prompt_tokens": r[2] or 0,
                    "completion_tokens": r[3] or 0,
                    "cost_usd": round(r[4] or 0.0, 6),
                }
                for r in rows
            ],
        }
