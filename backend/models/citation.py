from dataclasses import dataclass
from typing import Optional


@dataclass
class Citation:
    text: str
    article: str
    section: str
    subsection: Optional[str] = None
    valid: bool = True
    confidence: float = 1.0
