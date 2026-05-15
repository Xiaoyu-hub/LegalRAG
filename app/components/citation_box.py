import re


def extract_citations(text: str) -> list[dict]:
    pattern = r'\[(Article\s+[^,]+),\s*(Section\s+[^\]]+)\]'
    matches = re.findall(pattern, text)
    return [{"article": m[0], "section": m[1]} for m in matches]


def render_citation_marker(article: str, section: str) -> str:
    return f'**[{article}, {section}]({article})**'


def render_sources_expander(sources: list[dict]) -> str:
    parts = []
    for s in sources:
        article = s.get("article", "N/A")
        section = s.get("section", "")
        text = s.get("text", "")[:300]
        parts.append(f"**{article}** — {section}\n\n{text}\n\n---")
    return "\n\n".join(parts)
