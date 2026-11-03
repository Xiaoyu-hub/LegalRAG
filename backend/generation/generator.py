import logging
import time

import tiktoken
from ollama import chat, list as ollama_list, pull, ResponseError

logger = logging.getLogger(__name__)

# 主/备模型的唯一来源：Generator 与 GenerationPipeline 都从这里取，避免两处默认值打架
DEFAULT_MODEL = "llama3.2:3b"
DEFAULT_FALLBACK_MODEL = "llama3.1:8b"

# 上下文窗口与输出预算（Ollama options）
NUM_CTX = 4096
NUM_PREDICT = 1024
# 输入预算 = 窗口 - 保留给输出，否则 prompt 与输出抢同一块 4096，尾部会被截
INPUT_TOKEN_BUDGET = NUM_CTX - NUM_PREDICT

_ENC = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """真实 token 计数。

    旧实现用 len(text.split())：实测误差 英文 −8.3%、中文 −97.6%、中英混 −72.0%
    （中文没空格，整句只算 1 个 token）。
    """
    if not text:
        return 0
    return len(_ENC.encode(text))


class Generator:

    def __init__(self, model: str = DEFAULT_MODEL, fallback: str = DEFAULT_FALLBACK_MODEL):
        self.model = model
        self.fallback = fallback
        self._last_model_used = None
        self._last_latency = None
        self._last_token_count = None
        self._last_prompt_tokens = None

    @property
    def input_token_budget(self) -> int:
        """prompt 可用预算：必须从 num_ctx 里扣掉 num_predict。"""
        return NUM_CTX - NUM_PREDICT

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        models_to_try = [self.model, self.fallback]

        for model in models_to_try:
            try:
                start = time.time()
                response = chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    options={
                        "temperature": 0.1,
                        "num_ctx": 4096,
                        "num_predict": 1024,
                    },
                )
                elapsed = time.time() - start
                self._last_model_used = model
                self._last_latency = elapsed

                content = response.message.content
                self._last_token_count = count_tokens(content)
                self._last_prompt_tokens = count_tokens(system_prompt) + count_tokens(user_prompt)
                logger.info(
                    "Generated with model=%s, latency=%.2fs, prompt_tokens=%d, completion_tokens=%d",
                    model,
                    elapsed,
                    self._last_prompt_tokens,
                    self._last_token_count,
                )
                return content

            except ResponseError as e:
                if e.status_code == 404:
                    if model == self.model:
                        logger.warning(
                            "Model %s not found (404), trying fallback %s",
                            model,
                            self.fallback,
                        )
                        continue
                    logger.warning(
                        "Fallback model %s also not found (404)", model
                    )
                    continue
                logger.error("Ollama ResponseError: %s", e)
                raise

            except ConnectionError:
                raise ConnectionError(
                    "Cannot connect to Ollama. Ensure Ollama is running "
                    "(ollama serve)"
                )

        raise RuntimeError(
            f"Neither {self.model} nor {self.fallback} is available"
        )

    def generate_stream(self, system_prompt: str, user_prompt: str):
        """Stream tokens from Ollama. Yields text tokens as they arrive."""
        models_to_try = [self.model, self.fallback]
        for model in models_to_try:
            try:
                response = chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    options={"temperature": 0.1, "num_ctx": 4096, "num_predict": 1024},
                    stream=True,
                )
                self._last_model_used = model
                for part in response:
                    content = part.get("message", {}).get("content", "")
                    if content:
                        yield content
                return
            except ResponseError as e:
                if e.status_code == 404:
                    if model == self.fallback:
                        raise RuntimeError(f"Neither {self.model} nor {self.fallback} available")
                    continue
                raise
            except ConnectionError:
                raise ConnectionError("Cannot connect to Ollama (ollama serve)")

    def ensure_model_available(self, model: str) -> bool:
        try:
            response = ollama_list()
            available = [m.model for m in response.models if m.model]
            if any(model in m for m in available):
                logger.info("Model %s is already available", model)
                return True

            logger.info("Model %s not found, pulling...", model)
            for progress in pull(model, stream=True):
                status = getattr(progress, "status", "")
                logger.debug("Pulling %s: %s", model, status)
            return True

        except ConnectionError:
            logger.error(
                "Cannot connect to Ollama to check model availability"
            )
            return False
        except Exception as e:
            logger.error("Failed to pull model %s: %s", model, e)
            return False

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
