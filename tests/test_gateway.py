"""LLM 网关的契约测试。

覆盖 JD 里那三件真问题：多租户隔离（谁能用哪个模型）、成本控制（预算与计量）、
降级（主后端挂了自动换）。
"""
import pytest

from backend.gateway import (
    LLMGateway,
    MeteringStore,
    ModelNotAllowed,
    NoProviderAvailable,
    PricingTable,
    QuotaExceeded,
    Tenant,
    TenantRegistry,
    UnknownTenant,
)
from backend.gateway.pricing import Price
from backend.generation.providers.fake import FakeProvider


def build(tmp_path, providers=None, routes=None, prices=None, tenants=None,
          default="demo"):
    providers = providers or {"fake": FakeProvider(reply="hello gateway")}
    routes = routes or {"m1": "fake", "m2": "fake"}
    pricing = PricingTable(prices or {})
    registry = TenantRegistry(
        tenants or {
            "demo": Tenant(id="demo", models=("m1", "m2"), default_model="m1",
                           monthly_budget_usd=5.0, rpm_limit=100),
            "tiny": Tenant(id="tiny", models=("m1",), default_model="m1",
                           monthly_budget_usd=0.0, rpm_limit=100),
            "restricted": Tenant(id="restricted", models=("m2",), default_model="m2"),
        },
        default,
    )
    metering = MeteringStore(db_path=str(tmp_path / "usage.db"))
    return LLMGateway(providers=providers, routes=routes, pricing=pricing,
                      tenants=registry, metering=metering)


# ── 基本链路 ──────────────────────────────────────────────────────────────

def test_complete_records_usage(tmp_path):
    gw = build(tmp_path)
    res = gw.complete("demo", "system", "user")
    assert res.content == "hello gateway"
    assert res.model == "m1"
    assert res.provider == "fake"
    assert res.prompt_tokens > 0 and res.completion_tokens > 0

    usage = gw.usage("demo")
    assert usage["models"][0]["calls"] == 1
    assert usage["month_cost_usd"] >= 0.0


def test_cost_is_computed_from_price_table(tmp_path):
    # 故意用夸张单价，验证计量口径：prompt 1M 收 1000 美元、completion 1M 收 2000
    gw = build(tmp_path, prices={"m1": Price(input_per_1m=1000.0,
                                             output_per_1m=2000.0)})
    res = gw.complete("demo", "sys", "usr")
    expected = res.prompt_tokens / 1e6 * 1000 + res.completion_tokens / 1e6 * 2000
    assert res.cost_usd == pytest.approx(expected)
    assert gw.usage("demo")["month_cost_usd"] == pytest.approx(expected)


def test_zero_price_for_local_model(tmp_path):
    gw = build(tmp_path, prices={"m1": Price()})
    res = gw.complete("demo", "s", "u")
    assert res.cost_usd == 0.0


# ── 多租户隔离 ────────────────────────────────────────────────────────────

def test_tenant_cannot_use_model_outside_allowlist(tmp_path):
    gw = build(tmp_path)
    with pytest.raises(ModelNotAllowed):
        gw.complete("restricted", "s", "u", model="m1")


def test_unknown_tenant_is_rejected(tmp_path):
    gw = build(tmp_path)
    with pytest.raises(UnknownTenant):
        gw.complete("nobody", "s", "u")


def test_usage_is_isolated_per_tenant(tmp_path):
    gw = build(tmp_path)
    gw.complete("demo", "s", "u")
    gw.complete("demo", "s", "u")
    gw.complete("restricted", "s", "u")

    assert gw.usage("demo")["models"][0]["calls"] == 2
    assert gw.usage("restricted")["models"][0]["calls"] == 1


# ── 成本控制 ──────────────────────────────────────────────────────────────

def test_budget_exhausted_returns_quota_error(tmp_path):
    gw = build(tmp_path)           # tiny 的月预算是 0
    with pytest.raises(QuotaExceeded) as exc:
        gw.complete("tiny", "s", "u")
    assert exc.value.retry_after > 0


def test_rpm_limit_blocks_after_threshold(tmp_path):
    registry = TenantRegistry(
        {"fast": Tenant(id="fast", models=("m1",), default_model="m1", rpm_limit=2)},
        "fast",
    )
    gw = LLMGateway(
        providers={"fake": FakeProvider()},
        routes={"m1": "fake"},
        pricing=PricingTable({}),
        tenants=registry,
        metering=MeteringStore(db_path=str(tmp_path / "u.db")),
    )
    gw.complete("fast", "s", "u")
    gw.complete("fast", "s", "u")
    with pytest.raises(QuotaExceeded, match="rpm"):
        gw.complete("fast", "s", "u")


# ── 降级 ──────────────────────────────────────────────────────────────────

def test_fallback_to_secondary_model_when_primary_fails(tmp_path):
    class Boom(FakeProvider):
        def generate(self, system_prompt, user_prompt):
            raise RuntimeError("backend down")

    gw = build(
        tmp_path,
        providers={"bad": Boom(), "fake": FakeProvider(reply="from backup")},
        routes={"m1": "bad", "m2": "fake"},
    )
    res = gw.complete("demo", "s", "u", model="m1")
    assert res.model == "m2"
    assert res.content == "from backup"
    assert res.fallback_from == "m1", "必须记下是从哪个模型降下来的"


def test_all_backends_down_raises(tmp_path):
    class Boom(FakeProvider):
        def generate(self, system_prompt, user_prompt):
            raise RuntimeError("down")

    gw = build(tmp_path, providers={"bad": Boom()}, routes={"m1": "bad", "m2": "bad"})
    with pytest.raises(NoProviderAvailable):
        gw.complete("demo", "s", "u")


def test_model_without_route_is_skipped(tmp_path):
    gw = build(tmp_path, routes={"m2": "fake"})
    res = gw.complete("demo", "s", "u", model="m1")
    assert res.model == "m2"


# ── 流式 ──────────────────────────────────────────────────────────────────

def test_stream_records_usage(tmp_path):
    gw = build(tmp_path)
    out = "".join(gw.stream("demo", "s", "u"))
    assert out == "hello gateway"
    usage = gw.usage("demo")
    assert usage["models"][0]["calls"] == 1
    assert usage["models"][0]["completion_tokens"] > 0
