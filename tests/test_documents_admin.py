"""文档管理接口（删除 / 重建索引）与统计接口的测试。

删除这条路径最容易出「数据残留」bug：库记录删了、向量还留在 FAISS 里，
检索命中幽灵条文。所以断言必须同时看数据库、磁盘文件与索引重建调用。
"""
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import documents as documents_module
from backend.api.documents import router as documents_router
from backend.api.stats import router as stats_router
from backend.models.chunk import Chunk
from backend.models.document import Document
from backend.storage.conversation_store import ConversationStore
from backend.storage.metadata_store import MetadataStore


class FakeIndexer:
    """只记账不干活：真 Indexer 会加载 BGE 模型，单测里不能碰。"""

    def __init__(self):
        self.rebuilds = 0

    def rebuild_all(self):
        self.rebuilds += 1
        return 0


@pytest.fixture
def env(tmp_path, monkeypatch):
    upload_dir = tmp_path / "documents"
    upload_dir.mkdir()
    # 删除接口会把 file_path 与 UPLOAD_DIR 做 commonpath 校验，指到临时目录才测得到
    monkeypatch.setattr(documents_module, "UPLOAD_DIR", str(upload_dir))

    db_path = str(tmp_path / "meta.db")
    store = MetadataStore(db_path=db_path)
    indexer = FakeIndexer()

    app = FastAPI()
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")
    app.state.metadata_store = store
    app.state.conversation_store = ConversationStore(db_path=db_path)
    app.state.processing_status = {}
    app.get_indexer = lambda tenant: indexer

    return {
        "app": app,
        "client": TestClient(app),
        "store": store,
        "indexer": indexer,
        "upload_dir": upload_dir,
    }


def _add_document(env, tenant="demo", filename="law.pdf"):
    path = env["upload_dir"] / tenant / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4 fake")
    doc_id = env["store"].insert_document(
        Document(filename=filename, file_path=str(path), file_size=13, tenant=tenant)
    )
    env["store"].insert_chunks(doc_id, [
        Chunk(doc_id=doc_id, chunk_index=0, text="Article I. General Provisions",
              article="I", section="1"),
    ])
    env["app"].state.processing_status[doc_id] = "ready"
    return doc_id, path


def test_delete_removes_row_file_and_rebuilds_index(env):
    doc_id, path = _add_document(env)

    body = env["client"].delete(f"/api/v1/documents/{doc_id}").json()
    assert body["status"] == "ok"
    assert body["data"]["deleted"] == doc_id
    assert body["data"]["file_removed"] is True

    assert env["store"].get_document(doc_id, tenant="demo") is None
    assert env["store"].get_chunk_count("demo") == 0
    assert not path.exists()
    assert env["indexer"].rebuilds == 1, "删完必须重建索引，否则 FAISS 里留幽灵向量"
    assert doc_id not in env["app"].state.processing_status


def test_delete_is_tenant_scoped(env):
    doc_id, _ = _add_document(env, tenant="demo")
    r = env["client"].delete(f"/api/v1/documents/{doc_id}",
                             headers={"X-Tenant-Id": "legal"})
    assert r.status_code == 404
    assert env["store"].get_document(doc_id, tenant="demo") is not None


def test_delete_unknown_document_returns_404(env):
    assert env["client"].delete("/api/v1/documents/4242").status_code == 404


def test_reindex_requeues_document(env, monkeypatch):
    doc_id, _ = _add_document(env)
    calls = []
    monkeypatch.setattr(documents_module, "process_document_task",
                        lambda *a, **kw: calls.append((a, kw)))

    body = env["client"].post(f"/api/v1/documents/{doc_id}/reindex").json()
    assert body["data"]["status"] == "processing"
    assert env["app"].state.processing_status[doc_id] == "processing"
    assert calls and calls[0][0][0] == doc_id
    assert calls[0][0][3] is True, "重建索引必须走 rebuild=True，否则旧向量留着"


def test_reindex_without_file_reports_error(env):
    doc_id, path = _add_document(env)
    os.remove(path)
    body = env["client"].post(f"/api/v1/documents/{doc_id}/reindex").json()
    assert body["status"] == "error"
    assert "File missing" in body["error"]


def test_stats_counts_documents_and_messages(env):
    _add_document(env)
    conv = env["app"].state.conversation_store.create(tenant="demo")
    env["app"].state.conversation_store.append_message(conv, "user", "what is article I?")

    data = env["client"].get("/api/v1/stats").json()["data"]
    assert data["documents"] == 1
    assert data["documents_ready"] == 1
    assert data["chunks"] == 1
    assert data["conversations"] == 1
    assert data["messages"] == 1
    assert data["recent_documents"][0]["filename"] == "law.pdf"
