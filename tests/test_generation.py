import pytest

from backend.models.citation import Citation
from backend.models.chunk import Chunk
from backend.generation.prompt_builder import PromptBuilder


class TestCitationModel:

    def test_constructor_minimal(self):
        c = Citation(text="[Article III, Section 5]", article="III", section="5")
        assert c.text == "[Article III, Section 5]"
        assert c.article == "III"
        assert c.section == "5"
        assert c.subsection is None
        assert c.valid is True
        assert c.confidence == 1.0

    def test_constructor_full(self):
        c = Citation(
            text="[Article 2, Section 5(a)]",
            article="2",
            section="5(a)",
            subsection="(a)",
            valid=False,
            confidence=0.5,
        )
        assert c.text == "[Article 2, Section 5(a)]"
        assert c.article == "2"
        assert c.section == "5(a)"
        assert c.subsection == "(a)"
        assert c.valid is False
        assert c.confidence == 0.5

    def test_field_types(self):
        c = Citation(text="x", article="I", section="1")
        assert isinstance(c.text, str)
        assert isinstance(c.article, str)
        assert isinstance(c.section, str)
        assert isinstance(c.valid, bool)
        assert isinstance(c.confidence, float)

    def test_defaults_override(self):
        c = Citation(text="x", article="I", section="1", confidence=0.0)
        assert c.confidence == 0.0

    def test_subsection_defaults_to_none(self):
        c = Citation(text="x", article="I", section="1")
        assert c.subsection is None


class TestPromptBuilder:

    @pytest.fixture
    def builder(self):
        return PromptBuilder()

    def test_build_returns_tuple_of_strings(self, builder):
        system, user = builder.build("test query", [])
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_system_prompt_is_static(self, builder):
        s1, _ = builder.build("query a", [])
        s2, _ = builder.build("query b", [])
        assert s1 == s2

    def test_user_prompt_contains_query(self, builder):
        _, user = builder.build("What is the fine?", [])
        assert "What is the fine?" in user

    def test_user_prompt_contains_context_when_chunks_provided(self, builder):
        chunk = Chunk(id=1, text="some legal text", article="III", section="5")
        _, user = builder.build("test", [chunk])
        assert "some legal text" in user
        assert "Article" in user or "article" in user

    def test_xml_wrapping_includes_article_and_section(self, builder):
        chunk = Chunk(id=42, text="content here", article="II", section="10")
        _, user = builder.build("q", [chunk])
        assert 'id="42"' in user
        assert 'article="II"' in user or 'Article' in user
        assert 'section="10"' in user or 'Section' in user

    def test_empty_chunks_list(self, builder):
        _, user = builder.build("query", [])
        assert "Context" in user or "query" in user
        assert len(user) > 0

    def test_multiple_chunks_separated(self, builder):
        chunks = [
            Chunk(id=1, text="chunk one", article="I", section="1"),
            Chunk(id=2, text="chunk two", article="II", section="2"),
        ]
        _, user = builder.build("q", chunks)
        assert "chunk one" in user
        assert "chunk two" in user

    def test_truncation_reduces_token_count(self, builder):
        long_text = "legal text " * 5000
        chunk = Chunk(id=1, text=long_text, article="I", section="1")
        _, user = builder.build("short query", [chunk])
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        token_count = len(enc.encode(user))
        assert token_count <= builder.max_tokens

    def test_truncation_preserves_query(self, builder):
        long_text = "legal text " * 5000
        chunk = Chunk(id=1, text=long_text, article="I", section="1")
        _, user = builder.build("preserve this query", [chunk])
        assert "preserve this query" in user

    @pytest.mark.parametrize("max_tokens", [512, 1024, 2048])
    def test_respects_configured_max_tokens(self, max_tokens):
        custom_builder = PromptBuilder(max_tokens=max_tokens)
        long_text = "legal text " * 2000
        chunk = Chunk(id=1, text=long_text, article="I", section="1")
        _, user = custom_builder.build("q", [chunk])
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        assert len(enc.encode(user)) <= max_tokens

    def test_chunk_without_article_section_uses_unknown(self, builder):
        chunk = Chunk(id=1, text="bare text")
        _, user = builder.build("q", [chunk])
        assert "bare text" in user


