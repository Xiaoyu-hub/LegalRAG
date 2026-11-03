"""FastAPI application entry point for LegalRAG.

Per CONTEXT.md D-01~D-08:
  - D-01: Routes organized by resource (documents router registered here).
  - D-02: Engine instances as app.state singletons.
  - D-03: API prefix /api/v1.
  - D-04: Global exception handlers.
  - D-05: Async document indexing via BackgroundTasks.
  - D-06: Unified response wrapper.
  - D-07: Health check endpoint.
  - D-08: CORS permissive in development.
"""
import logging
import os
import sqlite3

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.chat import router as chat_router
from backend.api.documents import router as documents_router
from backend.api.gateway import router as gateway_router
from backend.api.search import router as search_router

logger = logging.getLogger(__name__)

# uvicorn 只配置自己的 logger，应用侧的 logger.info 默认被 root 的 WARNING 静默吞掉：
# 不显式配置的话，启动日志（加载索引、映射校验、重建）在控制台一行都看不到。
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger("backend").setLevel(logging.INFO)

# ── App Factory ────────────────────────────────────────────────────────────

app = FastAPI(
    title="LegalRAG API",
    version="1.0.0",
    description="Backend API for LegalRAG — Legal Document Q&A System",
)

# ── CORS (D-08) ────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Unified Error Response ─────────────────────────────────────────────────


def _error_response(status_code: int, detail: str) -> JSONResponse:
    """Return a unified error response per D-06."""
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "data": None, "error": detail},
    )


# ── Exception Handlers (D-04) ──────────────────────────────────────────────


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return unified error response."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return _error_response(500, f"Internal server error: {exc}")


# ── Lifecycle Events ───────────────────────────────────────────────────────


@app.on_event("startup")
async def startup():
    """Initialise app-level singletons (D-02, D-05)."""
    from backend.storage.metadata_store import MetadataStore
    from backend.pipeline.indexer import Indexer
    from backend.retrieval.vector_search import VectorSearch
    from backend.retrieval.bm25 import BM25Retriever

    logger.info("Starting LegalRAG API — initialising singletons")

    # Engine singletons
    app.state.metadata_store = MetadataStore()
    # 按租户建 Indexer：每个租户一套向量索引 + BM25，文件目录也分开
    app.state.indexers = {}

    def _indexer_for(tenant: str):
        if tenant not in app.state.indexers:
            app.state.indexers[tenant] = Indexer(tenant=tenant)
        return app.state.indexers[tenant]

    app.get_indexer = _indexer_for  # 便于路由层按租户取
    app.state.indexer = _indexer_for("demo")  # 向后兼容旧调用

    # 按租户恢复索引：每个租户一个目录 data/index/<tenant>/vector.faiss
    try:
        tenants = app.state.metadata_store.list_tenants() or ["demo"]
    except Exception as exc:
        logger.warning("Could not list tenants: %s", exc)
        tenants = ["demo"]

    for tenant in tenants:
        ix = _indexer_for(tenant)
        vs_t = ix.vector_search
        expected_ids = app.state.metadata_store.get_all_chunk_ids(tenant)
        index_file = ix.index_path

        if os.path.exists(index_file):
            try:
                vs_t.load(index_file)
                logger.info("[%s] Loaded FAISS index from %s (%d vectors)",
                            tenant, index_file, vs_t.size)
                # 启动校验：索引里的 position→chunk_id 映射必须与数据库 id 集合一致。
                if not vs_t.mapping_matches(expected_ids):
                    logger.warning(
                        "index_manifest_mismatch: tenant=%s faiss=%d vectors, db=%d chunks,"
                        " mapping_trusted=%s — rebuilding from SQLite",
                        tenant, vs_t.size, len(expected_ids), vs_t.mapping_trusted,
                    )
                    n = ix.rebuild_all()
                    logger.info("[%s] Rebuilt FAISS index with %d chunks", tenant, n)
            except Exception as exc:
                logger.warning("[%s] Could not load FAISS index: %s", tenant, exc)
        elif expected_ids:
            # 旧版索引在 data/index/vector.faiss，新版按租户分目录；首启重建一次
            n = ix.rebuild_all()
            logger.info("[%s] No index file, rebuilt %d chunks", tenant, n)

        # BM25 按租户重建
        try:
            chunks_t = app.state.metadata_store.get_all_chunks(tenant)
            if chunks_t:
                ix.bm25.build_index([c.text for c in chunks_t], [c.id for c in chunks_t])
                logger.info("[%s] Rebuilt BM25 index with %d chunks", tenant, len(chunks_t))
        except Exception as exc:
            logger.warning("[%s] Could not rebuild BM25: %s", tenant, exc)

    # Per-document async processing status (D-05)
    app.state.processing_status = {}
    # Mark documents that already have chunks as "ready"
    try:
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(app.state.metadata_store.db_path)
        c = conn.cursor()
        c.execute("SELECT id FROM documents")
        doc_ids = [row[0] for row in c.fetchall()]
        conn.close()
        for doc_id in doc_ids:
            chunks = app.state.metadata_store.get_chunks_by_doc_id(doc_id)
            if chunks:
                app.state.processing_status[doc_id] = "ready"
        if doc_ids:
            ready_count = sum(1 for d in doc_ids if d in app.state.processing_status)
            logger.info("Restored processing status: %d/%d documents ready", ready_count, len(doc_ids))
    except Exception as exc:
        logger.warning("Could not restore document statuses: %s", exc)

    # Citation retrieval buffer for Plan 2 (chat endpoint) —— 按会话 id 分槽
    app.state.last_chat_sources = {}
    app.state.last_chat_citations = {}

    # 重排器：启动时不加载模型（90MB + 几秒），首次用到再懒加载
    app.state.reranker = None
    try:
        from backend.retrieval.reranker import Reranker
        app.state.reranker = Reranker.get_instance()
        logger.info("Reranker ready: %s", app.state.reranker.model_name)
    except Exception as exc:
        logger.warning("Reranker unavailable, serving hybrid order only: %s", exc)

    # ── LLM 网关（多租户 / 配额 / 计量 / 降级）──
    # 启动时构造：price 表与租户配置都从 configs/ 读，改 YAML 重启即生效
    try:
        from backend.gateway import LLMGateway, MeteringStore, PricingTable, TenantRegistry
        from backend.generation.providers import build_provider

        model = __import__("os").getenv("LLM_MODEL", "llama3.2:3b")
        fallback = __import__("os").getenv("LLM_FALLBACK_MODEL", "llama3.1:8b")
        kind = __import__("os").getenv("LLM_PROVIDER", "ollama")
        # 当前默认只有 ollama 一个后端；配 LLM_PROVIDER=fake 可在无模型环境下
        # 跑通网关链路（配额 / 计量 / 降级都能验）；接云 API 时在这里加 provider 与 routes
        providers = {kind: build_provider(kind, model=model, fallback=fallback)}
        routes = {model: kind, fallback: kind}

        app.state.gateway = LLMGateway(
            providers=providers,
            routes=routes,
            pricing=PricingTable.load(),
            tenants=TenantRegistry.load(),
            metering=MeteringStore(),
        )
        logger.info("LLM gateway ready: providers=%s routes=%s",
                    list(providers), routes)
    except Exception as exc:
        app.state.gateway = None
        logger.warning("LLM gateway unavailable: %s", exc)

    logger.info("LegalRAG API startup complete")


