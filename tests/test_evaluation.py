"""Tests for evaluation framework."""

import json
from unittest.mock import patch, MagicMock
import yaml
from backend.evaluation.evaluator import Evaluator
from backend.evaluation.judge import RelevanceJudge
from backend.models.chunk import Chunk


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


class TestQueryAnnotations:
    """Tests for test_queries backward compatibility and annotation fields."""

    def test_existing_queries_still_have_original_fields(self):
        """Existing TEST_QUERIES entries still have all original fields."""
        from backend.evaluation.test_queries import TEST_QUERIES
        for q in TEST_QUERIES:
            assert "query" in q
            assert "relevant_chunk_ids" in q
            assert "category" in q
            assert "notes" in q

    def test_new_queries_have_expected_citations(self):
        """New entries with expected_citations are valid lists."""
        from backend.evaluation.test_queries import TEST_QUERIES
        for q in TEST_QUERIES:
            if "expected_citations" in q:
                citations = q["expected_citations"]
                assert isinstance(citations, list)
                for c in citations:
                    assert "article" in c
                    assert "section" in c

    def test_missing_expected_citations_does_not_break(self):
        """Queries without expected_citations field still work."""
        from backend.evaluation.test_queries import TEST_QUERIES
        for q in TEST_QUERIES:
            citations = q.get("expected_citations", [])
            assert isinstance(citations, list)

    def test_optional_expected_relevance(self):
        """expected_relevance is int 1-5 when present."""
        from backend.evaluation.test_queries import TEST_QUERIES
        for q in TEST_QUERIES:
            rel = q.get("expected_relevance")
            if rel is not None:
                assert isinstance(rel, int)
                assert 1 <= rel <= 5

    def test_query_count_maintained(self):
        """Test query count is preserved (23 entries)."""
        from backend.evaluation.test_queries import TEST_QUERIES
        assert len(TEST_QUERIES) == 23


class TestJudgePromptTemplate:
    """Tests for judge prompt template rendering."""

    def test_renders_query_variable(self):
        """Template renders {{ query }} correctly."""
        j = RelevanceJudge()
        rendered = j.judge_user_template.render(query="test query", answer="", sources="")
        assert "test query" in rendered

    def test_renders_answer_variable(self):
        """Template renders {{ answer }} correctly."""
        j = RelevanceJudge()
        rendered = j.judge_user_template.render(query="", answer="test answer", sources="")
        assert "test answer" in rendered

    def test_renders_sources_variable(self):
        """Template renders {{ sources }} correctly."""
        j = RelevanceJudge()
        rendered = j.judge_user_template.render(query="", answer="", sources="source1\nsource2")
        assert "source1" in rendered
        assert "source2" in rendered

    def test_system_template_loaded(self):
        """Judge system template is loaded from prompts.yaml."""
        j = RelevanceJudge()
        rendered = j.judge_system_template.render()
        assert "Score 1" in rendered or "score" in rendered.lower()
        assert "Excellent" in rendered or "5" in rendered

    def test_sources_formatting(self):
        """Sources are formatted as [Article X, Section Y]: text..."""
        j = RelevanceJudge()
        chunks = [
            Chunk(id=1, article="I", section="1", text="Definition of Person"),
            Chunk(id=2, article="III", section="3", text="Maximum fine provisions"),
        ]
        sources = j._format_sources(chunks)
        assert "[Article I, Section 1]:" in sources
        assert "[Article III, Section 3]:" in sources
        assert "Definition of Person" in sources
        assert "Maximum fine provisions" in sources

    def test_sources_skips_chunks_without_article(self):
        """Chunks with missing article/section are skipped in source formatting."""
        j = RelevanceJudge()
        chunks = [
            Chunk(id=1, article=None, section=None, text="No article"),
            Chunk(id=2, article="I", section="1", text="Has article"),
        ]
        sources = j._format_sources(chunks)
        assert "[Article I, Section 1]:" in sources
        assert "No article" not in sources

    def test_source_text_truncated_to_200_chars(self):
        """Chunk text is truncated to 200 characters."""
        j = RelevanceJudge()
        long_text = "A" * 500
        chunks = [Chunk(id=1, article="I", section="1", text=long_text)]
        sources = j._format_sources(chunks)
        assert "[Article I, Section 1]:" in sources
        assert "A" * 200 in sources
        assert "A" * 500 not in sources


