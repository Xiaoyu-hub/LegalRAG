"""Provider 工厂：按配置造后端，业务侧只认 `Provider` 协议。"""
import os

from backend.generation.providers.base import Provider, ProviderResponse


def build_provider(kind: str | None = None, model: str | None = None,
                   fallback: str | None = None) -> Provider:
    """按 provider 名构造后端。

    kind 优先级：显式参数 > 环境变量 LLM_PROVIDER > 默认 "ollama"。
    取值：ollama | openai | fake | extractive
    """
    from backend.generation.generator import DEFAULT_FALLBACK_MODEL, DEFAULT_MODEL

    kind = kind or os.getenv("LLM_PROVIDER", "ollama")
    model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
    fallback = fallback or os.getenv("LLM_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)

    if kind == "ollama":
        from backend.generation.providers.ollama_provider import OllamaProvider
        return OllamaProvider(model=model, fallback=fallback)

    if kind in ("openai", "openai-compatible"):
        from backend.generation.providers.openai_provider import (
            OpenAICompatibleProvider,
        )
        return OpenAICompatibleProvider(
            base_url=os.getenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1"),
            model=model,
            api_key=os.getenv("LLM_API_KEY", ""),
        )

    if kind == "fake":
        from backend.generation.providers.fake import FakeProvider
        # 压测时会用 FAKE_LATENCY_MS 模拟真实模型耗时
        latency_ms = float(os.getenv("FAKE_LATENCY_MS", "0") or 0)
        return FakeProvider(latency_sec=latency_ms / 1000.0)

    if kind == "extractive":
        # 无模型环境的确定性基线：不做生成，只从上下文里抽句子并带引用。
        # 详细说明见 providers/extractive.py 顶部。
        from backend.generation.providers.extractive import ExtractiveProvider
        return ExtractiveProvider(model=model)

    raise ValueError(
        f"Unknown provider {kind!r}; expected one of ollama / openai / fake / extractive"
    )


__all__ = ["Provider", "ProviderResponse", "build_provider"]
