"""Evaluation framework for retrieval quality and generation quality metrics.

Per D-19: Manual test dataset for 20-30 queries with relevance judgments.
Per D-20: Precision@5 and Recall@5 standard metrics.
Per D-21: JSON output for tracking over time.
Per EVAL-03: Citation accuracy metric (citation_precision).
Per EVAL-04: LLM-as-Judge for generation quality evaluation.
"""

from backend.evaluation.evaluator import Evaluator
from backend.evaluation.judge import RelevanceJudge

__all__ = ["Evaluator", "RelevanceJudge"]
