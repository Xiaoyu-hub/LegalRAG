"""评测框架：既评检索质量，也评生成质量。
- D-19：手工标注 20–30 条查询的相关性判定
- D-20：Precision@5 / Recall@5 两个标准指标
- D-21：结果落 JSON，便于长期追踪
- EVAL-03：引用准确率（citation_precision）
- EVAL-04：用 LLM-as-Judge 评生成质量"""

from backend.evaluation.evaluator import Evaluator
from backend.evaluation.judge import RelevanceJudge

__all__ = ["Evaluator", "RelevanceJudge"]
