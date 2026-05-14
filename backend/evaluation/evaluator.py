"""Evaluation framework for retrieval quality metrics.

Per D-20: Precision@5 and Recall@5 standard metrics.
Per D-21: Outputs JSON results for tracking over time.

Per architecture.md section 3.5:
- Precision@5: top-5 results that are relevant / 5
- Recall@5: top-5 results that are relevant / total relevant in corpus
"""

import json
import datetime
from typing import Callable, Optional
from backend.evaluation.test_queries import TEST_QUERIES


class Evaluator:
    """Evaluates retrieval quality using Precision@K and Recall@K."""

    def __init__(self, retrieve_fn: Callable = None,
                 generation_pipeline: Optional[object] = None,
                 judge: Optional[object] = None):
        """Initialize evaluator with optional retrieval, generation, and judge.

        Args:
            retrieve_fn: Function that takes (query, top_k) and returns
                       list of dicts with 'chunk' key containing Chunk object
            generation_pipeline: Object with .answer(query) method returning
                               (answer_text, citations_list) tuple
            judge: RelevanceJudge instance for scoring answer quality
        """
        self.retrieve_fn = retrieve_fn
        self.generation_pipeline = generation_pipeline
        self.judge = judge

    @staticmethod
    def precision_at_k(retrieved_ids: set, relevant_ids: set, k: int) -> float:
        """Precision@K = relevant retrieved / K."""
        if k == 0:
            return 0.0
        return len(retrieved_ids & relevant_ids) / k

    @staticmethod
    def recall_at_k(retrieved_ids: set, relevant_ids: set, k: int) -> float:
        """Recall@K = relevant retrieved / total relevant."""
        if len(relevant_ids) == 0:
            return 0.0  # Division by zero guard
        return len(retrieved_ids & relevant_ids) / len(relevant_ids)

    def evaluate_query(self, query: str, relevant_ids: set, k: int = 5) -> dict:
        """Evaluate a single query, return metric dict."""
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
        """Evaluate all test queries, return aggregate results.

        Args:
            queries: List of query dicts (default: TEST_QUERIES)
            k: Top-K value
            output_path: Optional path to write JSON results
        Returns:
            Dict with precision@k, recall@k, per_query breakdown
        """
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
        """Format evaluation results as a readable string."""
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
        """Compute citation precision = valid citations / total citations.

        Returns 1.0 for empty list (no citations means no incorrect ones).
        """
        if not citations:
            return 1.0
        valid = sum(1 for c in citations if c.valid)
        return valid / len(citations)

    def evaluate_generation(self, queries: list[dict] = None,
                            output_path: str = None) -> dict:
        """Evaluate generation quality across test queries.

        Runs queries through the generation pipeline (if available),
        computes citation precision, and optionally scores with RelevanceJudge.

        Args:
            queries: List of query dicts (default: TEST_QUERIES)
            output_path: Optional path to write JSON results

        Returns:
            Dict with average_citation_precision, per_query breakdown
        """
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
        """Format generation evaluation results as a readable string."""
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
