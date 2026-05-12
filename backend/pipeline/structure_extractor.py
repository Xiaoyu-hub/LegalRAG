import re
from typing import Optional


class StructureExtractor:
    """Extract legal document structure from plain text using regex patterns.

    Per D-04: Regex-based pattern matching for legal document structure.
    Per D-05: Patterns support Article [IVX]+/\d+, Section \d+, ([a-z])/(\d+) subsections.
    Per D-06: Extracts legal term definitions via 'term' means... patterns.

    Output hierarchy elements have:
    - type: "article" | "section" | "subsection" | "body_text"
    - number/label: identifier for the element
    - text: full line text
    - parent_article: article number this element belongs to (None for articles)
    - parent_section: section number this element belongs to (None for articles/sections)
    """

    PATTERNS = {
        "article": re.compile(r"^(Article)\s+((?:[IVXLCDM]+|\d+))", re.IGNORECASE),
        "section": re.compile(r"^(Section)\s+(\d+)", re.IGNORECASE),
        "subsection_letter": re.compile(r"^\(([a-z])\)"),
        "subsection_num": re.compile(r"^\((\d+)\)"),
        "definition": re.compile(r'"([^"]+)"\s+means\s+'),
    }

    def extract(self, text: str) -> list[dict]:
        """Process text line-by-line and return hierarchy list.

        Each dict contains:
        {"type": str, "number": str|None, "label": str|None,
         "text": str, "parent_article": str|None, "parent_section": str|None}
        """
        lines = text.split("\n")
        hierarchy: list[dict] = []
        current_article: Optional[str] = None
        current_section: Optional[str] = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if m := self.PATTERNS["article"].match(stripped):
                current_article = m.group(2).strip()
                current_section = None
                hierarchy.append({
                    "type": "article",
                    "number": current_article,
                    "text": stripped,
                    "parent_article": None,
                    "parent_section": None,
                })
            elif m := self.PATTERNS["section"].match(stripped):
                current_section = m.group(2)
                hierarchy.append({
                    "type": "section",
                    "number": current_section,
                    "text": stripped,
                    "parent_article": current_article,
                    "parent_section": None,
                })
            elif current_section and (m := self.PATTERNS["subsection_letter"].match(stripped)):
                hierarchy.append({
                    "type": "subsection",
                    "label": m.group(1),
                    "number": m.group(1),
                    "text": stripped,
                    "parent_article": current_article,
                    "parent_section": current_section,
                })
            elif current_section and (m := self.PATTERNS["subsection_num"].match(stripped)):
                hierarchy.append({
                    "type": "subsection",
                    "label": m.group(1),
                    "number": m.group(1),
                    "text": stripped,
                    "parent_article": current_article,
                    "parent_section": current_section,
                })
            else:
                # Body text — attach to current section or article
                if current_section:
                    hierarchy.append({
                        "type": "body_text",
                        "text": stripped,
                        "parent_article": current_article,
                        "parent_section": current_section,
                    })
                elif current_article:
                    hierarchy.append({
                        "type": "body_text",
                        "text": stripped,
                        "parent_article": current_article,
                        "parent_section": None,
                    })

        return hierarchy

    def extract_definitions(self, text: str) -> list[dict]:
        """Find legal term definitions like 'Person' means...

        Returns list of dicts with keys: term, definition, context.
        """
        definitions: list[dict] = []
        for m in self.PATTERNS["definition"].finditer(text):
            term = m.group(1)
            start = m.end()
            end = text.find(".", start)
            end = len(text) if end == -1 else end + 1
            definition_text = text[start:end].strip()
            definitions.append({
                "term": term,
                "definition": definition_text,
                "context": text[max(0, m.start() - 80):end].strip(),
            })
        return definitions
