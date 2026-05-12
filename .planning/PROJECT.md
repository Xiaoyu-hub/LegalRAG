# LegalRAG

## What This Is

LegalRAG is an intelligent Q&A system for English legal documents (regulations, statutes, judicial interpretations). It enables users to ask natural language questions about legal content and receive accurate answers with precise citations to specific articles and sections.

## Core Value

Users can quickly find precise answers to legal questions with verifiable sources—solving the problem of keyword search inaccuracy and fragmented legal document retrieval.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Parse PDF legal documents and extract structured text (Articles/Sections/Subsections)
- [ ] Implement legal-aware chunking strategies that preserve document hierarchy
- [ ] Build hybrid retrieval engine (BM25 + Vector Search)
- [ ] Generate answers with accurate legal citations
- [ ] Create Streamlit UI for document upload and Q&A interface
- [ ] Ensure full local deployment capability (privacy-preserving)

### Out of Scope

- Multi-language support (English only for v1) — scope focus on English legal documents
- Real-time document sync — MVP handles batch uploads only
- Mobile application — web-first approach
- Advanced analytics/dashboards — basic usage only
- OCR for scanned documents — focus on text-based PDFs first

## Context

### Problem Domain

Legal document retrieval faces unique challenges:
- **Keyword matching is inaccurate**: Legal terms have many synonyms ("shall" = "must" = "is required to")
- **Document structure is lost**: Traditional chunking breaks legal articles into fragments
- **Answers lack sources**: Generic RAG doesn't cite specific legal provisions
- **Data privacy concerns**: Law firms hesitate to upload sensitive docs to third-party APIs

### Technical Environment

- Target deployment: Local/On-premise (privacy-first)
- Primary language: English legal documents
- Document format: PDF (text-based initially)
- User base: Law firms, corporate legal departments, legal tech startups, legal AI researchers

### Reference Analysis

Based on analysis of successful RAG projects (LangChain, Dify, RAGFlow), this project differentiates through:
- Domain-specific legal document parsing
- Legal-aware chunking strategies
- Grounded citations with article/section numbers
- Privacy-focused local deployment

## Constraints

- **Tech Stack**: Python, FastAPI, Streamlit, FAISS, SQLite, Ollama
- **Deployment**: Must run entirely locally (no cloud APIs for sensitive docs)
- **Timeline**: 4-week MVP (aligned with architecture plan)
- **Performance**: CPU-compatible (BGE embeddings, Ollama local LLM)
- **License**: Open source (portfolio project)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hybrid retrieval (BM25 + Vector) | Legal needs both keyword precision and semantic similarity | — Pending |
| Local LLM via Ollama | Privacy requirement for sensitive legal docs | — Pending |
| BGE-large-en embeddings | Best open-source English embedding, CPU runnable | — Pending |
| Streamlit frontend | Rapid Python-native UI development | — Pending |
| FAISS for vector storage | Zero-dependency local vector DB | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-12 after initialization*