class TestCitationBuilder:

    @pytest.fixture
    def builder(self):
        from backend.generation.citation_builder import CitationBuilder
        return CitationBuilder()

    def test_extract_roman_article(self, builder):
        text = "The fine is $5000 [Article III, Section 5]."
        citations = builder.extract(text)
        assert len(citations) == 1
        assert citations[0].article == "III"
        assert citations[0].section == "5"
        assert citations[0].text == "[Article III, Section 5]"

    def test_extract_arabic_article(self, builder):
        text = "Per [Article 2, Section 10], the penalty applies."
        citations = builder.extract(text)
        assert len(citations) == 1
        assert citations[0].article == "2"
        assert citations[0].section == "10"

    def test_extract_multiple_citations(self, builder):
        text = (
            "[Article I, Section 1] establishes the right. "
            "[Article III, Section 5(a)] defines penalties. "
            "[Article II, Section 2] limits scope."
        )
        citations = builder.extract(text)
        assert len(citations) == 3
        assert citations[0].article == "I"
        assert citations[1].section == "5(a)"
        assert citations[2].article == "II"

    def test_extract_empty_text(self, builder):
        citations = builder.extract("")
        assert citations == []

    def test_extract_no_citations(self, builder):
        citations = builder.extract("This text has no citations at all.")
        assert citations == []

    def test_extract_subsection(self, builder):
        text = "See [Article V, Section 12(b)] for details."
        citations = builder.extract(text)
        assert len(citations) == 1
        assert citations[0].section == "12(b)"

    def test_extract_case_insensitive(self, builder):
        text = "See [article i, section 1] for details."
        citations = builder.extract(text)
        assert len(citations) == 1

    def test_validate_valid_citations(self, builder):
        chunks = [
            Chunk(id=1, text="a", article="I", section="1"),
            Chunk(id=2, text="b", article="III", section="5"),
        ]
        citations = [
            Citation(text="[Article I, Section 1]", article="I", section="1"),
            Citation(text="[Article III, Section 5]", article="III", section="5"),
        ]
        result = builder.validate(citations, chunks)
        assert all(c.valid for c in result)

    def test_validate_invalid_citation(self, builder):
        chunks = [
            Chunk(id=1, text="a", article="I", section="1"),
        ]
        citations = [
            Citation(text="[Article I, Section 1]", article="I", section="1"),
            Citation(text="[Article X, Section 99]", article="X", section="99"),
        ]
        result = builder.validate(citations, chunks)
        assert result[0].valid is True
        assert result[1].valid is False

    def test_validate_handles_article_section_prefixes(self, builder):
        chunks = [
            Chunk(id=1, text="a", article="Article I", section="Section 1"),
        ]
        citations = [
            Citation(text="[Article I, Section 1]", article="I", section="1"),
        ]
        result = builder.validate(citations, chunks)
        assert result[0].valid is True

    def test_validate_null_chunk_metadata(self, builder):
        chunks = [
            Chunk(id=1, text="a", article=None, section=None),
        ]
        citations = [
            Citation(text="[Article I, Section 1]", article="I", section="1"),
        ]
        result = builder.validate(citations, chunks)
        assert result[0].valid is False

    def test_mark_invalid_replaces_text(self, builder):
        citations = [
            Citation(
                text="[Article X, Section 99]",
                article="X",
                section="99",
                valid=False,
            ),
        ]
        text = "The fine is [Article X, Section 99]."
        result = builder.mark_invalid(text, citations)
        assert "[Citation needs verification]" in result
        assert "[Article X, Section 99]" not in result

    def test_mark_invalid_skips_valid(self, builder):
        citations = [
            Citation(
                text="[Article I, Section 1]",
                article="I",
                section="1",
                valid=True,
            ),
        ]
        text = "The right is [Article I, Section 1]."
        result = builder.mark_invalid(text, citations)
        assert "[Article I, Section 1]" in result
        assert "[Citation needs verification]" not in result

    def test_process_full_pipeline(self, builder):
        chunks = [Chunk(id=1, text="content", article="I", section="1")]
        text = (
            "Right is [Article I, Section 1]. "
            "Invalid is [Article X, Section 99]."
        )
        cleaned, citations = builder.process(text, chunks)
        assert "[Article I, Section 1]" in cleaned
        assert "[Article X, Section 99]" not in cleaned
        assert "[Citation needs verification]" in cleaned
        assert len(citations) == 2
        assert citations[0].valid is True
        assert citations[1].valid is False


