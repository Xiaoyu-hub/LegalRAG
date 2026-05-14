import logging

import tiktoken
import yaml
from jinja2 import Template

from backend.models.chunk import Chunk

logger = logging.getLogger(__name__)


class PromptBuilder:

    def __init__(
        self,
        config_path: str = "configs/prompts.yaml",
        max_tokens: int = 4096,
        encoding_name: str = "cl100k_base",
    ):
        self.max_tokens = max_tokens
        self.encoding_name = encoding_name

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        gen_config = config.get("generation", {})
        self.system_template = Template(gen_config.get("system", ""))
        self.user_template = Template(gen_config.get("user", ""))

    def build(self, query: str, chunks: list[Chunk]) -> tuple[str, str]:
        context_parts = []
        for i, chunk in enumerate(chunks):
            article = chunk.article or "Unknown"
            section = chunk.section or "Unknown"
            context_parts.append(
                f'<chunk id="{chunk.id}" article="{article}" '
                f'section="{section}">\n{chunk.text}\n</chunk>'
            )

        system_prompt = self.system_template.render()
        context = "\n\n".join(context_parts)
        user_prompt = self.user_template.render(context=context, query=query)

        enc = tiktoken.get_encoding(self.encoding_name)
        if len(enc.encode(user_prompt)) > self.max_tokens:
            for i in range(len(chunks) - 1, -1, -1):
                context_parts.pop()
                context = "\n\n".join(context_parts)
                user_prompt = self.user_template.render(
                    context=context, query=query
                )
                if len(enc.encode(user_prompt)) <= self.max_tokens:
                    logger.info(
                        "Dropped %d chunks to fit %d token budget",
                        len(chunks) - i,
                        self.max_tokens,
                    )
                    break

        return system_prompt, user_prompt
