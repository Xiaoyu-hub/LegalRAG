"""OpenAI 兼容后端适配器（vLLM / LM Studio / one-api / 任何 /v1/chat/completions）。

只依赖 httpx，不引入 openai SDK。
"""
import json
import logging
import time
from typing import Iterator

import httpx

from backend.generation.tokens import NUM_PREDICT, count_tokens
from backend.generation.providers.base import ProviderResponse

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    """走 `POST {base_url}/chat/completions` 的通用适配器。"""

    name = "openai-compatible"

    def __init__(self, base_url: str, model: str, api_key: str = "",
                 timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, system_prompt: str, user_prompt: str, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": NUM_PREDICT,
            "stream": stream,
        }

    def generate(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        start = time.time()
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(system_prompt, user_prompt, False),
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        return ProviderResponse(
            content=content,
            model=data.get("model", self.model),
            # 后端没回 usage 时用 tiktoken 兜底，保证计量口径一致
            prompt_tokens=usage.get("prompt_tokens")
            or count_tokens(system_prompt) + count_tokens(user_prompt),
            completion_tokens=usage.get("completion_tokens") or count_tokens(content),
            latency=time.time() - start,
        )

    def stream(self, system_prompt: str, user_prompt: str):
        with httpx.Client(timeout=self.timeout) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(system_prompt, user_prompt, True),
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[len("data:"):].strip()
                    if chunk == "[DONE]":
                        return
                    try:
                        delta = json.loads(chunk)["choices"][0]["delta"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    piece = delta.get("content")
                    if piece:
                        yield piece

    def ensure_available(self, model: str) -> bool:
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{self.base_url}/models", headers=self._headers())
            return resp.status_code == 200
        except Exception as exc:
            logger.error("Cannot reach %s: %s", self.base_url, exc)
            return False