class TestGenerator:

    @pytest.fixture
    def generator(self):
        from backend.generation.generator import Generator
        return Generator()

    # 生成逻辑已下沉到 providers/ollama_provider，mock 目标随之改到这里；
    # 这样测的仍是真实主链（Generator → OllamaProvider → ollama.chat）。
    PATCH = "backend.generation.providers.ollama_provider.chat"

    def test_generate_success(self, mocker, generator):
        mock_response = mocker.MagicMock()
        mock_response.message.content = "Generated answer [Article I, Section 1]."
        mocker.patch(self.PATCH, return_value=mock_response)
        result = generator.generate("system", "user")
        assert "Generated answer" in result
        assert generator.last_model_used == generator.model
        assert generator.last_token_count > 0, "token 计数必须是真实计数，不能是 None"

    def test_generate_fallback_on_404(self, mocker, generator):
        mock_response = mocker.MagicMock()
        mock_response.message.content = "Fallback answer."
        mocker.patch(
            self.PATCH,
            side_effect=[
                __import__("ollama").ResponseError("model not found", 404),
                mock_response,
            ],
        )
        result = generator.generate("system", "user")
        assert result == "Fallback answer."
        # 主备模型的默认值以 generator 模块常量为唯一来源（旧版本测试写死 qwen2.5:7b，
        # 与实现/README 的 llama3.1:8b 不同步）
        from backend.generation.generator import DEFAULT_FALLBACK_MODEL
        assert generator.last_model_used == DEFAULT_FALLBACK_MODEL

    def test_generate_raises_connection_error(self, mocker, generator):
        mocker.patch(self.PATCH, side_effect=ConnectionError("refused"))
        with pytest.raises(ConnectionError, match="Cannot connect to Ollama"):
            generator.generate("system", "user")

    def test_generate_raises_runtime_error_when_both_fail(self, mocker, generator):
        err_404 = __import__("ollama").ResponseError("model not found", 404)
        mocker.patch(self.PATCH, side_effect=[err_404, err_404])
        with pytest.raises(RuntimeError, match="Neither"):
            generator.generate("system", "user")

    def test_generate_propagates_non_404_error(self, mocker, generator):
        mocker.patch(
            self.PATCH,
            side_effect=__import__("ollama").ResponseError("Bad request", 400),
        )
        with pytest.raises(__import__("ollama").ResponseError):
            generator.generate("system", "user")

    def test_ensure_model_available_returns_true_when_available(self, mocker, generator):
        mock_model = mocker.MagicMock()
        mock_model.model = "llama3.1:8b"
        mock_response = mocker.MagicMock()
        mock_response.models = [mock_model]
        mocker.patch(
            "backend.generation.providers.ollama_provider.ollama_list",
            return_value=mock_response,
        )
        assert generator.ensure_model_available("llama3.1:8b") is True

    def test_ensure_model_available_pulls_when_missing(self, mocker, generator):
        mock_empty_response = mocker.MagicMock()
        mock_empty_response.models = []
        mock_pull_response = mocker.MagicMock()
        mock_pull_response.status = "pulling"

        mocker.patch(
            "backend.generation.providers.ollama_provider.ollama_list",
            return_value=mock_empty_response,
        )
        mock_pull = mocker.patch(
            "backend.generation.providers.ollama_provider.pull",
            return_value=[mock_pull_response],
        )
        assert generator.ensure_model_available("llama3.1:8b") is True
        mock_pull.assert_called_once_with("llama3.1:8b", stream=True)


class TestGenerationPipeline:

    @pytest.fixture
    def pipeline(self):
        from backend.generation.pipeline import GenerationPipeline
        return GenerationPipeline()

    def test_answer_without_retriever_succeeds(self, mocker, pipeline):
        mocker.patch.object(
            pipeline.generator, "generate", return_value="Answer [Article I, Section 1]."
        )
        result = pipeline.answer("test query")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_answer_with_retriever(self, mocker):
        from backend.generation.pipeline import GenerationPipeline

        mock_retriever = mocker.MagicMock()
        mock_retriever.retrieve.return_value = [(1, 0.95), (2, 0.85)]
        mock_store = mocker.MagicMock()
        mock_store.get_chunks.return_value = [
            Chunk(id=1, text="content a", article="I", section="1"),
            Chunk(id=2, text="content b", article="II", section="2"),
        ]

        pipeline = GenerationPipeline(
            retriever=mock_retriever,
            metadata_store=mock_store,
        )
        mocker.patch.object(
            pipeline.generator,
            "generate",
            return_value="Answer [Article I, Section 1] and [Article II, Section 2].",
        )

        result = pipeline.answer("test query")
        assert "Answer" in result
        assert pipeline.last_chunks is not None
        assert len(pipeline.last_chunks) == 2

    def test_answer_pipeline_flow(self, mocker):
        from backend.generation.pipeline import GenerationPipeline

        pipeline = GenerationPipeline()
        mocker.patch.object(
            pipeline.generator,
            "generate",
            return_value="The fine is [Article I, Section 1].",
        )

        result = pipeline.answer("What is the fine?")
        assert "fine" in result
        assert pipeline.last_chunks == []

    def test_last_chunks_populated(self, mocker):
        from backend.generation.pipeline import GenerationPipeline

        mock_retriever = mocker.MagicMock()
        mock_retriever.retrieve.return_value = [(1, 0.95)]
        mock_store = mocker.MagicMock()
        mock_store.get_chunks.return_value = [
            Chunk(id=1, text="content", article="I", section="1"),
        ]

        pipeline = GenerationPipeline(
            retriever=mock_retriever,
            metadata_store=mock_store,
        )
        mocker.patch.object(
            pipeline.generator,
            "generate",
            return_value="Answer.",
        )

        pipeline.answer("q")
        assert len(pipeline.last_chunks) == 1
        assert pipeline.last_chunks[0].article == "I"
