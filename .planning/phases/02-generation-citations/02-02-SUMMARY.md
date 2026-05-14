---
phase: 02-generation-citations
plan: 02
subsystem: evaluation
tags: [ollama, llm-as-judge, citation-precision, generation-eval]
requires:
  - phase: 02-generation-citations
    plan: 01
    provides: Citation model, prompts.yaml, generation pipeline components
provides:
  - LLM-as-Judge evaluation module (RelevanceJudge) using Ollama with temperature=0.0
  - Citation precision metric (valid/total citations ratio)
  - Generation evaluation pipeline with per-query metrics
  - Test query annotations for ground-truth citation evaluation
  - 50 passing evaluation tests covering all new functionality
affects: [phase 03 UI integration for evaluation dashboards]
tech-stack:
  added: [jinja2 (prompt templates), ollama Python SDK]
  patterns: [LLM-as-Judge with structured JSON output, citation validation via ground-truth annotations]
key-files:
  created:
    - backend/evaluation/judge.py
  modified:
    - backend/evaluation/evaluator.py
    - backend/evaluation/__init__.py
    - backend/evaluation/test_queries.py
    - tests/test_evaluation.py
key-decisions:
  - "RelevanceJudge defaults to llama3.1:8b but accepts configurable model name"
  - "Judge uses temperature=0.0 and format='json' for deterministic structured output"
  - "Citation precision returns 1.0 for empty citations list (no incorrect citations exists)"
  - "EXPECTED_CITATIONS annotations added as QUERY_ANNOTATIONS dict keyed by index, not inline in query dicts"
  - "Evaluator accepts generation_pipeline and judge as optional constructor params (backward compatible)"
requirements-completed: [EVAL-03, EVAL-04]
duration: 18min
completed: 2026-05-14
---

# Phase 02 Plan 02: Generation Evaluation Summary

**LLM-as-Judge (RelevanceJudge) with citation precision metric, query annotations, and end-to-end generation evaluation pipeline**

## Performance

- **Duration:** 18 min
- **Started:** 2026-05-14T13:08:00Z
- **Completed:** 2026-05-14T13:26:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Extended TEST_QUERIES with optional `expected_citations` and `expected_relevance` fields for ground-truth evaluation (backward compatible — existing queries unchanged)
- Created QUERY_ANNOTATIONS dict mapping 5 queries to their expected Article/Section citations and relevance scores
- Implemented RelevanceJudge class with Ollama chat, temperature=0.0, JSON format, and graceful error handling (Ollama unavailable, JSON parse failures, out-of-range scores)
- Judge prompt templates loaded from existing configs/prompts.yaml evaluation section
- Added citation_precision() static method to Evaluator (EVAL-03: citation accuracy metric)
- Added evaluate_generation() method to Evaluator (EVAL-04: full generation pipeline evaluation)
- Added format_generation_results() for human-readable output
- 50 evaluation tests passing (22 new + 13 new + 5 new + 10 pre-existing), no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Citation annotations + RelevanceJudge + prompts.yaml** - `f6a4e41` (feat)
2. **Task 2: Extend Evaluator with citation_precision + evaluate_generation** - `1e9ceb8` (feat)
3. **Task 3: End-to-end integration tests** - `3375a61` (test)

## Files Created/Modified

- `backend/evaluation/judge.py` — New RelevanceJudge class with Ollama-based LLM-as-Judge
- `backend/evaluation/evaluator.py` — Extended with citation_precision, evaluate_generation, format_generation_results
- `backend/evaluation/__init__.py` — Added RelevanceJudge to exports
- `backend/evaluation/test_queries.py` — Added QUERY_ANNOTATIONS dict with expected citations/relevance
- `tests/test_evaluation.py` — Added 40 new tests (annotations, prompts, judge, precision, generation eval, end-to-end)

## Decisions Made

- **QUERY_ANNOTATIONS as separate dict keyed by index** rather than inline `expected_citations` fields in each query dict — maintains backward compatibility with existing code that iterates TEST_QUERIES
- **citation_precision returns 1.0 for empty list** — zero citations means no incorrect citations per the EVAL-03 metric definition
- **RelevanceJudge defaults to llama3.1:8b** — follows the plan's default and plan 02-01 generation pipeline convention
- **Evaluator accepts generation_pipeline and judge as optional** — no breaking changes to existing Phase 1 Evaluator API

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- **Ollama import pattern**: Initial judge.py used `from ollama import chat, Options` which broke test patching (local reference vs module attribute). Fixed by switching to `import ollama` and using `ollama.chat()` — this allows `unittest.mock.patch("ollama.chat")` to work correctly.
- **Pre-existing test failure**: `tests/test_retrieval.py::TestFullRetrievalPipeline::test_retrieve_end_to_end` fails with `AttributeError: 'MetadataStore' object has no attribute 'insert_chunk'` — this is a pre-existing bug from Phase 1, unrelated to this plan.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Evaluation framework is complete with both retrieval metrics (Phase 1) and generation evaluation metrics (this plan)
- Ready for Phase 3 UI integration — evaluation results JSON can be consumed by Streamlit dashboard
- Ollama with a model (default: llama3.1:8b) required for RelevanceJudge to produce actual relevance scores

## Self-Check: PASSED

- All 5 created/modified files verified on disk
- All 3 commits verified in git history (f6a4e41, 1e9ceb8, 3375a61)
- All 50 evaluation tests pass (no regressions)

---

*Phase: 02-generation-citations*
*Completed: 2026-05-14*
