"""抽取式回答后端：没有 LLM 时也能把整条链路跑通的确定性基线。

为什么要有它：
- 本机 / CI 常常没有 Ollama（没有 GPU、镜像拉不下来、模型 1.3GB 起），
  而 `fake` 后端只会回一句 "fake answer"，既没有引用也验证不了引用校验；
- 抽取式基线拿到的是和真模型一模一样的 prompt（已按 token 预算裁好的
  `<chunk article=... section=...>` 上下文），它按词面重叠挑句子并带上
  `[Article X, Section Y]` 引用 ⇒ 检索、重排、引用校验、计量、流式出口全部被真实执行。

它**不是** LLM，答不出「需要推理」的问题，只做段落抽取。定位是「降级基线 +
引用链路的对照组」，README 与前端都这么标注，不当成模型能力宣传。

用法：`LLM_PROVIDER=extractive`
"""
import math
import os
import re
from typing import Iterator

from backend.generation.providers.base import ProviderResponse
from backend.generation.tokens import count_tokens

# PromptBuilder 组装的上下文格式（见 backend/generation/prompt_builder.py）
CHUNK_RE = re.compile(
    r'<chunk id="(\d+)" article="([^"]*)" section="([^"]*)">\n(.*?)\n</chunk>',
    re.DOTALL,
)
QUESTION_RE = re.compile(r"##\s*Question\s*\n+(.*?)(?=\n##\s|\Z)", re.DOTALL)
# 句子切分：句末标点后跟空白，或换行；法律条文里 "(a) ..." 这类子项独立成句
SENTENCE_RE = re.compile(r"[^.\n]+[.]|[^.\n]+")
# 结构行（Article II. Enforcement / Section 3. Administrative Penalties）不算正文句子
HEADING_RE = re.compile(r"^(Article|Section)\s+([IVXLCDM]+|\d+)\b", re.IGNORECASE)

STOPWORDS = frozenset("""
a an the and or but if then than that this these those of in on at to for from by with
without into over under about as is are was were be been being do does did done have has
had having will would shall should may might must can could not no nor so such it its
i you he she they we them his her their our your what which who whom whose when where why
how all any both each few more most other some only own same too very there here also
""".split())

DEFAULT_MAX_SENTENCES = 3
# 比最高分低太多的句子直接扔掉：纯按词面重叠挑句子时，总会有几句
# 只是因为「共享了一个泛词」而被打分，拼进来反而稀释答案。
RELATIVE_CUTOFF = 0.45
MAX_ANSWER_CHARS = 900


