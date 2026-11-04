import logging
import re
from typing import Optional

from backend.models.citation import Citation

logger = logging.getLogger(__name__)

# 匹配 [Article X, Section Y]，也兼容只写条号 [Article X]
CITATION_PATTERN = re.compile(
    r"\[(Article)\s+((?:[IVXLCDM]+|\d+))"
    r"(?:,\s*Section\s+(\d+(?:\([a-z]\))?))?"
    r"\]",
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
                    section=match.group(3) or "",
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
            if article:
                article_clean = article.replace("Article ", "").strip()
                section_clean = section.replace("Section ", "").strip()
                valid_pairs.add((article_clean, section_clean))

        for citation in citations:
            # 第一层：精确匹配（条号 + 小节号成对相同）
            if (citation.article, citation.section) in valid_pairs:
                citation.valid = True
                continue

            # 第二层：宽松匹配——引用文本作为子串出现在片段元数据里
            citation.valid = self._partial_match(citation, chunks)

        return citations

    def _partial_match(self, citation: Citation, chunks: list) -> bool:
        """检查引用文本是否出现在某个片段的元数据里（宽松匹配）。"""
        citation_lower = citation.text.lower()
        for chunk in chunks:
            chunk_meta = " ".join(filter(None, [
                chunk.article or "",
                chunk.section or "",
                chunk.title or "",
            ]))
            if citation_lower in chunk_meta.lower():
                return True
        return False

    def mark_invalid(self, text: str, citations: list[Citation]) -> str:
        result = text
        for citation in citations:
            if not citation.valid:
                result = result.replace(
                    citation.text, "[Citation needs verification]", 1
                )
        return result

    def process(
        self, text: str, chunks: list
    ) -> tuple[str, list[Citation]]:
        citations = self.extract(text)
        citations = self.validate(citations, chunks)
        cleaned_text = self.mark_invalid(text, citations)
        return cleaned_text, citations
