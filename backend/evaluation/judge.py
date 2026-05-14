"""LLM-as-Judge evaluation module using Ollama.

Per EVAL-04: Uses a local LLM to evaluate generation quality and citation usage.
Judge prompt templates are loaded from configs/prompts.yaml.
"""

import json
from typing import Optional
from jinja2 import Template
import yaml
import ollama
from backend.models.chunk import Chunk


class RelevanceJudge:
    """LLM-as-Judge for evaluating legal answer relevance and citation quality.

    Uses Ollama with a local model to score answers based on correctness
    and proper citation usage. Operates at temperature=0.0 for determinism.

    Attributes:
        model: Ollama model name (default: llama3.1:8b)
        config_path: Path to prompts YAML config
    """

    def __init__(self, model: str = "llama3.1:8b", config_path: str = "configs/prompts.yaml"):
        self.model = model
        self.config_path = config_path
        self._load_templates()

    def _load_templates(self):
        """Load judge prompt templates from prompts.yaml."""
        with open(self.config_path) as f:
            config = yaml.safe_load(f)
        judge_config = config.get("evaluation", {})
        self.judge_system_template = Template(judge_config.get("judge_system", ""))
        self.judge_user_template = Template(judge_config.get("judge_user", ""))

    def _format_sources(self, chunks: list[Chunk]) -> str:
        """Format chunks as source text lines for judge prompt.

        Formats each chunk as "[Article X, Section Y]: text" and skips
        chunks without article/section. Text is truncated to 200 chars.
        """
        source_lines = []
        for c in chunks:
            if not c.article or not c.section:
                continue
            truncated = c.text[:200]
            source_lines.append(f"[Article {c.article}, Section {c.section}]: {truncated}")
        return "\n\n".join(source_lines)

    def evaluate(self, query: str, answer: str, chunks: list[Chunk]) -> dict:
        """Evaluate answer relevance and citation usage.

        Calls Ollama with the judge prompt, parses JSON response.

        Args:
            query: The original question
            answer: The generated answer
            chunks: Source chunks used for generation

        Returns:
            dict with keys:
                - score (int or None): Relevance score 1-5, or None on error
                - reasoning (str): Judge's explanation
                - error (str or None): Error message if something went wrong
        """
        sources = self._format_sources(chunks) if chunks else ""
        user_prompt = self.judge_user_template.render(
            query=query, answer=answer, sources=sources
        )
        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.judge_system_template.render()},
                    {"role": "user", "content": user_prompt},
                ],
                options=ollama.Options(temperature=0.0),
                format="json",
            )
            result = json.loads(response.message.content)
            score = int(result.get("score", 0))
            if score < 1 or score > 5:
                raise ValueError(f"Score {score} out of range 1-5")
            return {
                "score": score,
                "reasoning": result.get("reasoning", ""),
                "error": None,
            }
        except Exception as e:
            return {
                "score": None,
                "reasoning": "",
                "error": str(e),
            }
