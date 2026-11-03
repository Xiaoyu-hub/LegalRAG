import logging

from backend.generation.citation_builder import CitationBuilder
from backend.generation.generator import (
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_MODEL,
    NUM_CTX,
    NUM_PREDICT,
)
from backend.generation.generator import Generator
from backend.generation.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class GenerationPipeline:

    def __init__(
        self,
        retriever=None,
        metadata_store=None,
        model: str = DEFAULT_MODEL,
        fallback: str = DEFAULT_FALLBACK_MODEL,
        reranker=None,
        recall_k: int = 10,
        rerank_top_k: int = 5,
    ):
        self.retriever = retriever
        self.metadata_store = metadata_store
        self.prompt_builder = PromptBuilder(max_tokens=NUM_CTX - NUM_PREDICT)
        self.generator = Generator(model=model, fallback=fallback)
        self.citation_builder = CitationBuilder()
        self.last_chunks = []
        # 重排阶段：召回 10 → cross-encoder 重排 → 留 5（D-18 / D-17）
        # 旧版这里根本没接 Reranker，重排只存在于测试和文档里。
        self.reranker = reranker
        self.recall_k = recall_k
        self.rerank_top_k = rerank_top_k
        self.last_reranked = []

    def _retrieve(self, query: str, document_id: int | None = None):
        """召回 → 取元数据 → 重排。返回送给 prompt 的最终 chunk 列表。"""
        if self.retriever is None or self.metadata_store is None:
            return []

        results = self.retriever.retrieve(query, top_k=self.recall_k)
        if not results:
            return []
        chunk_ids = [r[0] for r in results] if isinstance(results[0], tuple) else results
        chunks = self.metadata_store.get_chunks(chunk_ids)
        if document_id is not None:
            chunks = [c for c in chunks if c.doc_id == document_id]

        if self.reranker is not None and chunks:
            reranked = self.reranker.rerank(
                query, [c.text for c in chunks], top_k=self.rerank_top_k
            )
            self.last_reranked = reranked
            chunks = [chunks[r["corpus_id"]] for r in reranked]
        else:
            self.last_reranked = []
            chunks = chunks[: self.rerank_top_k]
        return chunks

    def answer(self, query: str, document_id: int | None = None) -> str:
        chunks = self._retrieve(query, document_id)
        self.last_chunks = chunks

        system_prompt, user_prompt = self.prompt_builder.build(query, chunks)
        raw_text = self.generator.generate(system_prompt, user_prompt)
        cleaned_text, citations = self.citation_builder.process(
            raw_text, chunks
        )

        logger.info(
            "Generated answer with %d citations (%d valid)",
            len(citations),
            sum(1 for c in citations if c.valid),
        )
        return cleaned_text

    def answer_stream(self, query: str, document_id: int | None = None):
        """流式输出。流内不改字，但流结束后仍要跑一次引用校验。

        旧版这里直接 yield token 就结束，`citation_builder.process` 从未执行；
        而 `/api/v1/chat` 用的正是这条路径 ⇒ 对外接口的答案零校验。
        现在把校验结果存在 self.last_citations，由调用方在流末尾推给前端。
        """
        chunks = self._retrieve(query, document_id)
        self.last_chunks = chunks

        system_prompt, user_prompt = self.prompt_builder.build(query, chunks)
        buffer: list[str] = []
        for token in self.generator.generate_stream(system_prompt, user_prompt):
            buffer.append(token)
            yield token

        _, citations = self.citation_builder.process("".join(buffer), chunks)
        self.last_citations = citations
        logger.info(
            "Stream finished with %d citations (%d valid)",
            len(citations),
            sum(1 for c in citations if c.valid),
        )
