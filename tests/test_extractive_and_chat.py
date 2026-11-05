"""抽取式后端（无 LLM 降级基线）与 /chat 落库的测试。

抽取式后端的价值就在这两条断言：
1. 它输出的引用必须能被 CitationBuilder 判为有效（否则「引用校验」这条链形同虚设）；
2. 它拿到的 prompt 与真模型完全一致，所以检索/裁剪/分块出问题时它一样会答错——
   这正是把它当对照组的前提。
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.chat import router as chat_router
from backend.api.conversations import router as conversations_router
from backend.generation.citation_builder import CitationBuilder
from backend.generation.prompt_builder import PromptBuilder
from backend.generation.providers import build_provider
from backend.generation.providers.extractive import ExtractiveProvider
from backend.models.chunk import Chunk
from backend.storage.conversation_store import ConversationStore
from backend.storage.metadata_store import MetadataStore

CHUNKS = [
    Chunk(id=1, doc_id=1, chunk_index=0, article="I", section="1",
          text="Article I. General Provisions\nSection 1. Definitions\n"
               "(a) \"Business Day\" means any day other than Saturday or Sunday."),
    Chunk(id=2, doc_id=1, chunk_index=1, article="II", section="3",
          text="Article II. Enforcement\nSection 3. Administrative Penalties\n"
               "(a) A fine not exceeding five thousand dollars may be imposed."),
]


def _prompt(question: str) -> tuple[str, str]:
    return PromptBuilder(config_path="configs/prompts.yaml").build(question, CHUNKS)


# ── 抽取式后端 ────────────────────────────────────────────────────────────


def test_answers_by_extracting_the_matching_clause():
    system, user = _prompt("What is the maximum fine for administrative penalties?")
    answer = ExtractiveProvider().generate(system, user).content
    assert "five thousand dollars" in answer
    assert "[Article II, Section 3]" in answer


def test_generated_citation_passes_validation():
    system, user = _prompt("How long is a business day defined?")
    answer = ExtractiveProvider().generate(system, user).content

    citations = CitationBuilder().extract(answer)
    assert citations, "答案里必须带引用，否则校验环节没有东西可校验"
    validated = CitationBuilder().validate(citations, CHUNKS)
    assert all(c.valid for c in validated), "自己拼的引用都被判无效，说明格式与 CitationBuilder 不一致"


def test_no_context_means_no_citation():
    """上下文为空时不能编引用：宁可说查不到。"""
    answer = ExtractiveProvider().compose("## Context Documents\n\n## Question\n\nfine?")
    assert "No context documents" in answer
    assert "[Article" not in answer


def test_unrelated_question_does_not_fabricate():
    system, user = _prompt("How do I bake sourdough bread?")
    answer = ExtractiveProvider().generate(system, user).content
    assert "do not mention" in answer
    assert "[Article" not in answer


def test_stream_yields_same_text_as_generate():
    system, user = _prompt("fine for administrative penalties?")
    provider = ExtractiveProvider()
    streamed = "".join(provider.stream(system, user))
    assert streamed == provider.generate(system, user).content


def test_build_provider_supports_extractive(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "extractive")
    assert isinstance(build_provider(), ExtractiveProvider)


# ── /chat 落库 ────────────────────────────────────────────────────────────


class _StubRetriever:
    def retrieve(self, query, top_k=10):
        return [(c.id, 1.0) for c in CHUNKS]


class _StubPipeline:
    """只回一段带引用的固定答案，把「检索与生成」换成常量，专测落库。"""

    def __init__(self, *args, **kwargs):
        self.last_chunks = CHUNKS
        self.last_citations = CitationBuilder().validate(
            CitationBuilder().extract("A fine may be imposed [Article II, Section 3]."),
            CHUNKS,
        )

    def answer_stream(self, query, document_id=None):
        for piece in ["A fine may be imposed ", "[Article II, Section 3]."]:
            yield piece


@pytest.fixture
def chat_client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "meta.db")
    app = FastAPI()
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(conversations_router, prefix="/api/v1")
    app.state.metadata_store = MetadataStore(db_path=db_path)
    app.state.conversation_store = ConversationStore(db_path=db_path)
    app.state.processing_status = {}
    app.state.last_chat_sources = {}
    app.state.last_chat_citations = {}
    app.state.reranker = None
    app.state.gateway = None

    import backend.generation.pipeline as pipeline_module
    import backend.retrieval.hybrid_search as hybrid_module

    monkeypatch.setattr(pipeline_module, "GenerationPipeline", _StubPipeline)
    monkeypatch.setattr(hybrid_module, "HybridSearch", lambda **kw: _StubRetriever())
    return TestClient(app), app


def test_chat_persists_question_and_answer(chat_client):
    client, app = chat_client
    conv = client.post("/api/v1/conversations", json={}).json()["data"]["id"]

    r = client.post("/api/v1/chat/", json={"question": "max fine?",
                                          "conversation_id": conv})
    assert r.status_code == 200
    assert "five" not in r.text and "[Article II, Section 3]" in r.text

    detail = client.get(f"/api/v1/conversations/{conv}").json()["data"]
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == "max fine?"
    assistant = detail["messages"][1]
    assert "[Article II, Section 3]" in assistant["content"]
    assert assistant["sources"][0]["chunk_id"] == 1
    assert assistant["sources"][0]["citation_valid"] is True
    assert assistant["latency_ms"] >= 0

    # 标题在首条提问时就定了，前端侧栏才有东西显示
    assert client.get("/api/v1/conversations").json()["data"]["conversations"][0]["title"] == "max fine?"


def test_chat_without_conversation_does_not_write(chat_client):
    client, app = chat_client
    client.post("/api/v1/chat/", json={"question": "no convo"})
    assert app.state.conversation_store.count("demo") == {"conversations": 0, "messages": 0}


def test_chat_rejects_unknown_conversation(chat_client):
    client, _ = chat_client
    r = client.post("/api/v1/chat/", json={"question": "q", "conversation_id": 999})
    assert r.status_code == 404


def test_chat_rejects_overlong_question(chat_client):
    client, _ = chat_client
    r = client.post("/api/v1/chat/", json={"question": "x" * 5000})
    assert r.json()["status"] == "error"


def test_sources_endpoint_returns_last_turn(chat_client):
    client, _ = chat_client
    client.post("/api/v1/chat/", json={"question": "max fine?", "session_id": "s1"})
    data = client.get("/api/v1/chat/sources", params={"session_id": "s1"}).json()["data"]
    assert data["sources"][0]["chunk_id"] == 1
    assert data["citations"][0]["valid"] is True
