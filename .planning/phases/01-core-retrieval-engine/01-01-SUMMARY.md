---
phase: 01-core-retrieval-engine
plan: 01
subsystem: ingestion-pipeline
tags: [pymupdf, pdfplumber, sqlite, pytest, regex, legal-chunking]

requires: []
provides:
  - PDF text extraction via PyMuPDF with pdfplumber fallback
  - Legal structure extraction (Article/Section/Subsection hierarchy)
  - Legal-aware chunking (by_section / by_article strategies)
  - SQLite metadata store (documents, chunks, definitions tables)
  - Integration test suite for ingestion pipeline
affects:
  - 01-02 (embedding and indexing will consume chunks from MetadataStore)
  - 01-03 (retrieval and reranking will use chunked data)
  - 01-04 (evaluation will use test dataset)

tech-stack:
  added:
    - pymupdf==1.27.2.3 (PDF text extraction)
    - pdfplumber==0.11.9 (PDF fallback parser)
    - numpy>=1.26.4 (array operations)
    - pytest>=8.0 (test framework)
  patterns:
    - TDD: RED phase (failing tests) before GREEN phase (implementation)
    - Threat model mitigations implemented directly in parser.py
    - Dataclass models for typed data contracts
    - Regex-based legal hierarchy extraction line-by-line

key-files:
  created:
    - backend/pipeline/parser.py — PDFParser with PyMuPDF + pdfplumber fallback
    - backend/pipeline/structure_extractor.py — StructureExtractor with regex hierarchy detection
    - backend/pipeline/legal_chunker.py — LegalChunker with by_section/by_article strategies
    - backend/storage/metadata_store.py — MetadataStore with SQLite CRUD for docs/chunks/definitions
    - backend/models/document.py — Document dataclass
    - backend/models/chunk.py — Chunk dataclass
    - data/test/sample_legal.txt — Synthetic regulation fixture (83 lines, 3 articles, 9 sections)
    - tests/test_ingestion.py — 14 pytest tests for full ingestion pipeline
    - tests/conftest.py — Shared test fixtures
    - requirements.txt — Project dependencies
  modified: []

key-decisions:
  - "Article headings included as context in by_section chunks (discovered during integration test — headings were being skipped)"
  - "Threat model mitigations (T-01-01 path traversal, T-01-02 file size limit) implemented directly in PDFParser"
  - "MetadataStore uses separate .db file path; :memory: support for testing"

patterns-established:
  - "TDD flow: RED tests → GREEN implementation commits per task"
  - "Backend modules structured as: models/ (dataclasses), pipeline/ (processing), storage/ (persistence)"
  - "SQLite schema with FK relationships for referential integrity"
  - "Fixture-driven testing with sample legal document shared across test classes"

requirements-completed:
  - DOC-01
  - DOC-02
  - DOC-03
  - DOC-04
  - DOC-05
  - CHNK-01
  - CHNK-02
  - CHNK-03

duration: 8min
completed: 2026-05-12
---

# Phase 01 Plan 01: Document Ingestion Pipeline Summary

**PDF parsing (PyMuPDF + pdfplumber fallback), regex-based legal structure extraction, legal-aware chunking (by_section/by_article), and SQLite metadata storage — 14/14 integration tests passing**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-12T06:00:00Z
- **Completed:** 2026-05-12T06:05:50Z
- **Tasks:** 3
- **Files created:** 12
- **Test count:** 14 (all passing)

## Accomplishments

- **TDD Foundation:** Wrote 14 behavioral tests for the full ingestion pipeline first (RED), then implemented all modules (GREEN) — all tests pass
- **PDF Parser:** PyMuPDF primary extraction with pdfplumber fallback, file size limit (100MB default), path traversal protection
- **Legal Structure Extractor:** Regex-based detection of Article (Roman/arabic), Section (\d+), Subsection ([a-z]/\d+), and legal term definitions ("term" means...)
- **Legal-Aware Chunker:** `by_section` (default, per D-07) and `by_article` (configurable, per D-08) strategies with full hierarchy metadata preservation per D-09
- **SQLite Metadata Store:** `documents`, `chunks`, and `definitions` tables with FK relationships and indexes
- **Sample Legal Fixture:** 83-line synthetic US-style regulation with 3 Articles, 9 Sections, subsections, and definitions

## Task Commits

