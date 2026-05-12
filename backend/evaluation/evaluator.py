"""Evaluation framework for retrieval quality metrics.

Per D-20: Precision@5 and Recall@5 standard metrics.
Per D-21: Outputs JSON results for tracking over time.

Per architecture.md section 3.5:
- Precision@5: top-5 results that are relevant / 5
- Recall@5: top-5 results that are relevant / total relevant in corpus
"""

import json
import datetime
from typing import Callable
from backend.evaluation.test_queries import TEST_QUERIES


class Evaluator:
    """Evaluates retrieval quality using Precision@K and Recall@K."""

    def __init__(self, retrieve_fn: Callable = None):
        """Initialize evaluator with a retrieval function.

        Args:
            retrieve_fn: Function that takes (query, top_k) and returns
                       list of dicts with 'chunk' key containing Chunk object
        """
        self.retrieve_fn = retrieve_fn

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
