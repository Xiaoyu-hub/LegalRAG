"""会话持久化与会话接口的测试。

覆盖三件容易被写错的事：
1. 标题：首条用户消息自动成标题（前端不该多发一次改名请求）
2. 隔离：A 租户读不到 B 租户的会话（与文档/chunk 同一套口径）
3. 级联：删会话连带删消息（靠外键，而外键是连接级开关，忘了 PRAGMA 就静默失效）
"""
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.conversations import router as conversations_router
from backend.storage.conversation_store import ConversationStore
from backend.storage.metadata_store import MetadataStore

@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "meta.db")


@pytest.fixture
def store(db_path):
    return ConversationStore(db_path=db_path)


@pytest.fixture
def client(db_path):
    """只挂会话路由的最小应用：不跑 lifespan，不加载向量模型。"""
    app = FastAPI()
    app.include_router(conversations_router, prefix="/api/v1")
    app.state.metadata_store = MetadataStore(db_path=db_path)
    app.state.conversation_store = ConversationStore(db_path=db_path)
    app.state.processing_status = {}
    return TestClient(app)


# ── 存储层 ────────────────────────────────────────────────────────────────


def test_first_user_message_becomes_title(store):
    conv = store.create(tenant="demo")
    assert store.list_conversations(tenant="demo")[0]["title"] == ""

    store.append_message(conv, "user", "What is the definition of Business Day?")
    title = store.list_conversations(tenant="demo")[0]["title"]
    assert title == "What is the definition of Business Day?"

    # 第二条用户消息不能覆盖标题
    store.append_message(conv, "user", "another question")
    assert store.list_conversations(tenant="demo")[0]["title"] == title


def test_long_title_is_truncated(store):
    conv = store.create(tenant="demo")
    store.append_message(conv, "user", "x" * 200)
    title = store.list_conversations(tenant="demo")[0]["title"]
    assert len(title) == 41 and title.endswith("…")


def test_messages_roundtrip_keeps_sources_and_citations(store):
    conv = store.create(tenant="demo")
    sources = [{"chunk_id": 7, "article": "I", "section": "1", "citation_valid": True}]
    citations = [{"text": "[Article I, Section 1]", "article": "I", "section": "1", "valid": True}]
    store.append_message(conv, "user", "q")
    store.append_message(conv, "assistant", "a [Article I, Section 1]",
                         sources=sources, citations=citations, latency_ms=12.5, token_count=9)

    msgs = store.messages(conv)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["sources"] == sources
    assert msgs[1]["citations"] == citations
    assert msgs[1]["latency_ms"] == 12.5


def test_conversations_are_isolated_by_tenant(store):
    a = store.create(tenant="tenant-a")
    store.create(tenant="tenant-b")
    assert [c["id"] for c in store.list_conversations(tenant="tenant-a")] == [a]
    assert store.get(a, tenant="tenant-b") is None
    assert store.delete(a, tenant="tenant-b") is False
    assert store.get(a, tenant="tenant-a") is not None


def test_delete_cascades_messages(store, db_path):
    conv = store.create(tenant="demo")
    store.append_message(conv, "user", "q")
    store.append_message(conv, "assistant", "a")

    assert store.delete(conv, tenant="demo") is True
    assert store.messages(conv) == []
    conn = sqlite3.connect(db_path)
    left = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    assert left == 0, "外键 CASCADE 没生效：messages 变成孤儿行"


def test_count_buckets_by_tenant(store):
    a = store.create(tenant="tenant-a")
    store.append_message(a, "user", "q")
    store.create(tenant="tenant-b")
    assert store.count("tenant-a") == {"conversations": 1, "messages": 1}
    assert store.count("tenant-b") == {"conversations": 1, "messages": 0}


# ── HTTP 接口 ─────────────────────────────────────────────────────────────


def test_create_list_get_delete_conversation(client):
    created = client.post("/api/v1/conversations", json={"title": ""}).json()["data"]
    conv_id = created["id"]

    listed = client.get("/api/v1/conversations").json()["data"]["conversations"]
    assert [c["id"] for c in listed] == [conv_id]

    detail = client.get(f"/api/v1/conversations/{conv_id}").json()["data"]
    assert detail["messages"] == []

    assert client.patch(f"/api/v1/conversations/{conv_id}",
                        json={"title": "罚款上限"}).json()["data"]["title"] == "罚款上限"

    assert client.delete(f"/api/v1/conversations/{conv_id}").json()["data"]["deleted"] == conv_id
    assert client.get(f"/api/v1/conversations/{conv_id}").status_code == 404


def test_unknown_conversation_returns_404(client):
    assert client.get("/api/v1/conversations/999").status_code == 404
    assert client.patch("/api/v1/conversations/999", json={"title": "x"}).status_code == 404
    assert client.delete("/api/v1/conversations/999").status_code == 404


def test_other_tenant_cannot_see_conversation(client):
    conv_id = client.post("/api/v1/conversations", json={}).json()["data"]["id"]
    r = client.get(f"/api/v1/conversations/{conv_id}",
                   headers={"X-Tenant-Id": "legal"})
    assert r.status_code == 404
