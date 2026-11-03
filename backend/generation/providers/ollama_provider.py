"""Ollama 适配器：主模型 404 自动降级到备用模型。"""
import logging
import time

from ollama import ResponseError
from ollama import chat
from ollama import list as ollama_list
from ollama import pull

from backend.generation.tokens import NUM_CTX, NUM_PREDICT, count_tokens
from backend.generation.providers.base import ProviderResponse

logger = logging.getLogger(__name__)

DEFAULT_OPTIONS = {"temperature": 0.1, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT}


class OllamaProvider:
    """走 Ollama HTTP API 的适配器。"""

    name = "ollama"

    def __init__(self, model: str, fallback: str):
        self.model = model
        self.fallback = fallback

    # ── 内部：按主→备顺序遍历模型 ──────────────────────────────────────────
    def _models(self) -> list[str]:
        return [self.model, self.fallback]

    def generate(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        for model in self._models():
            try:
                start = time.time()
                response = chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    options=DEFAULT_OPTIONS,
                )
                elapsed = time.time() - start
                content = response.message.content
                return ProviderResponse(
                    content=content,
                    model=model,
                    prompt_tokens=count_tokens(system_prompt) + count_tokens(user_prompt),
                    completion_tokens=count_tokens(content),
                    latency=elapsed,
                )
            except ResponseError as exc:
                if exc.status_code == 404:
                    logger.warning("Model %s not found (404), trying fallback %s",
                                   model, self.fallback)
                    continue
                logger.error("Ollama ResponseError: %s", exc)
                raise
            except ConnectionError:
                raise ConnectionError(
                    "Cannot connect to Ollama. Ensure Ollama is running (ollama serve)"
                )

        raise RuntimeError(f"Neither {self.model} nor {self.fallback} is available")

    def stream(self, system_prompt: str, user_prompt: str):
        for model in self._models():
            try:
                response = chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    options=DEFAULT_OPTIONS,
                    stream=True,
                )
                for part in response:
                    content = part.get("message", {}).get("content", "")
                    if content:
                        yield content
                return
            except ResponseError as exc:
                if exc.status_code == 404:
                    if model == self.fallback:
                        raise RuntimeError(
                            f"Neither {self.model} nor {self.fallback} available"
                        )
                    continue
                raise
            except ConnectionError:
                raise ConnectionError("Cannot connect to Ollama (ollama serve)")

    def ensure_available(self, model: str) -> bool:
        try:
            response = ollama_list()
            available = [m.model for m in response.models if m.model]
            if any(model in m for m in available):
                logger.info("Model %s is already available", model)
                return True

            logger.info("Model %s not found, pulling...", model)
            for progress in pull(model, stream=True):
                logger.debug("Pulling %s: %s", model, getattr(progress, "status", ""))
            return True
        except ConnectionError:
            logger.error("Cannot connect to Ollama to check model availability")
            return False
        except Exception as exc:
            logger.error("Failed to pull model %s: %s", model, exc)
            return False