class ExtractiveProvider:
    """按与问题的词面重叠度抽取原文句子，并附上所在条文引用。"""

    name = "extractive"

    def __init__(self, model: str = "extractive-baseline",
                 max_sentences: int | None = None):
        self.model = model
        self.max_sentences = max_sentences or int(
            os.getenv("EXTRACTIVE_MAX_SENTENCES", DEFAULT_MAX_SENTENCES)
        )

    # ── Provider 协议 ──

    def generate(self, system_prompt: str, user_prompt: str) -> ProviderResponse:
        content = self.compose(user_prompt)
        return ProviderResponse(
            content=content,
            model=self.model,
            prompt_tokens=count_tokens(system_prompt) + count_tokens(user_prompt),
            completion_tokens=count_tokens(content),
            latency=0.0,
        )

    def stream(self, system_prompt: str, user_prompt: str) -> Iterator[str]:
        """按句切片输出，让前端能看出「流式」而不是等整段。

        按句而不是按字符 yield：字符级切片在本地几毫秒就发完，前端只会看到
        一次性刷新，反而掩盖了 SSE / 流式读的 bug。
        """
        content = self.compose(user_prompt)
        for piece in re.findall(r"[^\n]*\n|[^\n]+", content):
            if piece:
                yield piece

    def ensure_available(self, model: str) -> bool:
        # 纯本地计算，永远可用
        return True

    # ── 核心：从上下文里抽句子 ──

    def compose(self, user_prompt: str) -> str:
        chunks = self._parse_chunks(user_prompt)
        question = self._parse_question(user_prompt)

        if not chunks:
            return ("No context documents were retrieved for this question. "
                    "Upload a document first, then ask again.")

        terms = self._content_terms(question)
        if not terms:
            # 抽取式基线只会做英文词面匹配：中文问题在这里就会被拦下，
            # 与其返回一句无意义的答案，不如把原因和两边选项说清楚。
            return ("This baseline matches English words literally, so the question needs "
                    "at least one English keyword. Ask in English, or switch to a real model "
                    "(LLM_PROVIDER=ollama) for multilingual answers.")

        df = self._document_frequencies(chunks, terms)
        scored: list[tuple[float, str, str]] = []
        for chunk in chunks:
            label = self._citation_label(chunk["article"], chunk["section"])
            for sentence in self._split_sentences(chunk["text"]):
                score = self._score(sentence, terms, df, len(chunks))
                if score > 0:
                    scored.append((score, sentence, label))

        if not scored:
            return ("The retrieved sections do not mention "
                    f"{', '.join(sorted(terms)[:6])}. "
                    "Try other wording, or upload a document that covers it.")

        # 高分在前，同一支部条文只留最相关的一句（避免答案变成复制粘贴）
        scored.sort(key=lambda item: item[0], reverse=True)
        best = scored[0][0]
        picked: list[tuple[float, str, str]] = []
        seen_labels: set[str] = set()
        seen_sentences: set[str] = set()
        for score, sentence, label in scored:
            if score < best * RELATIVE_CUTOFF:
                continue
            key = sentence.lower().strip()
            if key in seen_sentences:
                continue
            if label and label in seen_labels:
                continue
            picked.append((score, sentence, label))
            seen_sentences.add(key)
            if label:
                seen_labels.add(label)
            if len(picked) >= self.max_sentences:
                break

        lines = ["Based on the provided documents:", ""]
        for _, sentence, label in picked:
            text = sentence.strip()
            lines.append(f"{text} {label}".strip())
        answer = "\n".join(lines)
        return answer[:MAX_ANSWER_CHARS]

    # ── 解析 ──

    def _parse_chunks(self, user_prompt: str) -> list[dict]:
        return [
            {"id": int(m.group(1)), "article": m.group(2).strip(),
             "section": m.group(3).strip(), "text": m.group(4)}
            for m in CHUNK_RE.finditer(user_prompt or "")
        ]

    def _parse_question(self, user_prompt: str) -> str:
        m = QUESTION_RE.search(user_prompt or "")
        if m:
            return m.group(1).strip()
        # 模板被改过时退化成「最后一段非空文本」，总比拿整段上下文当问题好
        tail = [p for p in (user_prompt or "").split("\n\n") if p.strip()]
        return tail[-1].strip() if tail else ""

    # ── 打分 ──

    def _content_terms(self, text: str) -> set[str]:
        words = re.findall(r"[a-z0-9]+", (text or "").lower())
        return {w for w in words if w not in STOPWORDS and len(w) > 2}

    def _document_frequencies(self, chunks: list[dict], terms: set[str]) -> dict[str, float]:
        """逆文档频率：一个词在多少条文里出现。

        没有 idf 的话 "documents"、"shall" 这类高频词会把分数拉满，
        抽出来的是最泛的句子而不是最相关的那句。
        """
        df = {t: 0.0 for t in terms}
        for chunk in chunks:
            text = chunk["text"].lower()
            for term in terms:
                if term in text:
                    df[term] += 1.0
        return df

    def _score(self, sentence: str, terms: set[str], df: dict[str, float],
               n_chunks: int) -> float:
        words = re.findall(r"[a-z0-9]+", sentence.lower())
        if not words:
            return 0.0
        word_set = set(words)
        total = 0.0
        matched = 0
        for term in terms:
            if term in word_set:
                total += 1.0 + math.log(max(n_chunks, 1) / max(df.get(term, 1.0), 1.0))
                matched += 1
        if matched == 0:
            return 0.0
        # 长度归一：长句天然命中更多词，不归一化会只挑最长的段落
        return total / math.sqrt(len(words))

    def _split_sentences(self, text: str) -> list[str]:
        """切句，并扔掉条文里的结构行。

        chunk 的正文开头带着 `Article II. Enforcement` / `Section 3. Administrative
        Penalties` 这类标题行：它们字少且几乎全是问题里的关键词，不排掉就会
        永远排第一，答案变成把标题抄一遍。出处信息本身已经由引用标记给出。
        """
        sentences = []
        for line in (text or "").split("\n"):
            if HEADING_RE.match(line.strip()):
                continue
            for m in SENTENCE_RE.finditer(line):
                piece = m.group(0).strip()
                if len(piece) > 12:
                    sentences.append(piece)
        return sentences

    def _citation_label(self, article: str, section: str) -> str:
        """生成 `[Article I, Section 1]`。

        引用格式必须和 CitationBuilder.CITATION_PATTERN 完全一致，否则
        「引用校验」会把我们自己的答案标成无效——这里只按能匹配的形态拼，
        拼不出来就留空（宁可不标，也不标一个假引用）。
        """
        art = (article or "").replace("Article", "").strip()
        sec = (section or "").replace("Section", "").strip()
        if art and re.fullmatch(r"[IVXLCDM]+|\d+", art, re.IGNORECASE):
            if sec and re.fullmatch(r"\d+(\([a-z]\))?", sec):
                return f"[Article {art}, Section {sec}]"
            return f"[Article {art}]"
        return ""
