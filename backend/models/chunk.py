from dataclasses import dataclass
from typing import Optional


@dataclass
class Chunk:
    id: int = 0
    doc_id: int = 0
    chunk_index: int = 0
    text: str = ""
    article: Optional[str] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    title: str = ""
    parent_article: Optional[str] = None
    strategy: str = "by_section"
