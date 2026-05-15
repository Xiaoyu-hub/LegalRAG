# Roadmap: LegalRAG

**Project:** LegalRAG — Legal Document Q&A System  
**Created:** 2026-05-12  
**Mode:** MVP (Vertical slice delivery)

---

## Phase Overview

| Phase | Name | Goal | Requirements | Status |
|-------|------|------|--------------|--------|
| 1 | Core Retrieval Engine | Build document processing and hybrid retrieval pipeline | DOC-01~05, CHNK-01~06, RETR-01~05, EVAL-01~02 | ✓ Complete |
| 2 | Generation & Citations | Add LLM generation with legal citation support | GEN-01~05, EVAL-03~04 | ✓ Complete |
| 3 | UI & Deployment | Build Streamlit frontend and Docker deployment | API-01~05, UI-01~06 | ✓ Complete |
| 3.1 | 关闭阻塞项：修复依赖、健康检查、document_id、引用验证 | Fix blockers: deps, health check, document_id, citations | N/A | ✓ Complete |

---

## Phase 1: Core Retrieval Engine

**Goal:** Build document processing and hybrid retrieval pipeline

**Mode:** mvp

**Requirements Mapped:**
- DOC-01, DOC-02, DOC-03, DOC-04, DOC-05
- CHNK-01, CHNK-02, CHNK-03, CHNK-04, CHNK-05, CHNK-06
- RETR-01, RETR-02, RETR-03, RETR-04, RETR-05
- EVAL-01, EVAL-02

**Success Criteria:**
1. PDF documents can be uploaded and parsed into structured text
2. Legal structure (Article/Section/Subsection) is correctly extracted
3. Documents are chunked using legal-aware strategies
4. Hybrid retrieval (BM25 + Vector) returns relevant chunks
5. Evaluation metrics (Precision@5, Recall@5) are measurable

**Technical Notes:**
- Use PyMuPDF + pdfplumber for PDF parsing
- Implement regex-based structure extraction for Article/Section patterns
- BGE-large-en-v1.5 for embeddings (CPU compatible)
- FAISS for vector storage, SQLite for metadata
- BM25 via rank_bm25 library
- Cross-encoder/ms-marco for reranking

---

## Phase 2: Generation & Citations

**Goal:** Add LLM generation with legal citation support

**Mode:** mvp

**Requirements Mapped:**
- GEN-01, GEN-02, GEN-03, GEN-04, GEN-05
- EVAL-03, EVAL-04

**Success Criteria:**
1. System generates answers using local LLM via Ollama
2. Prompt instructs LLM to cite specific Articles/Sections
3. Citation builder extracts and formats legal references
4. Citation accuracy is measurable (>80% target)
5. Answer relevance evaluated (LLM-as-judge)

**Technical Notes:**
- Ollama integration for Qwen2.5 or Llama3
- Prompt templates in configs/prompts.yaml
- Citation extraction via regex and LLM parsing
- Evaluation scripts for citation accuracy

**Plans:** 2 plans

Plans:
- [x] 02-01-PLAN.md — Generation Pipeline (PromptBuilder, Generator, CitationBuilder, GenerationPipeline)
- [x] 02-02-PLAN.md — Evaluation Integration (citation annotations, RelevanceJudge, citation_precision, evaluate_generation)

---

## Phase 3: UI & Deployment

**Goal:** Build Streamlit frontend and Docker deployment

**Mode:** mvp

**Requirements Mapped:**
- API-01, API-02, API-03, API-04, API-05
- UI-01, UI-02, UI-03, UI-04, UI-05, UI-06

**Success Criteria:**
1. FastAPI backend exposes document and chat endpoints
2. Streamlit frontend provides document upload interface
3. Chat interface accepts questions and displays answers
4. Answers show inline citations with source references
5. Docker compose enables one-command deployment
6. README with setup instructions and screenshots

**Plans:** 2 plans

Plans:
- [x] 03-01-PLAN.md — Documents Vertical Slice (FastAPI framework, documents API, Streamlit documents page)
- [x] 03-02-PLAN.md — Chat + Search + Preview + Deployment (chat API, search API, chat/preview pages, Docker, README)

---

## Progress Tracking

**Phase Status Legend:**
- ○ Pending — Not started
- ◆ In Progress — Active phase
- ✓ Complete — Finished and verified

**Current Phase:** Phase 3.1 — 关闭阻塞项 (COMPLETE)

**Next Action:** v1.0 里程碑收尾

---

## Milestone Definition

**Milestone: v1.0 MVP**
- All 34 v1 requirements implemented
- System can: upload PDFs, parse legal structure, index for search, answer questions with citations
- Streamlit UI functional
- Docker deployment working
- README published on GitHub

---

*Roadmap created: 2026-05-12*
*Last updated: 2026-05-12 after initialization*

### Phase 03.1: 关闭阻塞项：修复依赖、健康检查、document_id、引用验证 (INSERTED)

**Goal:** Fix cross-phase blockers: dependency manifest, health check async/coverage, document_id filtering, citation validation
**Requirements**: N/A (bugfix/cleanup phase)
**Depends on:** Phase 3
**Plans:** 5 plans

Plans:
- [x] 03.1-01-PLAN.md — Dependency Manifest Fix (requirements.txt + Dockerfile)
- [x] 03.1-02-PLAN.md — Health Check Enhancement (httpx.AsyncClient, BM25/Embedder/FAISS checks)
- [x] 03.1-03-PLAN.md — Citation Validation Fixes (English text, article-only regex, two-level validation)
- [x] 03.1-04-PLAN.md — MetadataStore Refactor (get_all_documents(), eliminate raw SQLite from documents.py)
- [x] 03.1-05-PLAN.md — Document ID Post-Filtering (pipeline + chat endpoint)
