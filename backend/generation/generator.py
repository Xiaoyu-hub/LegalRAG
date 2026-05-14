import logging
import time

from ollama import chat, list as ollama_list, pull, ResponseError

logger = logging.getLogger(__name__)


class Generator:

    def __init__(self, model: str = "llama3.1:8b", fallback: str = "qwen2.5:7b"):
        self.model = model
        self.fallback = fallback
        self._last_model_used = None
        self._last_latency = None
        self._last_token_count = None

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
                self._last_token_count = len(content.split())
                logger.info(
                    "Generated with model=%s, latency=%.2fs, tokens=%d",
                    model,
                    elapsed,
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
