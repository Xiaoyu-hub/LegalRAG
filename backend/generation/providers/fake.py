"""测试用的假 Provider：不联网、不加载模型，行为确定。

用途：让 Generator / GenerationPipeline / chat 接口的单测完全不依赖真模型，
也让 CI 里能跑「有模型才能跑」的那部分逻辑。
"""
import time
from typing import Iterator

from backend.generation.tokens import count_tokens
from backend.generation.providers.base import ProviderResponse


class FakeProvider:
    """可编程的假后端。

    Args:
        reply: 固定返回的文本；也可以用 responses 队列轮流返回
        responses: 依次消费的返回列表（用于测降级/重试）
        fail_with: 若给定异常，则每次调用都抛它
        latency_sec: 人为延迟，用来模拟真实模型耗时（压测网关开销时用）
    """

    name = "fake"

    def __init__(self, reply: str = "fake answer", responses: list[str] | None = None,
                 fail_with: Exception | None = None, stream_chunks: int = 3,
                 latency_sec: float = 0.0):
        self.reply = reply
        self.responses = list(responses or [])
        self.fail_with = fail_with
        self.stream_chunks = stream_chunks
        self.latency_sec = latency_sec
        self.calls: list[tuple[str, str]] = []

    def _sleep(self):
        if self.latency_sec:
            time.sleep(self.latency_sec)

    def _next_reply(self) -> str:
        if self.responses:
            return self.responses.pop(0)
        return self.reply

    def generate(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        self.calls.append((system_prompt, user_prompt))
        if self.fail_with:
            raise self.fail_with
        self._sleep()
        content = self._next_reply()
        return ProviderResponse(
            content=content,
            model="fake-model",
            prompt_tokens=count_tokens(system_prompt) + count_tokens(user_prompt),
            completion_tokens=count_tokens(content),
            latency=0.0,
        )

    def stream(self, system_prompt: str, user_prompt: str) -> Iterator[str]:
        self.calls.append((system_prompt, user_prompt))
        if self.fail_with:
            raise self.fail_with
        self._sleep()
        content = self._next_reply()
        step = max(1, len(content) // max(1, self.stream_chunks))
        for i in range(0, len(content), step):
            yield content[i:i + step]

    def ensure_available(self, model: str) -> bool:
        return self.fail_with is None
