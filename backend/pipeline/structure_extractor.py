import re
from typing import Optional


class StructureExtractor:
    """用正则从纯文本里抽出法条结构。
    - D-04：基于正则识别结构
    - D-05：支持 Article 罗马数字/阿拉伯数字、Section 数字、(a)/(1) 形式的子项
    - D-06：识别「某术语 means …」这类定义句
    输出元素字段：
    - type: article | section | subsection | body_text
    - number/label：该元素的编号
    - text：整行原文
    - parent_article：所属条号（article 本身为 None）
    - parent_section：所属小节号（article/section 自身为 None）"""

    PATTERNS = {
        "article": re.compile(r"^(Article)\s+((?:[IVXLCDM]+|\d+))", re.IGNORECASE),
        "section": re.compile(r"^(Section)\s+(\d+)", re.IGNORECASE),
        "subsection_letter": re.compile(r"^\(([a-z])\)"),
        "subsection_num": re.compile(r"^\((\d+)\)"),
        "definition": re.compile(r'"([^"]+)"\s+means\s+'),
    }

    def extract(self, text: str) -> list[dict]:
        """逐行扫描文本，返回层级列表；每个 dict 含 type / number / label / text / parent_article / parent_section 六个字段。"""
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
                # 正文段落：挂到当前小节或当前条下
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
        """找「'Person' means …」这类术语定义，返回若干 dict，含 term、definition、context。"""
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
