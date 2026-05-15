# Requirements: LegalRAG

**Defined:** 2026-05-12
**Core Value:** Users can quickly find precise answers to legal questions with verifiable sources

## v1 Requirements

### Document Processing

- [x] **DOC-01**: System can upload and parse PDF legal documents
- [x] **DOC-02**: Parser extracts text content from PDF files
- [x] **DOC-03**: Structure extractor identifies Article/Section/Subsection hierarchy
- [x] **DOC-04**: System extracts legal term definitions from documents
- [x] **DOC-05**: Metadata is stored with document reference and structure info

### Chunking & Indexing

- [x] **CHNK-01**: Legal chunker supports "by_article" strategy (Article as minimum unit)
- [x] **CHNK-02**: Legal chunker supports "by_section" strategy (Section as minimum unit)
- [x] **CHNK-03**: Chunks preserve metadata (article, section, subsection, parent references)
- [x] **CHNK-04**: Text is embedded using BGE-large-en-v1.5 model
- [x] **CHNK-05**: Embeddings are stored in FAISS index locally
- [x] **CHNK-06**: Document metadata stored in SQLite database

### Retrieval

- [x] **RETR-01**: BM25 keyword search retrieves relevant chunks
- [x] **RETR-02**: Vector search retrieves semantically similar chunks
- [x] **RETR-03**: Hybrid search merges BM25 and vector results with configurable alpha
- [x] **RETR-04**: Cross-encoder reranker improves top-K result quality
- [x] **RETR-05**: System returns top-N chunks with metadata and similarity scores

### Generation

- [x] **GEN-01**: Prompt builder assembles context from retrieved chunks
- [x] **GEN-02**: System prompts LLM to cite specific Articles and Sections
- [x] **GEN-03**: Ollama integration supports Qwen2.5 (or Llama3) locally
- [x] **GEN-04**: Generated answers include formatted citations [Article X, Section Y]
- [x] **GEN-05**: Citation builder extracts and validates citation references

### User Interface

- [x] **UI-01**: Streamlit interface provides document upload page
- [x] **UI-02**: Document list shows uploaded documents with metadata
- [x] **UI-03**: Chat interface accepts natural language questions
- [x] **UI-04**: Answers display with inline citations
- [x] **UI-05**: Citation box component shows source text and reference
- [x] **UI-06**: Document preview shows parsed structure

### API Backend

- [x] **API-01**: FastAPI provides document upload endpoint
- [x] **API-02**: Document processing pipeline endpoint triggers parsing/indexing
- [x] **API-03**: Chat endpoint accepts question and returns answer with citations
- [x] **API-04**: Search endpoint returns raw retrieval results
- [x] **API-05**: Async processing for long-running document parsing tasks

### Evaluation

- [x] **EVAL-01**: Precision@5 metric for retrieval quality
- [x] **EVAL-02**: Recall@5 metric for retrieval coverage
- [x] **EVAL-03**: Citation accuracy metric for answer correctness
- [x] **EVAL-04**: Answer relevance evaluation (LLM-as-judge)

## v2 Requirements

### Document Processing

- **DOC-V2-01**: Support for scanned PDFs with OCR
- **DOC-V2-02**: Table extraction and preservation
- **DOC-V2-03**: Multi-format support (Word, HTML)

### Advanced Retrieval

- **RETR-V2-01**: Query expansion for legal synonyms
- **RETR-V2-02**: Multi-document reasoning across regulations
- **RETR-V2-03**: Query classification (factual vs. interpretive)

### Generation

- **GEN-V2-01**: Multi-hop reasoning for complex questions
- **GEN-V2-02**: Confidence scoring for answers
- **GEN-V2-03**: Answer summarization with key points

### UI/UX

- **UI-V2-01**: Chat history and conversation management
- **UI-V2-02**: Export answers with citations
- **UI-V2-03**: Advanced search filters

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-language support | Focus on English legal documents for MVP |
| Real-time document sync | Batch upload sufficient for v1 |
| Mobile application | Web-first, responsive design only |
| User authentication | Single-user local deployment for MVP |
| Advanced analytics | Basic functionality priority |
| Cloud deployment options | Privacy-first local-only for v1 |
| Collaborative features | Single-user focus for MVP |
| Integration with external legal databases | Manual document upload only |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DOC-01 | Phase 1 | ✓ Complete |
| DOC-02 | Phase 1 | ✓ Complete |
| DOC-03 | Phase 1 | ✓ Complete |
| DOC-04 | Phase 1 | ✓ Complete |
| DOC-05 | Phase 1 | ✓ Complete |
| CHNK-01 | Phase 1 | ✓ Complete |
| CHNK-02 | Phase 1 | ✓ Complete |
| CHNK-03 | Phase 1 | ✓ Complete |
| CHNK-04 | Phase 1 | ✓ Complete |
| CHNK-05 | Phase 1 | ✓ Complete |
| CHNK-06 | Phase 1 | ✓ Complete |
| RETR-01 | Phase 1 | ✓ Complete |
| RETR-02 | Phase 1 | ✓ Complete |
| RETR-03 | Phase 1 | ✓ Complete |
| RETR-04 | Phase 1 | ✓ Complete |
| RETR-05 | Phase 1 | ✓ Complete |
| EVAL-01 | Phase 1 | ✓ Complete |
| EVAL-02 | Phase 1 | ✓ Complete |
| GEN-01 | Phase 2 | ✓ Complete |
| GEN-02 | Phase 2 | ✓ Complete |
| GEN-03 | Phase 2 | ✓ Complete |
| GEN-04 | Phase 2 | ✓ Complete |
| GEN-05 | Phase 2 | ✓ Complete |
| EVAL-03 | Phase 2 | ✓ Complete |
| EVAL-04 | Phase 2 | ✓ Complete |
| API-01 | Phase 3 | ✓ Complete |
| API-02 | Phase 3 | ✓ Complete |
| API-03 | Phase 3 | ✓ Complete |
| API-04 | Phase 3 | ✓ Complete |
| API-05 | Phase 3 | ✓ Complete |
| UI-01 | Phase 3 | ✓ Complete |
| UI-02 | Phase 3 | ✓ Complete |
| UI-03 | Phase 3 | ✓ Complete |
| UI-04 | Phase 3 | ✓ Complete |
| UI-05 | Phase 3 | ✓ Complete |
| UI-06 | Phase 3 | ✓ Complete |

**Coverage:**
- v1 requirements: 34 total
- Mapped to phases: 34
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-12*
*Last updated: 2026-05-15 — all 34 v1 requirements completed*
