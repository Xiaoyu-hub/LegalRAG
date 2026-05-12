"""Tests for evaluation framework."""

import json
from backend.evaluation.evaluator import Evaluator


class MockRetriever:
    """Mock retriever that returns predefined results."""
    def __init__(self, results):
        self.results = results

    def retrieve(self, query, top_k=5):
        return self.results


class MockChunk:
    """Minimal mock chunk for testing."""
    def __init__(self, chunk_id):
        self.id = chunk_id


class TestEvaluatorMetrics:
    """Unit tests for Precision@K and Recall@K computation."""

    def test_precision_at_k_perfect(self):
        """Perfect retrieval: all 5 retrieved are relevant -> P@5 = 1.0"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = {1, 2, 3, 4, 5}
        assert ev.precision_at_k(retrieved, relevant, k=5) == 1.0

    def test_precision_at_k_none(self):
        """No relevant retrieved -> P@5 = 0.0"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = {10, 11, 12}
        assert ev.precision_at_k(retrieved, relevant, k=5) == 0.0

    def test_precision_at_k_partial(self):
        """3 of 5 relevant -> P@5 = 0.6"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = {1, 2, 3, 10, 11}
        assert ev.precision_at_k(retrieved, relevant, k=5) == 0.6

    def test_recall_at_k_perfect(self):
        """All 5 relevant docs retrieved in top 5 -> R@5 = 1.0"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = {1, 2, 3, 4, 5}
        assert ev.recall_at_k(retrieved, relevant, k=5) == 1.0

    def test_recall_at_k_partial(self):
        """3 of 10 relevant retrieved -> R@5 = 0.3"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = {1, 2, 3, 10, 11, 12, 13, 14, 15, 16}
        assert ev.recall_at_k(retrieved, relevant, k=5) == 0.3

    def test_recall_at_k_zero_relevant(self):
        """No relevant docs in corpus -> division by zero guard"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = set()
        assert ev.recall_at_k(retrieved, relevant, k=5) == 0.0

    def test_average_metrics(self):
        """Average over multiple queries is correct."""
        def mock_retriever(query, top_k=5):
            return []

        ev = Evaluator(retrieve_fn=mock_retriever)
        queries = [
            {"query": "q1", "relevant_chunk_ids": {1, 2}},
            {"query": "q2", "relevant_chunk_ids": {3}},
        ]
        results = ev.evaluate_all(queries, k=5)
        # Both have 0 precision and 0 recall
        assert results["precision@5"] == 0.0
        assert results["recall@5"] == 0.0

    def test_json_output_structure(self):
        """Evaluator outputs JSON with correct keys."""
        def mock_retriever(query, top_k=5):
            return []

        ev = Evaluator(retrieve_fn=mock_retriever)
        queries = [{"query": "test", "relevant_chunk_ids": {1}}]
        results = ev.evaluate_all(queries, k=5)
        assert "precision@5" in results
        assert "recall@5" in results
        assert "per_query" in results
        assert "total_queries" in results
        assert "evaluated_at" in results
        assert "metrics" in results
        assert results["total_queries"] == 1
        assert results["per_query"][0]["precision@k"] == 0.0

    def test_evaluator_empty_query_list(self):
        """Empty query list returns empty metrics gracefully."""
        ev = Evaluator(retrieve_fn=lambda q, k=5: [])
        results = ev.evaluate_all([], k=5)
        assert results["precision@5"] == 0.0
        assert results["recall@5"] == 0.0
        assert results["per_query"] == []
        assert results["total_queries"] == 0

    def test_evaluator_runs_on_test_queries(self):
        """Evaluator can load TEST_QUERIES and run end-to-end without crash."""
        from backend.evaluation.test_queries import TEST_QUERIES

        def mock_retrieve(query, top_k=5):
            return []

        ev = Evaluator(retrieve_fn=mock_retrieve)
        results = ev.evaluate_all(k=5)
        assert results["total_queries"] == len(TEST_QUERIES)
        assert results["precision@5"] == 0.0
        assert results["recall@5"] == 0.0
        assert len(results["per_query"]) == len(TEST_QUERIES)
