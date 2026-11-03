"""打印一次问答的 span 树，用于留证与截图。

用法（repo 根目录）：
    .venv\\Scripts\\python.exe docs\\trace_demo.py

不依赖真模型与真语料：检索/重排/生成都用桩，但埋点走的是真实代码路径。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.generation.pipeline import GenerationPipeline
from backend.generation.providers.fake import FakeProvider
from backend.models.chunk import Chunk
from backend.observability import tracing

CHUNKS = [
    Chunk(id=1, doc_id=1, chunk_index=0, text="Article I\nSection 1. Definitions.",
          article="I", section="1"),
    Chunk(id=2, doc_id=1, chunk_index=1, text="Article II\nSection 2. Obligations.",
          article="II", section="2"),
]


class StubRetriever:
    """代替 HybridSearch：真实实现会自己开 retrieval.hybrid span。"""

    def retrieve(self, query, top_k=None):
        from backend.observability import span

        with span("retrieval.hybrid", **{"tenant": "demo", "alpha": 0.7,
                                          "retrieval.n_total": len(CHUNKS)}) as sp:
            sp.set_attribute("retrieval.returned", len(CHUNKS))
        return [(c.id, 1.0) for c in CHUNKS]


class StubStore:
    def get_chunks(self, ids):
        return [c for c in CHUNKS if c.id in ids]


class StubReranker:
    """代替 cross-encoder：真实实现会自己开 retrieval.rerank span。"""

    def rerank(self, query, passages, top_k=5):
        from backend.observability import span

        with span("retrieval.rerank", **{"rerank.model": "stub", "rerank.inputs": len(passages),
                                          "rerank.top_k": top_k}) as sp:
            sp.set_attribute("rerank.returned", min(top_k, len(passages)))
        return [{"corpus_id": i, "score": 1.0 - i * 0.1, "text": p}
                for i, p in enumerate(passages[:top_k])]


def main():
    tracing.setup_tracing(exporter="memory")
    tracing.reset_for_tests()

    # 用真网关（FakeProvider 不联网）演示「检索 → 重排 → 网关调用」三段 span
    from backend.gateway import LLMGateway, MeteringStore, PricingTable, Tenant, TenantRegistry

    gateway = LLMGateway(
        providers={"fake": FakeProvider(
            reply="罚款见 [Article I, Section 1]，另见 [Article IX, Section 9]。")},
        routes={"llama3.2:3b": "fake"},
        pricing=PricingTable.load(),
        tenants=TenantRegistry.load(),
        metering=MeteringStore(db_path=os.path.join("data", "usage_demo.db")),
    )

    pipeline = GenerationPipeline(
        retriever=StubRetriever(),
        metadata_store=StubStore(),
        reranker=StubReranker(),
        gateway=gateway,
        tenant="demo",
    )
    answer = pipeline.answer("罚款上限是多少？")
    print("answer:", answer)

    spans = tracing.get_finished_spans()
    by_id = {s.context.span_id: s for s in spans}
    root = [s for s in spans if s.parent is None]

    def dump(sp, depth=0):
        dur = (sp.end_time - sp.start_time) / 1e6
        attrs = " ".join(f"{k}={v}" for k, v in sorted(sp.attributes.items()))
        print(f"{'  ' * depth}- {sp.name}  {dur:.2f}ms  [{attrs}]")
        for child in spans:
            if child.parent is not None and child.parent.span_id == sp.context.span_id:
                dump(child, depth + 1)

    print("\n=== span 树 ===")
    for sp in root:
        dump(sp)
    print(f"\n共 {len(spans)} 个 span")


if __name__ == "__main__":
    main()
