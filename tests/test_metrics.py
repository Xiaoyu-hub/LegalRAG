"""指标（metrics）测试：确认网关行为真的被记成可抓取的时序数据。

为什么值得单独测：指标最容易「写了但没接」，或者 label 拼错导致查不到；
这里直接断言 /metrics 输出的文本内容。
"""
import pytest

from backend.gateway import LLMGateway, MeteringStore, PricingTable, Tenant, TenantRegistry
from backend.gateway.pricing import Price
from backend.generation.providers.fake import FakeProvider
from backend.observability import render
from backend.observability.metrics import reset_for_tests


@pytest.fixture(autouse=True)
def _clean_metrics():
    reset_for_tests()
    yield
    reset_for_tests()


def build(tmp_path, providers=None, routes=None):
    return LLMGateway(
        providers=providers or {"fake": FakeProvider(reply="hello metrics")},
        routes=routes or {"m1": "fake", "m2": "fake"},
        pricing=PricingTable({"m1": Price(input_per_1m=1000.0, output_per_1m=2000.0)}),
        tenants=TenantRegistry({
            "demo": Tenant(id="demo", models=("m1", "m2"), default_model="m1"),
            "broke": Tenant(id="broke", models=("m1",), default_model="m1",
                            monthly_budget_usd=0.0),
            "slow": Tenant(id="slow", models=("m1",), default_model="m1", rpm_limit=1),
        }, "demo"),
        metering=MeteringStore(db_path=str(tmp_path / "u.db")),
    )


def text() -> str:
    return render().decode("utf-8")


def test_success_records_tokens_cost_and_latency(tmp_path):
    gw = build(tmp_path)
    gw.complete("demo", "sys", "usr")

    body = text()
    assert 'llm_requests_total{model="m1",provider="fake",status="ok",tenant="demo"} 1.0' in body
    assert 'llm_tokens_total{kind="prompt",model="m1",tenant="demo"}' in body
    assert 'llm_tokens_total{kind="completion",model="m1",tenant="demo"}' in body
    assert 'llm_cost_usd_total{model="m1",tenant="demo"}' in body
    assert 'llm_request_latency_seconds_count{model="m1",tenant="demo"} 1.0' in body


def test_cost_metric_matches_price_table(tmp_path):
    gw = build(tmp_path)
    res = gw.complete("demo", "sys", "usr")
    body = text()
    # 从 /metrics 里把 cost 样本值抠出来，和返回的 cost 对比
    prefix = 'llm_cost_usd_total{model="m1",tenant="demo"} '
    line = next(l for l in body.splitlines() if l.startswith(prefix))
    assert float(line[len(prefix):]) == pytest.approx(res.cost_usd)


def test_backend_failure_is_counted(tmp_path):
    class Boom(FakeProvider):
        def generate(self, system_prompt, user_prompt):
            raise RuntimeError("down")

    gw = build(tmp_path, providers={"boom": Boom(), "fake": FakeProvider()},
               routes={"m1": "boom", "m2": "fake"})
    gw.complete("demo", "s", "u", model="m1")

    body = text()
    assert 'status="error"' in body, "主模型失败必须留痕，否则看不出降级频率"
    assert 'status="ok"' in body


def test_quota_rejection_is_counted(tmp_path):
    gw = build(tmp_path)
    with pytest.raises(Exception):
        gw.complete("broke", "s", "u")
    body = text()
    assert 'llm_quota_rejections_total{reason="budget",tenant="broke"} 1.0' in body


def test_rpm_rejection_reason_is_labelled(tmp_path):
    gw = build(tmp_path)
    gw.complete("slow", "s", "u")
    with pytest.raises(Exception):
        gw.complete("slow", "s", "u")
    body = text()
    assert 'reason="rpm"' in body


def test_stream_records_metrics(tmp_path):
    gw = build(tmp_path)
    "".join(gw.stream("demo", "s", "u"))
    body = text()
    assert 'llm_requests_total{model="m1",provider="fake",status="ok",tenant="demo"} 1.0' in body
    assert 'llm_tokens_total{kind="completion"' in body


def test_metrics_are_per_tenant_not_global(tmp_path):
    gw = build(tmp_path)
    gw.complete("demo", "s", "u")
    body = text()
    assert 'tenant="demo"' in body
    assert 'tenant="broke"' not in body, "没有调用的租户不应凭空出现序列"
