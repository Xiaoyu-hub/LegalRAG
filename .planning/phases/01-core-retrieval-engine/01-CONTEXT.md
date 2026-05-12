# Phase 1: Core Retrieval Engine - Context

**Gathered:** 2026-05-12
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers the document processing and hybrid retrieval pipeline for LegalRAG. It includes:
- PDF document parsing and text extraction
- Legal structure extraction (Article/Section/Subsection hierarchy)
- Legal-aware document chunking with metadata preservation
- Hybrid retrieval system (BM25 + Vector Search)
- Evaluation metrics (Precision@5, Recall@5)

The output is a working retrieval engine that can process legal PDFs and return relevant chunks based on user queries.

</domain>

<decisions>
## Implementation Decisions

### PDF Parsing Strategy
- **D-01:** Use PyMuPDF (fitz) as primary parser for text extraction — it handles most legal PDFs well and preserves layout information
- **D-02:** Implement pdfplumber as fallback for complex table-heavy documents or when PyMuPDF fails
- **D-03:** Support text-based PDFs only for Phase 1 (OCR for scanned documents deferred to Phase 2)

### Legal Structure Extraction
- **D-04:** Use regex-based pattern matching to identify legal document structure — sufficient for standard legal document formats
- **D-05:** Patterns to support: `Article [IVX]+` / `Article \d+`, `Section \d+`, `\([a-z]\)` / `\(\d+\)` for subsections
- **D-06:** Extract legal term definitions (e.g., `"Person" means...`) for enhanced retrieval context

### Chunking Strategy
- **D-07:** Default to "by_section" chunking — provides better granularity for citation accuracy
- **D-08:** Support "by_article" as configurable alternative for broader context
- **D-09:** Preserve full hierarchy metadata: article → section → subsection → parent reference
- **D-10:** Chunk size target: 512-1024 tokens per chunk (to fit embedding model context)

### Embedding & Vector Storage
- **D-11:** Use BGE-large-en-v1.5 embedding model — confirmed best open-source English embedding, CPU runnable
- **D-12:** Batch size: 32 for embedding generation (memory-efficient on CPU)
- **D-13:** FAISS with IndexFlatIP (Inner Product) for exact similarity search — sufficient for MVP scale
- **D-14:** Store document metadata in SQLite with foreign key relationships

### Hybrid Retrieval
- **D-15:** Alpha weighting: 0.7 vector / 0.3 BM25 (vector-weighted as per architecture)
- **D-16:** Use rank_bm25 library for keyword retrieval
- **D-17:** Cross-encoder reranker: cross-encoder/ms-marco-MiniLM-L-6-v2 (lightweight, CPU-friendly)
- **D-18:** Return top-10 chunks before reranking, top-5 after reranking

### Evaluation Approach
- **D-19:** Create manual test dataset with 20-30 sample queries and relevance judgments
- **D-20:** Use standard metrics: Precision@5 and Recall@5
- **D-21:** Evaluation script outputs JSON results for tracking over time

### the agent's Discretion
- Exact regex pattern implementation details
- SQLite schema design (within constraints of requirements)
- Specific error handling strategies
- Directory structure within `backend/` folder

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — Project overview, core value, constraints
- `.planning/REQUIREMENTS.md` — Full requirements with REQ-IDs (DOC-01~05, CHNK-01~06, RETR-01~05, EVAL-01~02)
- `.planning/ROADMAP.md` — Phase 1 success criteria and technical notes

### Architecture Reference
- `architecture.md` — Full system architecture and data flow
- `ref.md` — RAG landscape analysis and best practices

### No External Specs
No external specifications referenced — requirements fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None yet — this is the foundational phase

### Established Patterns
- None yet — establishing patterns for future phases

### Integration Points
- Phase 2 (Generation) will consume the retrieval API from this phase
- Phase 3 (UI) will call the document processing pipeline

</code_context>

<specifics>
## Specific Ideas

Based on the architecture document:
- Legal document structure follows patterns: Article → Section → Subsection
- Example: "Article I. General Provisions / Section 1. Definitions / (a) 'Person' means..."
- Hybrid search formula: `score = 0.7 * vector_score + 0.3 * bm25_score`
- Chunk metadata must include: chunk_id, article, section, subsection, text, title, parent_article

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. All Phase 1 requirements are committed.

</deferred>

---

*Phase: 1-Core Retrieval Engine*
*Context gathered: 2026-05-12*
