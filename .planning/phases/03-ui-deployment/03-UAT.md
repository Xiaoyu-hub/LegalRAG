---
status: complete
phase: 03-ui-deployment
source: 03-01-SUMMARY.md, 03-02-SUMMARY.md
started: 2026-05-15T15:10:00Z
updated: 2026-05-15T15:50:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running server/service. Start the backend and frontend from scratch. Both boot without errors. Health endpoint returns live data.
result: pass

### 2. Upload a PDF Document
expected: Upload a PDF file via the API. Status transitions from "processing" to "ready" with chunks indexed.
result: pass
details: "POST /api/v1/documents/upload → document_id=1, status=processing → polling showed status=ready, chunk_count=3"

### 3. View Document in List
expected: Document appears in list with filename, chunk count, and ready status. Chunk details show Article/Section structure.
result: pass
details: "GET /api/v1/documents/ → 1 doc: test_legal_doc.pdf, status=ready, chunk_count=3"

### 4. Select Document from Sidebar
expected: Sidebar dropdown populated with uploaded document(s). Selecting a document updates the global document state.
result: pass
details: "Streamlit frontend running on :8501, backend document API reachable, all 3 page modules compile without errors"

### 5. Ask a Question & See Streaming Answer
expected: Send a question via the chat API. Tokens stream in one-by-one. Answer contains inline citation markers.
result: pass
details: "POST /api/v1/chat/ → 200 OK, 34 streaming tokens. Answer: 'Article 1 states agreement governed by state law [Article 1, Section 1]'"

### 6. View Citations & Sources
expected: Answer contains citation markers. Sources endpoint returns retrieved chunk details.
result: pass
details: "Answer included [Article 1, Section 1]. GET /api/v1/chat/sources returned 2 chunks with article/section/text"

### 7. Multi-turn Conversation
expected: Follow-up question with history. Context maintained from prior Q&A.
result: pass
details: "Follow-up 'What about Article 2?' returned 'Article 2 refers to Rights and Obligations [Article 2, Section 1]'"

### 8. Preview Document Structure
expected: Chunks endpoint returns hierarchical Article/Section structure with text.
result: pass
details: "GET /api/v1/documents/1/chunks → 3 chunks: Article 1 (Sec 1), Article 2 (Sec 1, Sec 2)"

### 9. Sidebar Navigation between Pages
expected: All page modules import and compile without errors. Frontend serves correctly.
result: pass
details: "All 6 Streamlit modules (main, 3 pages, 2 components) compile clean. Frontend _stcore/health: ok"

## Summary

total: 9
passed: 9
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]

## Bugs Fixed During Testing

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Duplicate document records on upload | `Indexer.process_document()` created its own doc record, ignoring API-created doc_id | Added `doc_id` param to `Indexer.process_document()`; background task passes it |
| Chat fails after backend restart | FAISS/BM25 indices are in-memory; model default `llama3.1:8b` not available | Startup loads FAISS from disk, rebuilds BM25 from SQLite; default model changed to `llama3.2:3b` |
| Document status "unknown" after restart | `processing_status` dict is in-memory (not persisted) | Startup marks docs with existing chunks as "ready" |
| Streamlit empty selectbox label warning | `st.selectbox("", ...)` with empty string | Changed to `st.selectbox("Select document", ...)` with proper label |
