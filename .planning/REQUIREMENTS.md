# Requirements: LegalRAG

**Defined:** 2026-05-12
**Core Value:** Users can quickly find precise answers to legal questions with verifiable sources

## v1 Requirements

### Document Processing

- [ ] **DOC-01**: System can upload and parse PDF legal documents
- [ ] **DOC-02**: Parser extracts text content from PDF files
- [ ] **DOC-03**: Structure extractor identifies Article/Section/Subsection hierarchy
- [ ] **DOC-04**: System extracts legal term definitions from documents
- [ ] **DOC-05**: Metadata is stored with document reference and structure info

### Chunking & Indexing

- [ ] **CHNK-01**: Legal chunker supports "by_article" strategy (Article as minimum unit)
- [ ] **CHNK-02**: Legal chunker supports "by_section" strategy (Section as minimum unit)
- [ ] **CHNK-03**: Chunks preserve metadata (article, section, subsection, parent references)
- [ ] **CHNK-04**: Text is embedded using BGE-large-en-v1.5 model
- [ ] **CHNK-05**: Embeddings are stored in FAISS index locally
- [ ] **CHNK-06**: Document metadata stored in SQLite database

### Retrieval

- [ ] **RETR-01**: BM25 keyword search retrieves relevant chunks
- [ ] **RETR-02**: Vector search retrieves semantically similar chunks
- [ ] **RETR-03**: Hybrid search merges BM25 and vector results with configurable alpha
- [ ] **RETR-04**: Cross-encoder reranker improves top-K result quality
- [ ] **RETR-05**: System returns top-N chunks with metadata and similarity scores

### Generation

- [ ] **GEN-01**: Prompt builder assembles context from retrieved chunks
- [ ] **GEN-02**: System prompts LLM to cite specific Articles and Sections
- [ ] **GEN-03**: Ollama integration supports Qwen2.5 (or Llama3) locally
- [ ] **GEN-04**: Generated answers include formatted citations [Article X, Section Y]
- [ ] **GEN-05**: Citation builder extracts and validates citation references

### User Interface

- [ ] **UI-01**: Streamlit interface provides document upload page
- [ ] **UI-02**: Document list shows uploaded documents with metadata
- [ ] **UI-03**: Chat interface accepts natural language questions
- [ ] **UI-04**: Answers display with inline citations
- [ ] **UI-05**: Citation box component shows source text and reference
- [ ] **UI-06**: Document preview shows parsed structure

### API Backend

- [ ] **API-01**: FastAPI provides document upload endpoint
- [ ] **API-02**: Document processing pipeline endpoint triggers parsing/indexing
- [ ] **API-03**: Chat endpoint accepts question and returns answer with citations
- [ ] **API-04**: Search endpoint returns raw retrieval results
- [ ] **API-05**: Async processing for long-running document parsing tasks

### Evaluation

- [ ] **EVAL-01**: Precision@5 metric for retrieval quality
- [ ] **EVAL-02**: Recall@5 metric for retrieval coverage
- [ ] **EVAL-03**: Citation accuracy metric for answer correctness
- [ ] **EVAL-04**: Answer relevance evaluation (LLM-as-judge)

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
| DOC-01 | Phase 1 | Pending |
| DOC-02 | Phase 1 | Pending |
| DOC-03 | Phase 1 | Pending |
| DOC-04 | Phase 1 | Pending |
| DOC-05 | Phase 1 | Pending |
| CHNK-01 | Phase 1 | Pending |
| CHNK-02 | Phase 1 | Pending |
| CHNK-03 | Phase 1 | Pending |
| CHNK-04 | Phase 1 | Pending |
| CHNK-05 | Phase 1 | Pending |
| CHNK-06 | Phase 1 | Pending |
| RETR-01 | Phase 1 | Pending |
| RETR-02 | Phase 1 | Pending |
| RETR-03 | Phase 1 | Pending |
| RETR-04 | Phase 1 | Pending |
| RETR-05 | Phase 1 | Pending |
| EVAL-01 | Phase 1 | Pending |
| EVAL-02 | Phase 1 | Pending |
| GEN-01 | Phase 2 | Pending |
| GEN-02 | Phase 2 | Pending |
| GEN-03 | Phase 2 | Pending |
| GEN-04 | Phase 2 | Pending |
| GEN-05 | Phase 2 | Pending |
| EVAL-03 | Phase 2 | Pending |
| EVAL-04 | Phase 2 | Pending |
| API-01 | Phase 3 | Pending |
| API-02 | Phase 3 | Pending |
| API-03 | Phase 3 | Pending |
| API-04 | Phase 3 | Pending |
| API-05 | Phase 3 | Pending |
| UI-01 | Phase 3 | Pending |
| UI-02 | Phase 3 | Pending |
| UI-03 | Phase 3 | Pending |
| UI-04 | Phase 3 | Pending |
| UI-05 | Phase 3 | Pending |
| UI-06 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 34 total
- Mapped to phases: 34
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-12*
*Last updated: 2026-05-12 after initial definition*
