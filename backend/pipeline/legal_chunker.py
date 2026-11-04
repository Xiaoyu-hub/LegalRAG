from typing import Optional

from backend.models.chunk import Chunk


class LegalChunker:
    """按法条结构分块，并保留文档层级元数据。
    - D-07：默认 by_section，切得更细，引用能精确到小节
    - D-08：另支持 by_article，可配置切换
    - D-09：完整保留层级：条、小节、子项、父级条号、标题
    - D-10：块大小目标 512–1024 token（靠条/小节边界自然切分）"""

    def __init__(self, strategy: str = "by_section"):
        if strategy not in ("by_section", "by_article"):
            raise ValueError(f"Unknown strategy: {strategy}")
        self.strategy = strategy

    def chunk(self, structure: list[dict], text: str = "") -> list[Chunk]:
        """把结构层级列表转成一批 Chunk 数据对象。"""
        if self.strategy == "by_section":
            return self._chunk_by_section(structure)
        return self._chunk_by_article(structure)

    def _chunk_by_section(self, structure: list[dict]) -> list[Chunk]:
        """每个 Section 生成一个 chunk，把它的子项与正文都装进去；同时把父级 Article 的标题带回块首，作为上下文。"""
        chunks: list[Chunk] = []
        current_section_data: Optional[dict] = None
        current_article_text: str = ""
        section_texts: list[str] = []
        chunk_index = 0

        for element in structure:
            if element["type"] == "article":
                # 进入新 Article 前必须先把上一个 Article 里最后一个 Section
                # flush 掉，否则每个 Article 的末小节会被静默丢弃
                # （实测 sample_legal.txt：10 个 Section 只落 8 个 chunk，17.4% 正文丢失）
                if current_section_data:
                    chunks.append(self._make_chunk(
                        current_section_data, section_texts, chunk_index
                    ))
                    chunk_index += 1
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
        """每个 Article 生成一个 chunk，把其下所有小节与子项都装进去。"""
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
        """用一个小节的内容组装 Chunk。"""
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
        """用一整条的内容组装 Chunk。"""
        return Chunk(
            chunk_index=chunk_index,
            text="\n".join(texts),
            article=article_element.get("number"),
            section=None,
            title=texts[0] if texts else "",
            parent_article=article_element.get("number"),
            strategy=self.strategy,
        )
