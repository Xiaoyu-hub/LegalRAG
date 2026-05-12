# Phase 1: Core Retrieval Engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-12
**Phase:** 1-Core Retrieval Engine
**Areas discussed:** PDF Parsing, Structure Extraction, Chunking Strategy, Hybrid Retrieval, Evaluation Approach
**Mode:** Auto (recommended defaults selected)

---

## PDF Parser Selection

| Option | Description | Selected |
|--------|-------------|----------|
| PyMuPDF primary | Fast, layout-preserving text extraction | ✓ |
| pdfplumber fallback | Better for complex tables | ✓ |
| OCR support | For scanned documents | (Deferred to Phase 2) |

**Auto-selected:** PyMuPDF as primary with pdfplumber fallback for robustness.
**Notes:** OCR deferred to Phase 2 per architecture document scope.

---

## Structure Extraction Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Regex patterns | Pattern matching for Article/Section/Subsection | ✓ |
| ML-based | Train model for structure detection | |
| Hybrid approach | Combine both methods | |

**Auto-selected:** Regex-based pattern matching — sufficient for standard legal document formats.
**Notes:** Patterns: `Article [IVX]+` / `Article \d+`, `Section \d+`, `\([a-z]\)` / `\(\d+\)`

---

## Chunking Granularity

| Option | Description | Selected |
|--------|-------------|----------|
| by_article | Article as minimum unit | (Alternative) |
| by_section | Section as minimum unit | ✓ |
| semantic_window | Context-aware expansion | |

**Auto-selected:** by_section as default (more granular for citation accuracy), by_article as configurable alternative.
**Notes:** Target 512-1024 tokens per chunk.

---

## Hybrid Search Configuration

| Parameter | Value | Notes |
|-----------|-------|-------|
| Alpha (vector/BM25) | 0.7 / 0.3 | Vector-weighted per architecture |
| BM25 library | rank_bm25 | Lightweight implementation |
| Reranker | ms-marco-MiniLM-L-6-v2 | CPU-friendly cross-encoder |
| Top-K before rerank | 10 | Retrieved candidates |
| Top-K after rerank | 5 | Final results |

**Auto-selected:** Standard configuration matching architecture document specifications.

---

## Evaluation Dataset

| Option | Description | Selected |
|--------|-------------|----------|
| Manual test set | Create 20-30 sample queries with judgments | ✓ |
| Synthetic data | Generate queries automatically | |
| Existing benchmark | Use legal IR benchmark | |

**Auto-selected:** Manual test dataset creation with sample legal documents.
**Notes:** Metrics: Precision@5 and Recall@5.

---

## the agent's Discretion

- Exact regex pattern implementation details
- SQLite schema design (within requirement constraints)
- Specific error handling strategies
- Directory structure within `backend/` folder

---

## Deferred Ideas

None — discussion stayed within phase scope.

---

*Log generated: 2026-05-12*
*Mode: Auto-select recommended options*
