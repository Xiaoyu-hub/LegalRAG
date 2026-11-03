# LegalRAG — 多租户 RAG 服务 + LLM 网关

A Retrieval-Augmented Generation service for English legal documents, plus a multi-tenant LLM gateway.
Upload PDFs and ask questions — answers carry inline citations down to Article / Section.

> 2026-11 定位升级：从「单租户法律文书问答」变成「多租户 RAG 服务 + LLM 网关」。
> 新增：租户隔离（元数据 / 向量 / 关键词）、
> LLM 网关（多后端路由、主备降级、配额、token 计量与成本归因）、
> Prometheus 指标与 OpenTelemetry span、FAISS 与 pgvector 双后端。

## 自检与 CI

```bash
python -m pytest tests -q          # 199 个单测与契约测试
python docs/e2e_check.py           # 端到端：上传 → 索引 → 检索 → 问答 → 重启一致（22 项断言）
python docs/trace_demo.py          # 打印一次问答的 span 树
python docs/loadtest.py            # 并发压测，出「并发 vs P99」表（需先起服务）
```

GitHub Actions（`.github/workflows/ci.yml`）跑同样的三步：单测 → 端到端自检 →
带 pgvector 服务容器的契约测试。生成段用 `LLM_PROVIDER=fake`，不依赖真模型服务。

## Architecture

- **FastAPI backend** with document processing, hybrid search (BM25 + Vector), and LLM-based Q&A
- **Streamlit frontend** with document upload, chat interface, and structure preview
- **Ollama** for local LLM inference (privacy-preserving, no cloud APIs)
- **FAISS** for vector storage, **SQLite** for metadata

## Quick Start

### Prerequisites

- Docker and Docker Compose (recommended)
- OR Python 3.11+ and Ollama (for local development)

### Docker Deployment (Recommended)

```bash
git clone <repo-url>
cd legalrag
docker-compose up
```

Then access the frontend at http://localhost:8501

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
pip install streamlit
```

2. Ensure Ollama is running:
```bash
ollama serve
```

3. Pull an LLM model:
```bash
ollama pull llama3.1:8b
```

4. Start the backend:
```bash
uvicorn backend.main:app --reload --port 8000
```

5. Start the frontend:
```bash
streamlit run app/main.py --server.port=8501
```

## Usage

1. **Upload** a PDF legal document via the Documents page
2. **Wait** for indexing to complete (status badge: amber → green)
3. **Select** the document from the sidebar
4. **Ask** questions in the Chat page
5. **View** retrieved sources under each answer
6. **Preview** document structure in the Preview page

Screenshots coming soon.

## Project Structure

```
legalrag/
├── app/                          # Streamlit frontend
│   ├── main.py                   # Entry point with sidebar navigation
│   ├── pages/
│   │   ├── 1_Documents.py        # Document upload & management
│   │   ├── 2_Chat.py             # Q&A interface with citations
│   │   └── 3_Preview.py          # Document structure preview
│   └── components/
│       ├── citation_box.py       # Citation rendering utilities
│       └── doc_preview.py        # Document tree builder
├── backend/                      # FastAPI backend
│   ├── main.py                   # FastAPI entry point
│   ├── api/
│   │   ├── documents.py          # Document upload/list/status/chunks API
│   │   ├── chat.py               # Streaming chat API
│   │   └── search.py             # Hybrid search API
│   ├── pipeline/                 # Document processing pipeline
│   ├── retrieval/                # BM25, vector, hybrid search
│   ├── generation/               # LLM generation & citations
│   └── models/                   # Data models
├── configs/                      # Configuration files
├── data/                         # Document storage & FAISS index
├── tests/                        # Test suite
├── Dockerfile                    # Multi-stage build
└── docker-compose.yml            # One-command deployment
```

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Streamlit | Rapid Python-native UI |
| Backend API | FastAPI | Async REST endpoints |
| PDF Parsing | PyMuPDF + pdfplumber | Text and table extraction |
| Embeddings | BGE-large-en-v1.5 | English legal document vectors |
| Vector Store | FAISS | Local vector search |
| BM25 | rank_bm25 | Keyword search |
| Reranking | Cross-Encoder (ms-marco) | Search result re-ranking |
| LLM | Ollama (Qwen2.5 / Llama3) | Local LLM inference |
| Metadata | SQLite | Document and chunk storage |
| Deployment | Docker | Containerized deployment |

## License

MIT
