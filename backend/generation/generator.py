"""生成器门面：把「主备降级 + 计量」这套通用逻辑留在业务侧，协议交给 Provider。

历史：这里原来直接 `from ollama import chat`，于是
  - 缺 ollama 包时整个 backend.generation 导入失败；
  - 单测只能 mock 模块级全局函数；
  - 想接 openai 兼容网关就得改这个类。
现在 `Generator` 只依赖 `Provider` 协议（见 providers/base.py）。
"""
import logging

from backend.generation.providers.base import Provider, ProviderResponse
from backend.generation.tokens import (  # noqa: F401  （对外保持旧导入路径可用）
    INPUT_TOKEN_BUDGET,
    NUM_CTX,
    NUM_PREDICT,
    count_tokens,
)

logger = logging.getLogger(__name__)

# 主/备模型的唯一来源：Generator、GenerationPipeline、provider 工厂都从这里取
DEFAULT_MODEL = "llama3.2:3b"
DEFAULT_FALLBACK_MODEL = "llama3.1:8b"


class Generator:
    """对外的生成入口。默认走 Ollama，可注入任意 Provider。"""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        fallback: str = DEFAULT_FALLBACK_MODEL,
        provider: Provider | None = None,
    ):
        self.model = model
        self.fallback = fallback
        if provider is None:
            from backend.generation.providers.ollama_provider import OllamaProvider
            provider = OllamaProvider(model=model, fallback=fallback)
        self.provider = provider

        self._last_model_used = None
        self._last_latency = None
        self._last_token_count = None
        self._last_prompt_tokens = None

    @property
    def input_token_budget(self) -> int:
        """prompt 可用预算：必须从 num_ctx 里扣掉 num_predict。"""
        return INPUT_TOKEN_BUDGET

    def _record(self, resp: ProviderResponse):
        self._last_model_used = resp.model
        self._last_latency = resp.latency
        self._last_token_count = resp.completion_tokens
        self._last_prompt_tokens = resp.prompt_tokens

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        resp = self.provider.generate(system_prompt, user_prompt)
        self._record(resp)
        logger.info(
            "Generated with provider=%s model=%s, latency=%.2fs, "
            "prompt_tokens=%d, completion_tokens=%d",
            getattr(self.provider, "name", "?"),
            resp.model,
            resp.latency,
            resp.prompt_tokens,
            resp.completion_tokens,
        )
        return resp.content

    def generate_stream(self, system_prompt: str, user_prompt: str):
        """流式输出。token 计量在流结束后补齐（流式阶段拿不到 usage）。"""
        buffer: list[str] = []
        for piece in self.provider.stream(system_prompt, user_prompt):
            buffer.append(piece)
            yield piece
        content = "".join(buffer)
        self._last_model_used = getattr(self.provider, "model", None)
        self._last_token_count = count_tokens(content)
        self._last_prompt_tokens = (
            count_tokens(system_prompt) + count_tokens(user_prompt)
        )

    def ensure_model_available(self, model: str) -> bool:
        return self.provider.ensure_available(model)

    # ── 计量读数（保持旧接口）─────────────────────────────────────────────
    @property
    def last_model_used(self):
        return self._last_model_used

    @property
    def last_latency(self):
        return self._last_latency

    @property
    def last_token_count(self):
        return self._last_token_count

    @property
    def last_prompt_tokens(self):
        return self._last_prompt_tokens
