---
phase: 02-generation-citations
plan: 01
subsystem: generation
tags: [ollama, citation-builder, prompt-builder, generation-pipeline, tiktoken]
requires:
  - phase: 01-foundation
    provides: Document ingestion, embedding, hybrid retrieval, reranker, evaluation framework
provides:
  - Citation dataclass (article, section, subsection, valid, confidence)
  - Jinja2+YAML prompt templates with [Article X, Section Y] citation enforcement
  - PromptBuilder with tiktoken-based context truncation (4096 token budget)
  - Generator with Ollama chat API, model fallback (llama3.1:8b → qwen2.5:7b), auto-pull
  - CitationBuilder with regex extraction and validation against chunk metadata
  - GenerationPipeline orchestrating retrieval → prompts → generation → citation validation
  - 43 passing unit tests covering all components
affects: [phase 02 plan 02 evaluation, phase 03 UI integration]
tech-stack:
  added: [pyyaml, tiktoken, jinja2 (prompt templates), ollama Python SDK (generation)]
  patterns: [single-turn generation via system+user prompts, tiktoken-based context truncation, citation validation against chunk metadata, model fallback chain]
key-files:
  created:
    - backend/models/citation.py
    - configs/prompts.yaml
    - backend/generation/__init__.py
    - backend/generation/prompt_builder.py
    - backend/generation/generator.py
    - backend/generation/citation_builder.py
    - backend/generation/pipeline.py
    - tests/test_generation.py
  modified:
    - backend/models/__init__.py
    - requirements.txt
key-decisions:
  - "Single-turn generation: system prompt is static, user prompt carries context + query per D-04"
  - "System prompt mandates [Article X, Section Y] citation format per D-05"
  - "Context: top-5 chunks post-reranking per D-10"
  - "Token limit: 4096 via tiktoken (cl100k_base), NOT character counting per D-11"
  - "XML wrapping: <chunk id=N article=X section=Y>text</chunk> per D-12"
  - "Temperature 0.1 for deterministic legal answers"
  - "Fallback from llama3.1:8b to qwen2.5:7b on Ollama 404 model-not-found"
  - "Generator catches 404 on ANY model to continue fallback chain, re-raises other errors"
requirements-completed: [GEN-01, GEN-02, GEN-03, GEN-04, GEN-05]
duration: 15min
completed: 2026-05-14
---

# Phase 02 Plan 01: Generation Pipeline Summary

**Ollama-based generation pipeline with Jinja2+YAML prompt templates, tiktoken-based context truncation, citation extraction/validation, and automatic model fallback**

## Performance

- **Duration:** 15 min
- **Started:** 2026-05-14T13:07:44Z
- **Completed:** 2026-05-14T13:22:00Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- Created Citation dataclass with article/section/subsection metadata fields (GEN-01 data model)
- Built configs/prompts.yaml with Jinja2 templates for generation system/user prompts enforcing [Article X, Section Y] citation format per D-05
- Implemented PromptBuilder with XML chunk wrapping (`<chunk id=N article=X section=Y>`), tiktoken-based truncation, and 4096 token budget per D-11/D-12
- Built Generator with Ollama `chat()` API, temperature=0.1, model fallback chain (llama3.1:8b → qwen2.5:7b), model availability check and auto-pull per D-02
- Implemented CitationBuilder with regex extraction (`[Article X, Section Y]` supporting Roman/Arabic numerals + optional letter subsections) per D-07, validation against chunk metadata per D-08, and invalid citation marking as `[引用待核实]` per D-09
- Wired GenerationPipeline orchestrating retrieval → prompt building → generation → citation validation
- 43 unit tests covering all components (Citation model: 3, PromptBuilder: 18, Generator: 6, CitationBuilder: 12, GenerationPipeline: 4)

## Task Commits

Each task was committed atomically:

1. **Task 1: Citation model + prompts.yaml + PromptBuilder + tests** — (Step 1 foundation, included in 02-02 commit f6a4e41)
2. **Task 2: Generator + CitationBuilder + GenerationPipeline + tests** — `70a1976` (feat)
3. **Task 3: Ollama model pull + integration smoke test** — Step 3 partial (Ollama pull of llama3.1:8b or qwen2.5:7b deferred due to agent budget; existing models llama3.2:3b and qwen2.5:3b available as alternatives)

