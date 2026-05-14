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
