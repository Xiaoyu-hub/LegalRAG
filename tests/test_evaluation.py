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


class MockCitation:
    """Minimal citation mock for testing citation_precision."""
    def __init__(self, valid=True):
        self.valid = valid


class TestCitationPrecision:
    """Tests for Evaluator.citation_precision()."""

    def test_all_valid(self):
        """5 valid / 5 total = 1.0"""
        citations = [MockCitation(valid=True) for _ in range(5)]
        assert Evaluator.citation_precision(citations) == 1.0

    def test_partial_valid(self):
        """3 valid / 5 total = 0.6"""
        citations = [MockCitation(valid=True) for _ in range(3)] + [MockCitation(valid=False) for _ in range(2)]
        assert Evaluator.citation_precision(citations) == 0.6

    def test_none_valid(self):
        """0 valid / 5 total = 0.0"""
        citations = [MockCitation(valid=False) for _ in range(5)]
        assert Evaluator.citation_precision(citations) == 0.0

    def test_empty_list(self):
        """0 / 0 = 1.0 (edge case: no citations means no incorrect ones)"""
        assert Evaluator.citation_precision([]) == 1.0

    def test_single_valid(self):
        """1 valid / 1 total = 1.0"""
        assert Evaluator.citation_precision([MockCitation(valid=True)]) == 1.0

    def test_single_invalid(self):
        """0 valid / 1 total = 0.0"""
        assert Evaluator.citation_precision([MockCitation(valid=False)]) == 0.0


class TestGenerationEvaluation:
    """Tests for Evaluator.evaluate_generation()."""

    def test_evaluate_generation_runs_with_mocked_pipeline(self):
        """evaluate_generation runs with mocked pipeline."""
        def mock_pipeline(query):
            return "Generated answer for: " + query

        def mock_retrieve(q, top_k=5):
            return [{"chunk": MockChunk(1)}]

        ev = Evaluator(retrieve_fn=mock_retrieve)
        queries = [
            {"query": "test query 1", "relevant_chunk_ids": {1}},
        ]
        results = ev.evaluate_generation(queries=queries)
        assert "average_citation_precision" in results
        assert "per_query" in results
        assert "total_queries" in results
        assert "evaluated_at" in results
        assert results["total_queries"] == 1
        assert len(results["per_query"]) == 1

    def test_evaluate_generation_with_judge(self):
        """When RelevanceJudge is provided, output includes relevance_score."""
        j = RelevanceJudge()
        mock_response = MagicMock()
        mock_response.message.content = json.dumps({"score": 4, "reasoning": "Good"})

        class MockGenerationPipeline:
            def answer(self, query):
                return ("Generated answer for: " + query, [])

        def mock_retrieve(q, top_k=5):
            return [{"chunk": MockChunk(1)}]

        ev = Evaluator(retrieve_fn=mock_retrieve, generation_pipeline=MockGenerationPipeline(), judge=j)
        queries = [
            {"query": "test query 1", "relevant_chunk_ids": {1}},
        ]
        with patch("ollama.chat", return_value=mock_response):
            results = ev.evaluate_generation(queries=queries)

        per_query = results["per_query"][0]
        assert "relevance_score" in per_query
        assert "relevance_reasoning" in per_query
        assert per_query["relevance_score"] == 4

    def test_evaluate_generation_output_json(self):
        """JSON output structure matches expected format."""
        import datetime

        def mock_pipeline(query):
            return "Generated answer for: " + query

        def mock_retrieve(q, top_k=5):
            return [{"chunk": MockChunk(1)}]

        ev = Evaluator(retrieve_fn=mock_retrieve)
        queries = [
            {"query": "q1", "relevant_chunk_ids": {1}},
            {"query": "q2", "relevant_chunk_ids": {2}},
        ]
        results = ev.evaluate_generation(queries=queries)
        assert "average_citation_precision" in results
        assert "per_query" in results
        assert "total_queries" in results
        assert "judge_model" in results
        assert "evaluated_at" in results
        assert results["total_queries"] == 2
        assert isinstance(results["average_citation_precision"], float)
        assert 0.0 <= results["average_citation_precision"] <= 1.0
        # Per-query structure
        for pq in results["per_query"]:
            assert "query" in pq
            assert "citation_precision" in pq
            assert "total_citations" in pq
            assert "valid_citations" in pq

    def test_evaluate_generation_writes_output_file(self):
        """When output_path is specified, JSON is written to disk."""
        import tempfile
        import os
        import json

        def mock_pipeline(query):
            return "Generated answer for: " + query

        def mock_retrieve(q, top_k=5):
            return [{"chunk": MockChunk(1)}]

        ev = Evaluator(retrieve_fn=mock_retrieve)
        queries = [{"query": "q1", "relevant_chunk_ids": {1}}]

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            output_path = f.name

        try:
            ev.evaluate_generation(queries=queries, output_path=output_path)
            assert os.path.exists(output_path)
            with open(output_path) as f:
                data = json.load(f)
            assert "average_citation_precision" in data
            assert "per_query" in data
        finally:
            os.unlink(output_path)

    def test_evaluate_generation_empty_queries(self):
        """Empty query list returns empty results gracefully."""
        def mock_pipeline(query):
            return "answer"

        def mock_retrieve(q, top_k=5):
            return []

        ev = Evaluator(retrieve_fn=mock_retrieve)
        results = ev.evaluate_generation(queries=[])
        assert results["total_queries"] == 0
        assert results["per_query"] == []
        assert results["average_citation_precision"] == 0.0

    def test_evaluate_generation_defaults_to_test_queries(self):
        """When no queries provided, defaults to TEST_QUERIES."""
        from backend.evaluation.test_queries import TEST_QUERIES

        def mock_pipeline(query):
            return "Generated answer for: " + query

        def mock_retrieve(q, top_k=5):
            return []

        ev = Evaluator(retrieve_fn=mock_retrieve)
        results = ev.evaluate_generation()
        assert results["total_queries"] == len(TEST_QUERIES)

    def test_format_generation_results(self):
        """format_generation_results produces readable output."""
        results = {
            "average_citation_precision": 0.85,
            "total_queries": 5,
            "evaluated_at": "2026-05-14T12:00:00",
            "per_query": [],
        }
        output = Evaluator.format_generation_results(results)
        assert "85.00%" in output or "0.85" in output
        assert "5" in output