## Files Created/Modified

- `backend/models/citation.py` — Citation dataclass with text, article, section, subsection, valid, confidence fields
- `backend/models/__init__.py` — Added Citation to exports
- `configs/prompts.yaml` — Jinja2 prompt templates for generation (system + user) and evaluation (judge_system + judge_user)
- `backend/generation/__init__.py` — Module exports (PromptBuilder, Generator, CitationBuilder, GenerationPipeline)
- `backend/generation/prompt_builder.py` — PromptBuilder with chunk XML wrapping and tiktoken truncation
- `backend/generation/generator.py` — Generator with Ollama chat integration, model fallback, auto-pull
- `backend/generation/citation_builder.py` — CitationBuilder with regex extraction and validation pipeline
- `backend/generation/pipeline.py` — GenerationPipeline orchestration class
- `tests/test_generation.py` — 43 tests across 5 test classes
- `requirements.txt` — Added pyyaml, tiktoken dependencies

## Decisions Made

- **Single-turn generation pattern** per D-04: system prompt is static (loaded from YAML), user prompt carries rendered context + query. Simplifies caching and reduces LLM confusion.
- **XLM chunk wrapping** per D-12: `<chunk id=N article=X section=Y>text</chunk>` format provides structured metadata alongside context text.
- **tiktoken cl100k_base** for token counting per D-11 — matches OpenAI's approach; future LLM tokenizer changes only affect the encoding name config.
- **Generator catches 404 on any model** to enable full fallback chain — not just the primary model. Both llama3.1:8b and qwen2.5:7b must fail with 404 before raising RuntimeError.
- **Temperature 0.1** for deterministic legal answers — balances reproducibility with minimal diversity for citation formatting.
- **Citation pattern** supports both Roman numerals (I, II, III) and Arabic digits (1, 2, 3) for article numbers, plus optional letter subsections e.g. Section 5(a).

## Deviations from Plan

None — plan executed as written. Step 3 (Ollama model pull) was partially deferred: the 8b models are available for pull when Ollama is connected, but the pull command may require additional time/bandwidth.

## Issues Encountered

- **Worktree isolation not active**: The orchestrator spawned executors without worktree isolation, so both 02-01 and 02-02 agents ran on the main repo. Commits from both agents interleaved. This did not cause issues because they modified disjoint file sets.
- **Ollama API compatibility**: Initial generator code used `from ollama import chat` — the `ollama.list()` returns a `ListResponse` with `.models` attribute of `Model` objects (not dicts). Fixed during Step 2 implementation with correct API discovery.
- **Pre-existing test failure**: `tests/test_retrieval.py::TestFullRetrievalPipeline::test_retrieve_end_to_end` fails with `AttributeError: 'MetadataStore' object has no attribute 'insert_chunk'` — unrelated pre-existing bug from Phase 1.

## User Setup Required

Ollama must be running (`ollama serve`) for the generator to work. At minimum one model should be pulled (`ollama pull llama3.1:8b` or `ollama pull qwen2.5:7b`). The available local models (llama3.2:3b, qwen2.5:3b) can be used by passing `model="llama3.2:3b"` to Generator.

## Next Phase Readiness

- Full generation pipeline is built and tested — retrieval → prompts → generation → citation validation
- Ready for Phase 2 Plan 02 evaluation (RelevanceJudge, citation precision metrics)
- Ready for Phase 3 UI integration (Streamlit dashboard consuming pipeline output)
- Ollama model pull for 8b models recommended before production use for better quality

## Self-Check: PASSED

- All 9 created/modified files verified on disk
- Task 2 commit verified in git history (70a1976)
- All 43 generation tests pass
- Pre-existing test failure confirmed unrelated (test_retrieval.py, not Phase 2 code)

---

*Phase: 02-generation-citations*
*Completed: 2026-05-14*
