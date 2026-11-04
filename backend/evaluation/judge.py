"""LLM 评委模块（走 Ollama）。EVAL-04：用本地模型评生成质量与引用使用情况；评委的提示词模板从 configs/prompts.yaml 加载。"""

import json
from typing import Optional
from jinja2 import Template
import yaml
import ollama
from backend.models.chunk import Chunk


class RelevanceJudge:
    """用 LLM 当评委，评法条问答的相关性与引用质量。依据答案正确性与引用是否恰当打分；temperature=0.0 保证同一输入打分稳定。
    属性：
    - model：Ollama 模型名（默认 llama3.1:8b）
    - config_path：提示词配置路径"""

    def __init__(self, model: str = "llama3.1:8b", config_path: str = "configs/prompts.yaml"):
        self.model = model
        self.config_path = config_path
        self._load_templates()

    def _load_templates(self):
        """从 prompts.yaml 读取评委的提示词模板。"""
        with open(self.config_path) as f:
            config = yaml.safe_load(f)
        judge_config = config.get("evaluation", {})
        self.judge_system_template = Template(judge_config.get("judge_system", ""))
        self.judge_user_template = Template(judge_config.get("judge_user", ""))

    def _format_sources(self, chunks: list[Chunk]) -> str:
        """把检索到的片段整理成评委提示词里的出处行，格式为「[Article X, Section Y]: 正文」；缺 article/section 的片段跳过，正文截断到 200 字符。"""
        source_lines = []
        for c in chunks:
            if not c.article or not c.section:
                continue
            truncated = c.text[:200]
            source_lines.append(f"[Article {c.article}, Section {c.section}]: {truncated}")
        return "\n\n".join(source_lines)

    def evaluate(self, query: str, answer: str, chunks: list[Chunk]) -> dict:
        """评答案的相关性与引用使用情况：把评委提示词发给 Ollama，再解析它返回的 JSON。
        参数：
        - query：用户原始问题
        - answer：生成出来的答案
        - chunks：本次生成所依据的片段
        返回 dict：
        - score（int 或 None）：1–5 分，出错时为 None
        - reasoning（str）：评委给出的理由
        - error（str 或 None）：出错信息"""
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
