"""Prometheus 指标：把网关的行为变成可抓取的时序数据。

为什么单独一个 registry：默认的 `REGISTRY` 是全局的，测试里重复 import 会报
duplicated timeseries；用自建 registry 后，测试可以自己造一份干净的实例。
"""
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

REGISTRY = CollectorRegistry(auto_describe=True)

# 调用次数：按租户 / 模型 / 后端 / 结果切片
# status 取值：ok / error（后端异常）/ quota（被配额拦下）
LLM_REQUESTS = Counter(
    "llm_requests_total",
    "LLM 调用次数",
    ["tenant", "model", "provider", "status"],
    registry=REGISTRY,
)

# token 按 kind 分开：prompt（输入）与 completion（输出）价格不同，混在一起就没法算钱
LLM_TOKENS = Counter(
    "llm_tokens_total",
    "LLM token 数",
    ["tenant", "model", "kind"],
    registry=REGISTRY,
)

# 成本：Counter 只增不减，适合「累计花掉多少钱」这种单调量
LLM_COST = Counter(
    "llm_cost_usd_total",
    "累计成本（美元）",
    ["tenant", "model"],
    registry=REGISTRY,
)

# 延迟用 Histogram：能算分位数，也能算「超过 2s 的比例」
LLM_LATENCY = Histogram(
    "llm_request_latency_seconds",
    "LLM 调用耗时",
    ["tenant", "model"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)

# 配额拒绝：必须单独立指标，否则「429 变多」只能从日志里翻
QUOTA_REJECTIONS = Counter(
    "llm_quota_rejections_total",
    "配额拒绝次数",
    ["tenant", "reason"],
    registry=REGISTRY,
)


def record_success(tenant: str, model: str, provider: str,
                   prompt_tokens: int, completion_tokens: int,
                   cost_usd: float, latency_sec: float):
    LLM_REQUESTS.labels(tenant=tenant, model=model, provider=provider, status="ok").inc()
    LLM_TOKENS.labels(tenant=tenant, model=model, kind="prompt").inc(prompt_tokens)
    LLM_TOKENS.labels(tenant=tenant, model=model, kind="completion").inc(completion_tokens)
    LLM_COST.labels(tenant=tenant, model=model).inc(cost_usd)
    LLM_LATENCY.labels(tenant=tenant, model=model).observe(latency_sec)


def record_error(tenant: str, model: str, provider: str):
    LLM_REQUESTS.labels(tenant=tenant, model=model, provider=provider, status="error").inc()


def record_rejection(tenant: str, reason: str):
    QUOTA_REJECTIONS.labels(tenant=tenant, reason=reason).inc()


def render() -> bytes:
    return generate_latest(REGISTRY)


def reset_for_tests():
    """测试用：清空所有指标的子系列（不影响 registry 对象本身）。"""
    for metric in (LLM_REQUESTS, LLM_TOKENS, LLM_COST, LLM_LATENCY, QUOTA_REJECTIONS):
        metric.clear()
