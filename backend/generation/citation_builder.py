import logging
import re
from typing import Optional

from backend.models.citation import Citation

logger = logging.getLogger(__name__)

CITATION_PATTERN = re.compile(
    r"\[(Article)\s+((?:[IVXLCDM]+|\d+)),\s*Section\s+(\d+(?:\([a-z]\))?)\]",
    re.IGNORECASE,
)


class CitationBuilder:

    def extract(self, text: str) -> list[Citation]:
        if not text:
            return []

        citations = []
        for match in CITATION_PATTERN.finditer(text):
            citations.append(
                Citation(
                    text=match.group(0),
                    article=match.group(2),
                    section=match.group(3),
                )
            )
        return citations

    def validate(
        self, citations: list[Citation], chunks: list
    ) -> list[Citation]:
        valid_pairs = set()
        for chunk in chunks:
            article = chunk.article or ""
            section = chunk.section or ""
            if article and section:
                article_clean = article.replace("Article ", "").strip()
                section_clean = section.replace("Section ", "").strip()
                valid_pairs.add((article_clean, section_clean))

        for citation in citations:
            citation.valid = (
                citation.article,
                citation.section,
            ) in valid_pairs

        return citations

    def mark_invalid(self, text: str, citations: list[Citation]) -> str:
        result = text
        for citation in citations:
            if not citation.valid:
                result = result.replace(
                    citation.text, "[引用待核实]", 1
                )
        return result

    def process(
        self, text: str, chunks: list
    ) -> tuple[str, list[Citation]]:
        citations = self.extract(text)
        citations = self.validate(citations, chunks)
        cleaned_text = self.mark_invalid(text, citations)
        return cleaned_text, citations
