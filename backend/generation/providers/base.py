"""Provider 抽象层：把「调用哪个模型、走什么协议」从业务逻辑里剥离。

背景：`Generator` 原来直接 `from ollama import chat`，导致
  1) 单测必须 mock 模块级全局函数，mock 一改就失效；
  2) 换后端（openai 兼容网关、vLLM、本地 fake）要改业务类；
  3) 依赖 `ollama` 包，缺它就整个 `backend.generation` 导入失败。

现在 `Generator` 只依赖 `Provider` 协议，具体协议由适配器实现。
"""
from dataclasses import dataclass, field
from typing import Iterator, Protocol, runtime_checkable


@dataclass
class ProviderResponse:
    """一次生成的结果 + 计量信息（token 一律为真实计数）。"""

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency: float = 0.0
    extra: dict = field(default_factory=dict)


@runtime_checkable
class Provider(Protocol):
    """所有生成后端的统一接口。

    只要求三件事：能生成、能流式生成、能自报可用性。
    降级（主模型 404 换备用）属于适配器内部策略，不暴露给调用方。
    """

    name: str

    def generate(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        ...

    def stream(self, system_prompt: str, user_prompt: str) -> Iterator[str]:
        ...

    def ensure_available(self, model: str) -> bool:
        ...
