"""OpenTelemetry 埋点：把一次问答拆成三段可观测的 span。

为什么手动埋而不全用自动探针：自动探针只能告诉你「HTTP 请求花了 800ms」，
回答不了「慢在检索、重排还是模型」。这三段是本项目真正的成本结构，
所以每个关键步骤单独开 span，并带上业务属性（租户、模型、token、成本）。

导出后端默认 `memory`（测试用），生产可切 `console` 或换 OTLP。
"""
import logging
import os
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

logger = logging.getLogger(__name__)

SERVICE_NAME = "legalrag"
_provider: TracerProvider | None = None
_memory: InMemorySpanExporter | None = None


def setup_tracing(exporter: str | None = None, service_name: str = SERVICE_NAME):
    """初始化 tracer provider。重复调用是安全的（幂等）。"""
    global _provider, _memory
    if _provider is not None:
        return _provider

    exporter = exporter or os.getenv("OTEL_EXPORTER", "memory")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))

    if exporter == "memory":
        _memory = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(_memory))
    elif exporter == "console":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif exporter in ("none", ""):
        pass
    else:
        logger.warning("未知 OTEL_EXPORTER=%s，按 none 处理", exporter)

    try:
        trace.set_tracer_provider(provider)
    except Exception as exc:  # 已被别的库设过
        logger.warning("set_tracer_provider failed: %s", exc)
    _provider = provider
    return provider


def get_tracer():
    setup_tracing()
    return trace.get_tracer(SERVICE_NAME)


@contextmanager
def span(name: str, **attributes):
    """开一个 span；属性里值为 None 的跳过（OTel 不接受 None）。"""
    with get_tracer().start_as_current_span(name) as sp:
        for key, value in attributes.items():
            if value is None:
                continue
            sp.set_attribute(key, value)
        yield sp


def set_attrs(sp, **attributes):
    """给已有 span 补属性（比如拿到要等结果才知道 token 数）。"""
    if sp is None:
        return
    for key, value in attributes.items():
        if value is None:
            continue
        try:
            sp.set_attribute(key, value)
        except Exception:
            pass


def get_finished_spans():
    """测试用：取出已结束的 span。"""
    if _memory is None:
        return []
    return list(_memory.get_finished_spans())


def reset_for_tests():
    """测试用：清空已记录的 span。"""
    if _memory is not None:
        _memory.clear()