@app.on_event("shutdown")
async def shutdown():
    """Log shutdown event."""
    logger.info("LegalRAG API shutting down")


# ── Routes (D-03) ──────────────────────────────────────────────────────────

app.include_router(documents_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(gateway_router, prefix="/api/v1")


# ── Health Endpoint (D-07) ─────────────────────────────────────────────────


# ── Prometheus 指标出口（D-07 之外单独一个路径，方便 scrape 配置）──


@app.get("/metrics")
async def metrics():
    """暴露 Prometheus 指标。不带 /api/v1 前缀：Prometheus 默认就这么配。"""
    from fastapi.responses import Response

    from backend.observability import render

    return Response(content=render(), media_type="text/plain; version=0.0.4")


@app.get("/api/v1/health")
async def health(request: Request):
    """Check system health: Ollama, SQLite, FAISS, BM25, Embedder."""
    # --- SQLite ---
    try:
        conn = sqlite3.connect(request.app.state.metadata_store.db_path)
        conn.execute("SELECT 1")
        conn.close()
        sqlite_status = "ok"
    except Exception:
        sqlite_status = "error"

    # --- FAISS / BM25（按租户汇总：全部租户都有索引才算 ok）---
    from backend.retrieval.vector_search import VectorSearch
    from backend.retrieval.bm25 import BM25Retriever
    try:
        indexers = getattr(request.app.state, "indexers", {}) or {"demo": None}
        tenants = list(indexers) or ["demo"]
        vs_ok = all(VectorSearch.get_instance(tenant=t).size > 0 for t in tenants)
        bm_ok = all(
            (lambda b: b.bm25 is not None and len(b.corpus) > 0)(BM25Retriever.get_instance(t))
            for t in tenants
        )
        faiss_status = "ok" if vs_ok else "error"
        bm25_status = "ok" if bm_ok else "error"
        faiss_tenants = {t: VectorSearch.get_instance(tenant=t).size for t in tenants}
    except Exception:
        faiss_status = bm25_status = "error"
        faiss_tenants = {}

    # --- Ollama ---
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            ollama_status = "ok" if resp.status_code == 200 else "error"
    except Exception:
        ollama_status = "error"

    # --- BM25 ---

    # --- Embedder ---
    from backend.embedding.embedder import Embedder
    try:
        embedder = Embedder.get_instance()
        embedder.model.encode(["health check"], batch_size=1)
        embedder_status = "ok"
    except Exception:
        embedder_status = "error"

    return {
        "status": "ok",
        "data": {
            "ollama": ollama_status,
            "sqlite": sqlite_status,
            "faiss": faiss_status,
            "faiss_vectors": faiss_tenants,
            "bm25": bm25_status,
            "embedder": embedder_status,
        },
        "error": None,
    }
