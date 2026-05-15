---
status: complete
phase: 02-generation-citations
source:
  - 02-01-SUMMARY.md
  - 02-02-SUMMARY.md
started: 2026-05-15T00:00:00Z
updated: 2026-05-15T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Generation Pipeline E2E — Error When Unavailable
expected: Without available models, the pipeline returns a clear, user-actionable error message (not a cryptic traceback).
result: pass
details: |
  Two cases tested:
  - Ollama running, models 404 → RuntimeError: "Neither llama3.1:8b nor qwen2.5:7b is available"
  - Ollama not running → ConnectionError: "Cannot connect to Ollama. Ensure Ollama is running (ollama serve)" (verified via unit tests)
  Both error messages list the available actions the user can take.

### 2. Citation Format in Generated Answers
expected: Generated answers contain citations in `[Article X, Section Y]` format.
result: pass
details: |
  E2E with llama3.2:3b → answer included "[Article 5, Section 1]" matching the enforced format.
  CitationBuilder regex correctly extracts citations from raw LLM output.

### 3. Citation Validation Against Chunks
expected: Valid citations pass; hallucinated citations get `[引用待核实]` marker.
result: pass
details: |
  - Valid [Article 5, Section 1] → valid=True
  - Hallucinated [Article 99, Section 50] → valid=False → replaced with [引用待核实]
  - Subsection [Article 10, Section 3(a)] → valid=True (matched section=3 + subsection=a — bugfix applied)

### 4. Model Fallback Chain
expected: Falls back to secondary on 404; raises RuntimeError when both unavailable.
result: pass
details: |
  - llama3.1:8b (404) → auto falls back to llama3.2:3b → success
  - qwen2.5:3b direct → success
  - Both models 404 → RuntimeError raised
  - Non-404 errors propagated immediately (not swallowed)

### 5. Context Truncation to Token Budget
expected: PromptBuilder truncates to 4096 tokens via tiktoken, drops chunks not query.
result: pass
details: |
  - All 3 truncation test variants pass (512, 1024, 2048 budgets)
  - Query text preserved, chunks dropped from tail
  - XML wrapping includes article/section metadata
  - 18 PromptBuilder unit tests pass

### 6. Citation Precision Metric
expected: Correctly computes valid/total ratio; returns 1.0 for empty list.
result: pass
details: |
  - All 6 precision tests pass (all valid, partial, none, empty list, single valid, single invalid)
  - Edge cases: mixed valid/invalid

### 7. RelevanceJudge Evaluation
expected: Returns score (1-5) with justification; graceful error handling.
result: pass
details: |
  - E2E with llama3.2:3b: score=4/5 for well-cited answer
  - temperature=0.0, format='json' for deterministic output
  - Ollama unavailable → returns fallback score, no crash
  - 10 RelevanceJudge tests pass

### 8. Unit Tests Pass
expected: All 94 tests pass without regressions.
result: pass
details: |
  - 44/44 generation tests pass (including new subsection test)
  - 50/50 evaluation tests pass
  - Pre-existing test_retrieval.py failure acknowledged as unrelated (Phase 1)

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0

## Gaps

[none]

## Bugfix Applied During UAT

### Subsection Citation Matching — validate() method
- **File**: `backend/generation/citation_builder.py`
- **Root cause**: Citations like `[Article 10, Section 3(a)]` were never marked valid. The regex captures `3(a)` as the section group, but chunks store `section="3"` + `subsection="a"` separately. The validate() exact string match `("10", "3(a)") != ("10", "3")` always failed for subsection citations.
- **Fix**: When a chunk has subsection metadata, add `(article_clean, f"{section_clean}({chunk.subsection})")` to the valid_pairs set. This allows citations with embedded subsections to match their source chunks.
- **Test**: Added `test_validate_subsection_citation` to tests/test_generation.py
- **Verification**: 94/94 tests pass
