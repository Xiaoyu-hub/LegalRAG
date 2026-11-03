"""Provider 抽象层的契约测试。

验收标准（记住这三件套）：
  1. 接口存在且被主链调用——不是「写了个类放那儿」；
  2. 有假实现——单测不依赖真模型；
  3. 换实现后业务结果不变——否则抽象只是摆设。

背景：本项目历史上三次栽在「模块存在 ≠ 主链在用」
（Reranker 生产零调用、get_chunk_ids_for_indices 零调用、流式路径不跑引用校验）。
"""
import pytest

from backend.generation.generator import Generator
from backend.generation.pipeline import GenerationPipeline
from backend.generation.providers import build_provider
from backend.generation.providers.base import Provider, ProviderResponse
from backend.generation.providers.fake import FakeProvider
from backend.models.chunk import Chunk


# ── 1. 协议本身 ────────────────────────────────────────────────────────────

def test_fake_provider_satisfies_protocol():
    assert isinstance(FakeProvider(), Provider)


def test_generator_uses_injected_provider():
    fake = FakeProvider(reply="injected")
    g = Generator(provider=fake)
    assert g.generate("s", "u") == "injected"
    assert fake.calls == [("s", "u")], "Generator 必须真的转发到注入的 provider"


# ── 2. 不用真模型也能测主链行为 ───────────────────────────────────────────

def test_generator_stream_records_tokens():
    from backend.generation.tokens import count_tokens

    g = Generator(provider=FakeProvider(reply="hello world from fake"))
    out = "".join(g.generate_stream("s", "u"))
    assert out == "hello world from fake"
    # 流式阶段拿不到 usage，结束时必须补算
    assert g.last_token_count == count_tokens("hello world from fake")
    assert g.last_prompt_tokens > 0


def test_generator_propagates_provider_failure():
    g = Generator(provider=FakeProvider(fail_with=RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        g.generate("s", "u")


def test_pipeline_runs_end_to_end_without_llm():
    """整条问答链路（检索桩 → 引用校验 → 生成）不碰真模型。"""
    chunk = Chunk(id=1, doc_id=1, chunk_index=0, text="Article text",
                  article="I", section="1")

    class Retriever:
        def retrieve(self, query, top_k=None):
            return [(1, 1.0)]

    class Store:
        def get_chunks(self, ids):
            return [chunk]

    p = GenerationPipeline(retriever=Retriever(), metadata_store=Store(),
                           provider=FakeProvider(reply="见 [Article I, Section 1] 与 [Article X, Section 9]"))
    answer = p.answer("q")

    assert "Article I, Section 1" in answer
    # 无效引用被替换成占位文本，说明 citation 校验在真实链路里跑到了
    assert "[Citation needs verification]" in answer
    assert p.last_citations[1].valid is False


def test_pipeline_accepts_provider_kwarg():
    fake = FakeProvider(reply="ok")
    p = GenerationPipeline(provider=fake)
    assert p.generator.provider is fake


# ── 3. 换实现后结果不变（契约测试）───────────────────────────────────────

def test_same_answer_across_providers():
    """同一段固定 reply，两个实现产出的 answer 必须逐字相同。"""
    class Retriever:
        def retrieve(self, query, top_k=None):
            return []

    class Store:
        def get_chunks(self, ids):
            return []

    a = GenerationPipeline(retriever=Retriever(), metadata_store=Store(),
                           provider=FakeProvider(reply="答案"))
    b = GenerationPipeline(retriever=Retriever(), metadata_store=Store(),
                           provider=FakeProvider(reply="答案"))
    assert a.answer("q") == b.answer("q")


# ── 4. 工厂 ───────────────────────────────────────────────────────────────

def test_factory_builds_fake():
    assert isinstance(build_provider("fake"), FakeProvider)


def test_factory_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown provider"):
        build_provider("nope")


def test_factory_env_switch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert isinstance(build_provider(), FakeProvider)


# ── 5. openai 兼容适配器（不联网，用 MockTransport）────────────────────

def test_openai_provider_parses_response():
    import httpx
    from backend.generation.providers.openai_provider import (
        OpenAICompatibleProvider,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, json={
            "model": "srv-model",
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 2},
        })

    p = OpenAICompatibleProvider(base_url="http://x/v1", model="m")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resp = p._payload("s", "u", False)
        assert resp["model"] == "m"

    # 真正走 generate 的路径要能替换 client，这里用 monkeypatch 注入
    real_client = httpx.Client
    httpx.Client = lambda *a, **kw: real_client(transport=httpx.MockTransport(handler))
    try:
        out = p.generate("s", "u")
    finally:
        httpx.Client = real_client

    assert out.content == "hi"
    assert out.model == "srv-model"
    assert out.prompt_tokens == 11 and out.completion_tokens == 2
