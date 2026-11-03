from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Document:
    id: int = 0
    filename: str = ""
    title: str = ""
    page_count: int = 0
    file_path: str = ""
    file_size: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    tenant: str = "demo"
