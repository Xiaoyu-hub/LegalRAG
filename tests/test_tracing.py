"""链路追踪（tracing）测试。

验收三件套：span 真的产生了、属性带着业务信息、嵌套关系正确（否则看不出阶段耗时占比）。
"""
import pytest

from backend.generation.pipeline import GenerationPipeline
from backend.generation.providers.fake import FakeProvider
from backend.models.chunk import Chunk
from backend.observability import tracing


@pytest.fixture(autouse=True)
def _tracing():
    tracing.setup_tracing(exporter="memory")
    tracing.reset_for_tests()
    yield
    tracing.reset_for_tests()


def names() -> list[str]:
    return [s.name for s in tracing.get_finished_spans()]


def test_pipeline_emits_rag_answer_span():
    class Retriever:
        def retrieve(self, query, top_k=None):
            return []

    class Store:
        def get_chunks(self, ids):
            return []

    p = GenerationPipeline(retriever=Retriever(), metadata_store=Store(),
                           provider=FakeProvider(reply="answer"))
    p.answer("what is the fine?")

    spans = tracing.get_finished_spans()
    assert "rag.answer" in [s.name for s in spans]

    rag = next(s for s in spans if s.name == "rag.answer")
    assert rag.attributes["rag.query_chars"] == len("what is the fine?")
    assert rag.attributes["rag.chunks"] == 0
    assert rag.attributes["rag.citations"] == 0


def test_citation_counts_recorded():
    chunk = Chunk(id=1, doc_id=1, chunk_index=0, text="ctx", article="I", section="1")

    class Retriever:
        def retrieve(self, query, top_k=None):
            return [(1, 1.0)]

    class Store:
        def get_chunks(self, ids):
            return [chunk]

    p = GenerationPipeline(retriever=Retriever(), metadata_store=Store(),
                           provider=FakeProvider(
                               reply="见 [Article I, Section 1] 与 [Article X, Section 9]"))
    p.answer("q")

    rag = next(s for s in tracing.get_finished_spans() if s.name == "rag.answer")
    assert rag.attributes["rag.citations"] == 2
    assert rag.attributes["rag.citations_valid"] == 1


def test_llm_span_carries_tokens_and_cost(tmp_path):
    from backend.gateway import LLMGateway, MeteringStore, PricingTable, Tenant, TenantRegistry
    from backend.gateway.pricing import Price

    gw = LLMGateway(
        providers={"fake": FakeProvider(reply="hello")},
        routes={"m1": "fake"},
        pricing=PricingTable({"m1": Price(input_per_1m=1000.0, output_per_1m=2000.0)}),
        tenants=TenantRegistry({"demo": Tenant(id="demo", models=("m1",), default_model="m1")},
                               "demo"),
        metering=MeteringStore(db_path=str(tmp_path / "u.db")),
    )
    res = gw.complete("demo", "sys", "usr")

    llm = next(s for s in tracing.get_finished_spans() if s.name == "llm.complete")
    assert llm.attributes["tenant"] == "demo"
    assert llm.attributes["llm.model"] == "m1"
    assert llm.attributes["llm.provider"] == "fake"
    assert llm.attributes["llm.prompt_tokens"] == res.prompt_tokens
    assert llm.attributes["llm.completion_tokens"] == res.completion_tokens
    assert abs(llm.attributes["llm.cost_usd"] - res.cost_usd) < 1e-12


def test_fallback_is_recorded_on_span(tmp_path):
    from backend.gateway import LLMGateway, MeteringStore, PricingTable, Tenant, TenantRegistry

    class Boom(FakeProvider):
        def generate(self, system_prompt, user_prompt):
            raise RuntimeError("down")

    gw = LLMGateway(
        providers={"boom": Boom(), "fake": FakeProvider(reply="backup")},
        routes={"m1": "boom", "m2": "fake"},
        pricing=PricingTable({}),
        tenants=TenantRegistry({"demo": Tenant(id="demo", models=("m1", "m2"),
                                               default_model="m1")}, "demo"),
        metering=MeteringStore(db_path=str(tmp_path / "u.db")),
    )
    gw.complete("demo", "s", "u")

    llm = next(s for s in tracing.get_finished_spans() if s.name == "llm.complete")
    assert llm.attributes["llm.model"] == "m2"
    assert llm.attributes["llm.fallback_from"] == "m1"


def test_no_span_leak_when_exception(tmp_path):
    from backend.gateway import LLMGateway, MeteringStore, PricingTable, Tenant, TenantRegistry

    class Boom(FakeProvider):
        def generate(self, system_prompt, user_prompt):
            raise RuntimeError("down")

    gw = LLMGateway(
        providers={"boom": Boom()},
        routes={"m1": "boom"},
        pricing=PricingTable({}),
        tenants=TenantRegistry({"demo": Tenant(id="demo", models=("m1",), default_model="m1")},
                               "demo"),
        metering=MeteringStore(db_path=str(tmp_path / "u.db")),
    )
    with pytest.raises(Exception):
        gw.complete("demo", "s", "u")

    spans = tracing.get_finished_spans()
    llm = next(s for s in spans if s.name == "llm.complete")
    # 失败的 span 也要结束并被记录，status 应标成 error
    assert llm.status.status_code.name.lower() == "error"
