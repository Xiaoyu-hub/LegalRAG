# LegalRAG — Legal Document Q&A System

LegalRAG is a Retrieval-Augmented Generation system for English legal documents. Upload PDF legal documents and ask natural language questions — answers include inline citations to specific Articles and Sections.

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
