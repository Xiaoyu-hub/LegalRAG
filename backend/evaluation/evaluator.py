"""检索质量评测。
- D-20：Precision@5 与 Recall@5
- D-21：结果落 JSON 以便追踪
口径（architecture.md 3.5 节）：
- Precision@5 = 前 5 条里相关的条数 / 5
- Recall@5 = 前 5 条里相关的条数 / 全库里相关的总条数"""

import json
import datetime
from typing import Callable, Optional
from backend.evaluation.test_queries import TEST_QUERIES


class Evaluator:
    """用 Precision@K 与 Recall@K 评估检索质量。"""

    def __init__(self, retrieve_fn: Callable = None,
                 generation_pipeline: Optional[object] = None,
                 judge: Optional[object] = None):
        """初始化评测器（检索、生成、评委三个依赖都可选）。
        参数：
        - retrieve_fn：接收 (query, top_k)，返回若干 dict，每个 dict 的 'chunk' 键是 Chunk 对象
        - generation_pipeline：有 .answer(query) 方法，返回 (答案文本, 引用列表)
        - judge：RelevanceJudge 实例，用来给答案质量打分"""
        self.retrieve_fn = retrieve_fn
        self.generation_pipeline = generation_pipeline
        self.judge = judge

    @staticmethod
    def precision_at_k(retrieved_ids: set, relevant_ids: set, k: int) -> float:
        """Precision@K = 召回的相关的条数 / K。"""
        if k == 0:
            return 0.0
        return len(retrieved_ids & relevant_ids) / k

    @staticmethod
    def recall_at_k(retrieved_ids: set, relevant_ids: set, k: int) -> float:
        """Recall@K = 召回的相关的条数 / 全库相关总数。"""
        if len(relevant_ids) == 0:
            return 0.0  # 兜住分母为 0 的情况
        return len(retrieved_ids & relevant_ids) / len(relevant_ids)

    def evaluate_query(self, query: str, relevant_ids: set, k: int = 5) -> dict:
        """评估单条查询，返回指标 dict。"""
        if self.retrieve_fn is None:
            raise RuntimeError("retrieve_fn not set")

        results = self.retrieve_fn(query, top_k=k)
        retrieved_ids = {r["chunk"].id for r in results}

        return {
            "query": query,
            "precision@k": self.precision_at_k(retrieved_ids, relevant_ids, k),
            "recall@k": self.recall_at_k(retrieved_ids, relevant_ids, k),
            "retrieved_count": len(results),
            "relevant_count": len(relevant_ids),
            "true_positives": len(retrieved_ids & relevant_ids),
        }

    def evaluate_all(self, queries: list[dict] = None, k: int = 5,
                     output_path: str = None) -> dict:
        """跑完整套测试查询，返回汇总结果。
        参数：
        - queries：查询列表（默认用 TEST_QUERIES）
        - k：取前 K 条
        - output_path：可选，把 JSON 结果写到这个路径
        返回：含 precision@k、recall@k 与逐条明细的 dict"""
        if queries is None:
            queries = TEST_QUERIES

        per_query = [
            self.evaluate_query(q["query"], q["relevant_chunk_ids"], k)
            for q in queries
        ]

        precisions = [pq["precision@k"] for pq in per_query]
        recalls = [pq["recall@k"] for pq in per_query]

        results = {
            f"precision@{k}": sum(precisions) / len(precisions) if precisions else 0.0,
            f"recall@{k}": sum(recalls) / len(recalls) if recalls else 0.0,
            "per_query": per_query,
            "total_queries": len(per_query),
            "evaluated_at": datetime.datetime.now().isoformat(),
            "metrics": [f"precision@{k}", f"recall@{k}"],
        }

        if output_path:
            import os
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)
            print(f"Results written to {output_path}")

        return results

    @staticmethod
    def format_results(results: dict) -> str:
        """把评测结果格式化成可读文本。"""
        lines = [
            "=" * 50,
            "Retrieval Evaluation Results",
            "=" * 50,
            f"Evaluated at: {results['evaluated_at']}",
            f"Total queries: {results['total_queries']}",
            "",
            "Metrics:",
        ]
        for metric in results.get("metrics", []):
            lines.append(f"  {metric}: {results[metric]:.4f}")
        lines.append("")
        lines.append("-" * 50)
        return "\n".join(lines)

    @staticmethod
    def citation_precision(citations: list) -> float:
        """计算引用准确率 = 有效引用数 / 引用总数。空列表返回 1.0（一条引用都没有，也就没有错的）。"""
        if not citations:
            return 1.0
        valid = sum(1 for c in citations if c.valid)
        return valid / len(citations)

    def evaluate_generation(self, queries: list[dict] = None,
                            output_path: str = None) -> dict:
        """评估生成质量：把测试查询跑一遍生成链路（可用时），算引用准确率，需要时再交 RelevanceJudge 打分。
        参数：
        - queries：查询列表（默认 TEST_QUERIES）
        - output_path：可选，JSON 落盘路径
        返回：含平均引用准确率与逐条明细的 dict"""
        if queries is None:
            queries = TEST_QUERIES

        per_query = []
        citation_precisions = []

        for q in queries:
            answer_text = ""
            citations = []
            chunks = []

            if self.generation_pipeline is not None:
                try:
                    result = self.generation_pipeline.answer(q["query"])
                    if isinstance(result, tuple) and len(result) == 2:
                        answer_text, citations = result
                    elif isinstance(result, str):
                        answer_text = result
                except Exception:
                    answer_text = ""

            cp = self.citation_precision(citations)
            citation_precisions.append(cp)

            entry = {
                "query": q["query"],
                "citation_precision": cp,
                "total_citations": len(citations),
                "valid_citations": sum(1 for c in citations if c.valid) if citations else 0,
                "citations": [
                    {"text": c.text, "valid": c.valid}
                    for c in citations
                ],
            }

            if self.judge is not None and answer_text:
                judge_result = self.judge.evaluate(q["query"], answer_text, chunks)
                entry["relevance_score"] = judge_result.get("score")
                entry["relevance_reasoning"] = judge_result.get("reasoning", "")
            elif self.judge is not None:
                entry["relevance_score"] = None
                entry["relevance_reasoning"] = ""

            per_query.append(entry)

        avg_cp = (
            sum(citation_precisions) / len(citation_precisions)
            if citation_precisions else 0.0
        )

        with_judge = self.judge is not None and any(
            "relevance_score" in pq for pq in per_query
        )
        if with_judge:
            relevance_scores = [
                pq["relevance_score"]
                for pq in per_query
                if pq.get("relevance_score") is not None
            ]
            avg_relevance = (
                sum(relevance_scores) / len(relevance_scores)
                if relevance_scores else None
            )
        else:
            avg_relevance = None

        results = {
            "average_citation_precision": avg_cp,
            "average_relevance_score": avg_relevance,
            "per_query": per_query,
            "total_queries": len(per_query),
            "judge_model": self.judge.model if self.judge else None,
            "evaluated_at": datetime.datetime.now().isoformat(),
        }

        if output_path:
            import os
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)

        return results

    @staticmethod
    def format_generation_results(results: dict) -> str:
        """把生成质量评测结果格式化成可读文本。"""
        lines = [
            "=" * 60,
            "Generation Evaluation Results",
            "=" * 60,
            f"Evaluated at: {results.get('evaluated_at', 'N/A')}",
            f"Total queries: {results.get('total_queries', 0)}",
            f"Average citation precision: {results.get('average_citation_precision', 0.0):.4f} ({results.get('average_citation_precision', 0.0) * 100:.1f}%)",
        ]
        avg_rel = results.get("average_relevance_score")
        if avg_rel is not None:
            lines.append(f"Average relevance score: {avg_rel:.2f}")
        judge_model = results.get("judge_model")
        if judge_model:
            lines.append(f"Judge model: {judge_model}")
        lines.append("")
        lines.append("-" * 60)
        return "\n".join(lines)