class TestEndToEndGenerationEvaluation:
    """Integration tests for full evaluation pipeline."""

    def test_evaluate_generation_with_mocked_pipeline(self):
        """Full pipeline with mocked pipeline produces valid output structure."""
        class MockGenerationPipeline:
            def answer(self, query):
                from backend.models.citation import Citation
                citations = [
                    Citation(text="[Article III, Section 3]", article="III", section="3", valid=True),
                    Citation(text="[Article I, Section 1]", article="I", section="1", valid=False),
                ]
                return "Answer about " + query, citations

        def mock_retrieve(q, top_k=5):
            return [{"chunk": MockChunk(1)}]

        ev = Evaluator(retrieve_fn=mock_retrieve, generation_pipeline=MockGenerationPipeline())
        results = ev.evaluate_generation()
        assert results["total_queries"] > 0
        assert "average_citation_precision" in results
        assert len(results["per_query"]) == results["total_queries"]
        for pq in results["per_query"]:
            assert "query" in pq
            assert "citation_precision" in pq
            assert "total_citations" in pq
            assert "valid_citations" in pq

    def test_evaluate_generation_with_judge_and_pipeline(self):
        """Full pipeline with judge includes relevance scores."""
        from backend.models.citation import Citation
        j = RelevanceJudge()
        mock_response = MagicMock()
        mock_response.message.content = json.dumps({"score": 4, "reasoning": "Good citations"})

        class MockGenerationPipeline:
            def answer(self, query):
                citations = [
                    Citation(text="[Article III, Section 3]", article="III", section="3", valid=True),
                ]
                return "Answer about " + query, citations

        def mock_retrieve(q, top_k=5):
            return [{"chunk": MockChunk(1)}]

        ev = Evaluator(
            retrieve_fn=mock_retrieve,
            generation_pipeline=MockGenerationPipeline(),
            judge=j,
        )
        with patch("ollama.chat", return_value=mock_response):
            results = ev.evaluate_generation()

        assert results["average_relevance_score"] is not None
        assert results["judge_model"] == "llama3.1:8b"
        for pq in results["per_query"]:
            assert "relevance_score" in pq
            assert "relevance_reasoning" in pq

    def test_output_json_has_required_keys(self):
        """JSON output has all required keys for downstream consumption."""
        class MockGenerationPipeline:
            def answer(self, query):
                return "Answer", []

        def mock_retrieve(q, top_k=5):
            return []

        ev = Evaluator(retrieve_fn=mock_retrieve, generation_pipeline=MockGenerationPipeline())
        results = ev.evaluate_generation()
        required_keys = {"average_citation_precision", "per_query", "total_queries", "evaluated_at"}
        assert required_keys.issubset(results.keys())

    def test_handles_generation_pipeline_error(self):
        """Generation pipeline error doesn't crash evaluator."""
        class FailingPipeline:
            def answer(self, query):
                raise RuntimeError("Pipeline failure")

        def mock_retrieve(q, top_k=5):
            return []

        ev = Evaluator(retrieve_fn=mock_retrieve, generation_pipeline=FailingPipeline())
        results = ev.evaluate_generation()
        assert results["total_queries"] > 0
        assert results["average_citation_precision"] == 1.0  # no citations = 1.0

    def test_output_matches_phase1_structure_pattern(self):
        """evaluate_generation output follows Phase 1 pattern (per_query, total_queries, evaluated_at)."""
        class MockGenerationPipeline:
            def answer(self, query):
                return "Answer", []

        def mock_retrieve(q, top_k=5):
            return []

        ev = Evaluator(retrieve_fn=mock_retrieve, generation_pipeline=MockGenerationPipeline())
        results = ev.evaluate_generation()
        assert "per_query" in results
        assert "total_queries" in results
        assert "evaluated_at" in results
        assert isinstance(results["per_query"], list)
        assert isinstance(results["total_queries"], int)
        assert isinstance(results["evaluated_at"], str)