1. **Task 1: Test fixture and failing integration tests (TDD RED)** — `751a584` (test: add test fixture and failing tests)
2. **Task 2: Data models and PDF parser** — `2ec514b` (feat: implement data models and PDF parser)
3. **Task 3: StructureExtractor, LegalChunker, MetadataStore** — `a5922a9` (feat: implement all three modules)

## Files Created/Modified

- `requirements.txt` — Project dependencies (pymupdf, pdfplumber, pytest, etc.)
- `backend/__init__.py` — Backend package init
- `backend/models/__init__.py` — Exports Document and Chunk
- `backend/models/document.py` — Document dataclass with all fields
- `backend/models/chunk.py` — Chunk dataclass with hierarchy metadata
- `backend/pipeline/__init__.py` — Exports PDFParser, StructureExtractor, LegalChunker
- `backend/pipeline/parser.py` — PDFParser with PyMuPDF + pdfplumber, threat mitigations
- `backend/pipeline/structure_extractor.py` — StructureExtractor with regex hierarchy and definition extraction
- `backend/pipeline/legal_chunker.py` — LegalChunker with by_section / by_article strategies
- `backend/storage/__init__.py` — Exports MetadataStore
- `backend/storage/metadata_store.py` — MetadataStore with full SQLite CRUD
- `data/test/sample_legal.txt` — 83-line synthetic regulation fixture
- `tests/__init__.py` — Test package init
- `tests/conftest.py` — Shared test fixtures (sample_pdf_text, sample_pdf_path, temp_db_path)
- `tests/test_ingestion.py` — 14 tests across 6 test classes

## Decisions Made

- **Article heading context:** by_section chunking now includes the parent article heading text at the start of each section chunk. Discovered during integration testing — the article heading was being skipped since by_section only includes section elements.
- **Threat model implementation:** T-01-01 (path traversal) mitigated via `os.path.basename()` and `..` rejection in `_validate_path`. T-01-02 (DoS) mitigated via configurable `max_file_size` parameter defaulting to 100MB.
- **MetadataStore :memory: support:** Pass `db_path=":memory:"` for testing without file I/O.
- **PyMuPDF block extraction:** Using `page.get_text("blocks", sort=True)` with `block_type == 0` filter for text-only extraction, which handles reading order.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Article heading text excluded from by_section chunks**
- **Found during:** Task 3 (Integration test verification)
- **Issue:** The integration test `test_full_ingestion_pipeline` asserts that chunk texts contain "General Provisions" (from the Article I heading). The by_section chunker was skipping article elements entirely, so article headings were not included in any chunk's text.
- **Fix:** Modified `_chunk_by_section` to track `current_article_text` and prepend it to each section's content when a new section is encountered.
- **Files modified:** `backend/pipeline/legal_chunker.py`
- **Verification:** Integration test passes — `any("General Provisions" in t for t in chunk_texts)` now returns True
- **Committed in:** a5922a9 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Fix ensures article headings are preserved as context in section chunks — essential for legal document retrieval where the parent article provides critical context.

## Issues Encountered

- **pip install timeout:** Installing sentence-transformers and faiss-cpu timed out (5+ min). These packages are not needed for Plan 01-01 (they're for plans 01-02 and beyond). Installed only the packages needed: pymupdf, pdfplumber, numpy, pytest.

## User Setup Required

None — no external service configuration required. All dependencies installable via pip.

## Next Phase Readiness

- **Ingestion pipeline complete** — ready for Plan 01-02 (Embedding & Indexing) which will consume chunk texts from MetadataStore
- **MetadataStore API stable** — `get_chunk_texts()`, `get_all_chunks()`, `get_chunks()` provide the interface needed for embedding generation
- **Test infrastructure in place** — pytest suite, fixtures, and sample legal document available for all downstream testing
- **sentence-transformers and faiss-cpu** still need installation (deferred to Plan 01-02 due to long install time)

## Self-Check: PASSED

- ✅ SUMMARY.md exists at `.planning/phases/01-core-retrieval-engine/01-01-SUMMARY.md`
- ✅ Commit `751a584` exists (Task 1: test fixture + failing tests)
- ✅ Commit `2ec514b` exists (Task 2: data models + PDF parser)
- ✅ Commit `a5922a9` exists (Task 3: StructureExtractor, LegalChunker, MetadataStore)
- ✅ Commit `3069043` exists (docs: SUMMARY.md)
- ✅ All 14 tests pass
- ✅ All 8 requirements completed (DOC-01~05, CHNK-01~03)

---
*Phase: 01-core-retrieval-engine*
*Completed: 2026-05-12*
