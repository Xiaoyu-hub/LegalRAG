import logging

from backend.generation.citation_builder import CitationBuilder
from backend.generation.generator import Generator
from backend.generation.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class GenerationPipeline:

    def __init__(
        self,
        retriever=None,
        metadata_store=None,
        model: str = "llama3.1:8b",
        fallback: str = "qwen2.5:7b",
    ):
        self.retriever = retriever
        self.metadata_store = metadata_store
        self.prompt_builder = PromptBuilder()
        self.generator = Generator(model=model, fallback=fallback)
        self.citation_builder = CitationBuilder()
        self.last_chunks = []

    def answer(self, query: str) -> str:
        chunks = []

        if self.retriever is not None and self.metadata_store is not None:
            results = self.retriever.retrieve(query, top_k=5)
            if results:
                chunk_ids = [r[0] for r in results] if isinstance(results[0], tuple) else results
                chunks = self.metadata_store.get_chunks(chunk_ids)

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

    def answer_stream(self, query: str):
        """Stream answer tokens, then yield source data."""
        chunks = []
        if self.retriever is not None and self.metadata_store is not None:
            results = self.retriever.retrieve(query, top_k=5)
            if results:
                chunk_ids = [r[0] for r in results] if isinstance(results[0], tuple) else results
                chunks = self.metadata_store.get_chunks(chunk_ids)
        self.last_chunks = chunks

        system_prompt, user_prompt = self.prompt_builder.build(query, chunks)
        for token in self.generator.generate_stream(system_prompt, user_prompt):
            yield token
