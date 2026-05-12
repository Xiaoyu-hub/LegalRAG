from typing import Optional

from backend.models.chunk import Chunk


class LegalChunker:
    """Create legal-aware chunks preserving document hierarchy metadata.

    Per D-07: Default strategy is 'by_section' for granular citation accuracy.
    Per D-08: 'by_article' strategy supported as configurable alternative.
    Per D-09: Full hierarchy preserved: article, section, subsection, parent_article, title.
    Per D-10: Chunk size target 512-1024 tokens (via section/article boundaries).
    """

    def __init__(self, strategy: str = "by_section"):
        if strategy not in ("by_section", "by_article"):
            raise ValueError(f"Unknown strategy: {strategy}")
        self.strategy = strategy

    def chunk(self, structure: list[dict], text: str = "") -> list[Chunk]:
        """Convert structure hierarchy into a list of Chunk dataclass instances."""
        if self.strategy == "by_section":
            return self._chunk_by_section(structure)
        return self._chunk_by_article(structure)

    def _chunk_by_section(self, structure: list[dict]) -> list[Chunk]:
        """Each Section becomes a chunk with its subsections and body text.

        The parent article's heading text is included as context at the start
        of each section's content.
        """
        chunks: list[Chunk] = []
        current_section_data: Optional[dict] = None
        current_article_text: str = ""
        section_texts: list[str] = []
        chunk_index = 0

        for element in structure:
            if element["type"] == "article":
                current_article_text = element["text"]
                current_section_data = None
                section_texts = []
            elif element["type"] == "section":
                if current_section_data:
                    chunks.append(self._make_chunk(
                        current_section_data, section_texts, chunk_index
                    ))
                    chunk_index += 1
                current_section_data = element
                section_texts = (
                    [current_article_text, element["text"]]
                    if current_article_text
                    else [element["text"]]
                )
            elif element["type"] in ("subsection", "body_text"):
                if current_section_data:
                    section_texts.append(element["text"])
            else:
                if current_section_data:
                    section_texts.append(element.get("text", ""))

        if current_section_data:
            chunks.append(self._make_chunk(
                current_section_data, section_texts, chunk_index
            ))

        return chunks

    def _chunk_by_article(self, structure: list[dict]) -> list[Chunk]:
        """Each Article becomes a chunk with all its sections and subsections."""
        chunks: list[Chunk] = []
        current_article_data: Optional[dict] = None
        article_texts: list[str] = []
        chunk_index = 0

        for element in structure:
            if element["type"] == "article":
                if current_article_data:
                    chunks.append(self._make_article_chunk(
                        current_article_data, article_texts, chunk_index
                    ))
                    chunk_index += 1
                current_article_data = element
                article_texts = [element["text"]]
            elif element["type"] in ("section", "subsection", "body_text"):
                if current_article_data:
                    article_texts.append(element["text"])

        if current_article_data:
            chunks.append(self._make_article_chunk(
                current_article_data, article_texts, chunk_index
            ))

        return chunks

    def _make_chunk(self, section_element: dict, texts: list[str],
                    chunk_index: int) -> Chunk:
        """Build a Chunk from a section's worth of content."""
        return Chunk(
            chunk_index=chunk_index,
            text="\n".join(texts),
            article=section_element.get("parent_article"),
            section=section_element.get("number"),
            title=texts[0] if texts else "",
            parent_article=section_element.get("parent_article"),
            strategy=self.strategy,
        )

    def _make_article_chunk(self, article_element: dict, texts: list[str],
                            chunk_index: int) -> Chunk:
        """Build a Chunk from an article's worth of content."""
        return Chunk(
            chunk_index=chunk_index,
            text="\n".join(texts),
            article=article_element.get("number"),
            section=None,
            title=texts[0] if texts else "",
            parent_article=article_element.get("number"),
            strategy=self.strategy,
        )
