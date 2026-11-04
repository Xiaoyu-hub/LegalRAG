"""评测框架的测试。"""

import json
from unittest.mock import patch, MagicMock
import yaml
from backend.evaluation.evaluator import Evaluator
from backend.evaluation.judge import RelevanceJudge
from backend.models.chunk import Chunk


class MockRetriever:
    """假的检索器：返回预先写死的结果。"""
    def __init__(self, results):
        self.results = results

    def retrieve(self, query, top_k=5):
        return self.results


class MockChunk:
    """测试用的最小 chunk 桩。"""
    def __init__(self, chunk_id):
        self.id = chunk_id


class TestEvaluatorMetrics:
    """Precision@K 与 Recall@K 计算的单元测试。"""

    def test_precision_at_k_perfect(self):
        """完美召回：前 5 条全相关，P@5 = 1.0"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = {1, 2, 3, 4, 5}
        assert ev.precision_at_k(retrieved, relevant, k=5) == 1.0

    def test_precision_at_k_none(self):
        """一条相关的都没召回，P@5 = 0.0"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = {10, 11, 12}
        assert ev.precision_at_k(retrieved, relevant, k=5) == 0.0

    def test_precision_at_k_partial(self):
        """前 5 条里 3 条相关，P@5 = 0.6"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = {1, 2, 3, 10, 11}
        assert ev.precision_at_k(retrieved, relevant, k=5) == 0.6

    def test_recall_at_k_perfect(self):
        """全库 5 条相关全进前 5，R@5 = 1.0"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = {1, 2, 3, 4, 5}
        assert ev.recall_at_k(retrieved, relevant, k=5) == 1.0

    def test_recall_at_k_partial(self):
        """全库 10 条相关只召回 3 条，R@5 = 0.3"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = {1, 2, 3, 10, 11, 12, 13, 14, 15, 16}
        assert ev.recall_at_k(retrieved, relevant, k=5) == 0.3

    def test_recall_at_k_zero_relevant(self):
        """全库没有相关文档：兜住除零"""
        ev = Evaluator()
        retrieved = {1, 2, 3, 4, 5}
        relevant = set()
        assert ev.recall_at_k(retrieved, relevant, k=5) == 0.0

    def test_average_metrics(self):
        """多条查询取平均要算对。"""
        def mock_retriever(query, top_k=5):
            return []

        ev = Evaluator(retrieve_fn=mock_retriever)
        queries = [
            {"query": "q1", "relevant_chunk_ids": {1, 2}},
            {"query": "q2", "relevant_chunk_ids": {3}},
        ]
        results = ev.evaluate_all(queries, k=5)
        # 两种情况精确率与召回率都是 0
        assert results["precision@5"] == 0.0
        assert results["recall@5"] == 0.0

    def test_json_output_structure(self):
        """评测器输出的 JSON 键名要正确。"""
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
        """空查询列表要优雅返回空指标。"""
        ev = Evaluator(retrieve_fn=lambda q, k=5: [])
        results = ev.evaluate_all([], k=5)
        assert results["precision@5"] == 0.0
        assert results["recall@5"] == 0.0
        assert results["per_query"] == []
        assert results["total_queries"] == 0

    def test_evaluator_runs_on_test_queries(self):
        """评测器能加载 TEST_QUERIES 并端到端跑通、不崩。"""
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
    """测试用例集的向后兼容性与标注字段。"""

    def test_existing_queries_still_have_original_fields(self):
        """原有测试条目仍保留全部字段。"""
        from backend.evaluation.test_queries import TEST_QUERIES
        for q in TEST_QUERIES:
            assert "query" in q
            assert "relevant_chunk_ids" in q
            assert "category" in q
            assert "notes" in q

    def test_new_queries_have_expected_citations(self):
        """带 expected_citations 的新条目是合法列表。"""
        from backend.evaluation.test_queries import TEST_QUERIES
        for q in TEST_QUERIES:
            if "expected_citations" in q:
                citations = q["expected_citations"]
                assert isinstance(citations, list)
                for c in citations:
                    assert "article" in c
                    assert "section" in c

    def test_missing_expected_citations_does_not_break(self):
        """没有 expected_citations 字段的条目照样能用。"""
        from backend.evaluation.test_queries import TEST_QUERIES
        for q in TEST_QUERIES:
            citations = q.get("expected_citations", [])
            assert isinstance(citations, list)

    def test_optional_expected_relevance(self):
        """有 expected_relevance 时它是 1–5 的整数。"""
        from backend.evaluation.test_queries import TEST_QUERIES
        for q in TEST_QUERIES:
            rel = q.get("expected_relevance")
            if rel is not None:
                assert isinstance(rel, int)
                assert 1 <= rel <= 5

    def test_query_count_maintained(self):
        """测试查询条数保持不变（23 条）。"""
        from backend.evaluation.test_queries import TEST_QUERIES
        assert len(TEST_QUERIES) == 23


class TestJudgePromptTemplate:
    """评委提示词模板渲染测试。"""

    def test_renders_query_variable(self):
        """模板正确渲染 {{ query }}。"""
        j = RelevanceJudge()
        rendered = j.judge_user_template.render(query="test query", answer="", sources="")
        assert "test query" in rendered

    def test_renders_answer_variable(self):
        """模板正确渲染 {{ answer }}。"""
        j = RelevanceJudge()
        rendered = j.judge_user_template.render(query="", answer="test answer", sources="")
        assert "test answer" in rendered

    def test_renders_sources_variable(self):
        """模板正确渲染 {{ sources }}。"""
        j = RelevanceJudge()
        rendered = j.judge_user_template.render(query="", answer="", sources="source1\nsource2")
        assert "source1" in rendered
        assert "source2" in rendered

    def test_system_template_loaded(self):
        """评委的 system 模板从 prompts.yaml 读出。"""
        j = RelevanceJudge()
        rendered = j.judge_system_template.render()
        assert "Score 1" in rendered or "score" in rendered.lower()
        assert "Excellent" in rendered or "5" in rendered

    def test_sources_formatting(self):
        """出处按「[Article X, Section Y]: 正文」格式拼。"""
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
        """缺 article/section 的片段在拼出处时跳过。"""
        j = RelevanceJudge()
        chunks = [
            Chunk(id=1, article=None, section=None, text="No article"),
            Chunk(id=2, article="I", section="1", text="Has article"),
        ]
        sources = j._format_sources(chunks)
        assert "[Article I, Section 1]:" in sources
        assert "No article" not in sources

    def test_source_text_truncated_to_200_chars(self):
        """片段正文截断到 200 字符。"""
        j = RelevanceJudge()
        long_text = "A" * 500
        chunks = [Chunk(id=1, article="I", section="1", text=long_text)]
        sources = j._format_sources(chunks)
        assert "[Article I, Section 1]:" in sources
        assert "A" * 200 in sources
        assert "A" * 500 not in sources


class TestRelevanceJudge:
    """RelevanceJudge 类的测试。"""

    def test_init_default_model(self):
        """评委默认用 llama3.1:8b。"""
        j = RelevanceJudge()
        assert j.model == "llama3.1:8b"

    def test_init_custom_model(self):
        """评委支持自定义模型名。"""
        j = RelevanceJudge(model="custom:latest")
        assert j.model == "custom:latest"

    def test_evaluate_returns_dict_with_score_and_reasoning(self):
        """evaluate() 返回的 dict 里有 score（整数）与 reasoning（字符串）。"""
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
        """evaluate() 调 Ollama 时带 temperature=0.0 与 format='json'。"""
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
        """evaluate() 把 system 与 user 两条消息一起传给 Ollama。"""
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
        """Ollama 报错时 evaluate() 不崩，返回 score=None。"""
        j = RelevanceJudge()

        with patch("ollama.chat", side_effect=Exception("Ollama not available")):
            result = j.evaluate("test query", "test answer", [])

        assert result["score"] is None
        assert "error" in result
        assert "Ollama not available" in result["error"]

    def test_evaluate_handles_json_parse_failure(self):
        """模型返回非 JSON 时 evaluate() 能兜住。"""
        j = RelevanceJudge()
        mock_response = MagicMock()
        mock_response.message.content = "This is not JSON"

        with patch("ollama.chat", return_value=mock_response):
            result = j.evaluate("test query", "test answer", [])

        assert result["score"] is None
        assert "error" in result

    def test_evaluate_validates_score_range(self):
        """evaluate() 校验分数在 1–5 之间。"""
        j = RelevanceJudge()

        for bad_score in [0, 6, -1, 100]:
            mock_response = MagicMock()
            mock_response.message.content = json.dumps({"score": bad_score, "reasoning": "bad"})

            with patch("ollama.chat", return_value=mock_response):
                result = j.evaluate("test query", "test answer", [])
            assert result["score"] is None
            assert "error" in result

    def test_evaluate_returns_error_none_on_success(self):
        """正常完成时 error 字段为 None。"""
        j = RelevanceJudge()
        mock_response = MagicMock()
        mock_response.message.content = json.dumps({"score": 4, "reasoning": "Good answer"})

        with patch("ollama.chat", return_value=mock_response):
            result = j.evaluate("test", "answer", [])

        assert result.get("error") is None

    def test_evaluate_empty_chunks_list(self):
        """片段列表为空时 evaluate() 也能跑。"""
        j = RelevanceJudge()
        mock_response = MagicMock()
        mock_response.message.content = json.dumps({"score": 3, "reasoning": "No sources"})

        with patch("ollama.chat", return_value=mock_response):
            result = j.evaluate("test", "answer", [])

        assert result["score"] == 3


class MockCitation:
    """测试引用准确率用的最小 Citation 桩。"""
    def __init__(self, valid=True):
        self.valid = valid


class TestCitationPrecision:
    """Evaluator.citation_precision() 的测试。"""

    def test_all_valid(self):
        """5 条全有效，准确率 1.0"""
        citations = [MockCitation(valid=True) for _ in range(5)]
        assert Evaluator.citation_precision(citations) == 1.0

    def test_partial_valid(self):
        """5 条里 3 条有效，准确率 0.6"""
        citations = [MockCitation(valid=True) for _ in range(3)] + [MockCitation(valid=False) for _ in range(2)]
        assert Evaluator.citation_precision(citations) == 0.6

    def test_none_valid(self):
        """5 条全无效，准确率 0.0"""
        citations = [MockCitation(valid=False) for _ in range(5)]
        assert Evaluator.citation_precision(citations) == 0.0

    def test_empty_list(self):
        """0/0 取 1.0（边界：没有引用就不存在错引用）"""
        assert Evaluator.citation_precision([]) == 1.0

    def test_single_valid(self):
        """1 条有效，准确率 1.0"""
        assert Evaluator.citation_precision([MockCitation(valid=True)]) == 1.0

    def test_single_invalid(self):
        """1 条无效，准确率 0.0"""
        assert Evaluator.citation_precision([MockCitation(valid=False)]) == 0.0


class TestGenerationEvaluation:
    """Evaluator.evaluate_generation() 的测试。"""

    def test_evaluate_generation_runs_with_mocked_pipeline(self):
        """用桩生成链路跑 evaluate_generation。"""
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
        """传了评委时，输出里带 relevance_score。"""
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
        """JSON 输出结构与约定格式一致。"""
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
        # 逐条查询的结构
        for pq in results["per_query"]:
            assert "query" in pq
            assert "citation_precision" in pq
            assert "total_citations" in pq
            assert "valid_citations" in pq

    def test_evaluate_generation_writes_output_file(self):
        """给了 output_path 就把 JSON 落盘。"""
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
        """空查询列表优雅返回空结果。"""
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
        """不传查询时默认用 TEST_QUERIES。"""
        from backend.evaluation.test_queries import TEST_QUERIES

        def mock_pipeline(query):
            return "Generated answer for: " + query

        def mock_retrieve(q, top_k=5):
            return []

        ev = Evaluator(retrieve_fn=mock_retrieve)
        results = ev.evaluate_generation()
        assert results["total_queries"] == len(TEST_QUERIES)

    def test_format_generation_results(self):
        """结果格式化后是可读文本。"""
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
    """整条评测链路的集成测试。"""

    def test_evaluate_generation_with_mocked_pipeline(self):
        """整条链路（生成用桩）产出的结构合法。"""
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
        """带评委的整条链路输出里含相关性分数。"""
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
        """JSON 输出含下游消费所需的全部键。"""
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
        """生成链路报错不会把评测器带崩。"""
        class FailingPipeline:
            def answer(self, query):
                raise RuntimeError("Pipeline failure")

        def mock_retrieve(q, top_k=5):
            return []

        ev = Evaluator(retrieve_fn=mock_retrieve, generation_pipeline=FailingPipeline())
        results = ev.evaluate_generation()
        assert results["total_queries"] > 0
        assert results["average_citation_precision"] == 1.0  # 没有引用时按 1.0 算

    def test_output_matches_phase1_structure_pattern(self):
        """evaluate_generation 的输出沿用第一阶段格式：per_query、total_queries、evaluated_at。"""
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