class TestRelevanceJudge:
    """Tests for RelevanceJudge class."""

    def test_init_default_model(self):
        """RelevanceJudge defaults to llama3.1:8b model."""
        j = RelevanceJudge()
        assert j.model == "llama3.1:8b"

    def test_init_custom_model(self):
        """RelevanceJudge accepts custom model name."""
        j = RelevanceJudge(model="custom:latest")
        assert j.model == "custom:latest"

    def test_evaluate_returns_dict_with_score_and_reasoning(self):
        """evaluate() returns dict with 'score' (int) and 'reasoning' (str)."""
        j = RelevanceJudge()
        mock_response = MagicMock()
        mock_response.message.content = json.dumps({"score": 4, "reasoning": "Good answer"})

        with patch("ollama.chat", return_value=mock_response):
            result = j.evaluate("test query", "test answer", [])

        assert isinstance(result, dict)
        assert "score" in result
        assert "reasoning" in result
        assert result["score"] == 4
        assert result["reasoning"] == "Good answer"

    def test_evaluate_uses_temperature_zero_and_format_json(self):
        """evaluate() calls Ollama with temperature=0.0 and format='json'."""
        j = RelevanceJudge()
        mock_response = MagicMock()
        mock_response.message.content = json.dumps({"score": 3, "reasoning": "OK"})

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = mock_response
            j.evaluate("test query", "test answer", [])

        _, kwargs = mock_chat.call_args
        assert kwargs.get("format") == "json"
        options = kwargs.get("options", {})
        assert options.temperature == 0.0

    def test_evaluate_passes_system_and_user_messages(self):
        """evaluate() passes system + user messages to Ollama."""
        j = RelevanceJudge()
        mock_response = MagicMock()
        mock_response.message.content = json.dumps({"score": 3, "reasoning": "OK"})

        with patch("ollama.chat") as mock_chat:
            mock_chat.return_value = mock_response
            j.evaluate("test query", "test answer", [Chunk(id=1, article="I", section="1", text="test")])

        _, kwargs = mock_chat.call_args
        messages = kwargs.get("messages", [])
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_evaluate_handles_ollama_error(self):
        """evaluate() handles Ollama errors gracefully, returns score=None."""
        j = RelevanceJudge()

        with patch("ollama.chat", side_effect=Exception("Ollama not available")):
            result = j.evaluate("test query", "test answer", [])

        assert result["score"] is None
        assert "error" in result
        assert "Ollama not available" in result["error"]

    def test_evaluate_handles_json_parse_failure(self):
        """evaluate() handles non-JSON response from LLM."""
        j = RelevanceJudge()
        mock_response = MagicMock()
        mock_response.message.content = "This is not JSON"

        with patch("ollama.chat", return_value=mock_response):
            result = j.evaluate("test query", "test answer", [])

        assert result["score"] is None
        assert "error" in result

    def test_evaluate_validates_score_range(self):
        """evaluate() validates score is between 1 and 5."""
        j = RelevanceJudge()

        for bad_score in [0, 6, -1, 100]:
            mock_response = MagicMock()
            mock_response.message.content = json.dumps({"score": bad_score, "reasoning": "bad"})

            with patch("ollama.chat", return_value=mock_response):
                result = j.evaluate("test query", "test answer", [])
            assert result["score"] is None
            assert "error" in result

    def test_evaluate_returns_error_none_on_success(self):
        """Successful evaluate() returns error=None."""
        j = RelevanceJudge()
        mock_response = MagicMock()
        mock_response.message.content = json.dumps({"score": 4, "reasoning": "Good answer"})

        with patch("ollama.chat", return_value=mock_response):
            result = j.evaluate("test", "answer", [])

        assert result.get("error") is None

    def test_evaluate_empty_chunks_list(self):
        """evaluate() works with empty chunks list."""
        j = RelevanceJudge()
        mock_response = MagicMock()
        mock_response.message.content = json.dumps({"score": 3, "reasoning": "No sources"})

        with patch("ollama.chat", return_value=mock_response):
            result = j.evaluate("test", "answer", [])

        assert result["score"] == 3
