# Phase 2: Generation & Citations - Context

**Gathered:** 2026-05-12
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers LLM-powered answer generation with legal citation support for LegalRAG. It includes:
- Ollama LLM integration (local, privacy-preserving)
- Prompt engineering with citation instructions
- Answer generation with structured citations
- Citation validation and extraction
- Evaluation metrics for citation accuracy and answer relevance

The output is a generation pipeline that takes user queries + retrieved chunks and produces natural language answers with verifiable legal citations.

</domain>

<decisions>
## Implementation Decisions

### LLM Model Selection
- **D-01:** Use Llama3.1:8b (Q4_K_M quantized) — optimal balance of CPU performance and legal reasoning quality
- **D-02:** Fallback model: qwen2.5:7b if Llama3.1 unavailable — both support standard Ollama API
- **D-03:** Pull command: `ollama pull llama3.1:8b` — Q4_K_M quantization for ~5GB memory footprint

### Prompt Engineering Strategy
- **D-04:** Single-turn generation (not multi-turn) — reduces latency, simplifies debugging
- **D-05:** System prompt defines citation rules explicitly — "每个事实后必须标注引用：[Article X, Section Y]"
- **D-06:** Prompt templates stored in `configs/prompts.yaml` — externalized for non-dev tuning

### Citation Format & Validation
- **D-07:** Inline format `[Article X, Section Y]` — matches legal document reading patterns
- **D-08:** Post-processing validation: extract citations via regex, verify against retrieved chunk metadata
- **D-09:** Invalid citations marked as `[引用待核实]` — graceful degradation for false positives

### Context Assembly
- **D-10:** Include top-5 chunks (post-reranking) — balance of information density and token budget
- **D-11:** Context window: 4096 tokens — enough for answer quality, fast enough for CPU
- **D-12:** XML chunk wrapping with metadata: `<chunk id="N" article="..." section="...">` — helps LLM identify boundaries

### Evaluation Approach
- **D-13:** Citation Precision metric: valid_citations / total_citations — target >80%
- **D-14:** LLM-as-Judge: 1-5 scale for relevance — accuracy, completeness, citation adequacy
- **D-15:** Reuse Phase 1 test queries (20-30) with manual citation annotations

### Agent's Discretion
- Exact tokenization strategy for context truncation
- Specific regex patterns for citation extraction
- Error handling specifics for Ollama connection failures

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — Project overview, core value, constraints
- `.planning/REQUIREMENTS.md` — Full requirements with REQ-IDs (GEN-01~05, EVAL-03~04)
- `.planning/ROADMAP.md` — Phase 2 success criteria and technical notes

### Prior Phase Context
- `.planning/phases/01-core-retrieval-engine/01-CONTEXT.md` — Phase 1 decisions (Chunk model, retrieval pipeline)

### Architecture Reference
- `architecture.md` — System architecture and data flow
- `ref.md` — RAG landscape analysis

### No External Specs
No external specifications — requirements fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/models/chunk.py`: Chunk dataclass with article, section, subsection, title, parent_article — already has citation-relevant metadata
- `backend/retrieval/hybrid_search.py`: HybridSearch class returns (chunk_id, score) tuples — can be reused for chunk fetching
- `backend/storage/metadata_store.py`: MetadataStore.get_chunks(chunk_ids) — retrieves full chunk objects

### Established Patterns
- D-15 (Phase 1): Alpha weighting 0.7 vector / 0.3 BM25 — consistent with retrieval
- D-18 (Phase 1): Top-10 before reranking, top-5 after — generation uses post-rerank chunks
- SQLite schema includes article/section/subsection columns — citation extraction can query metadata

### Integration Points
- Generation consumes: query + top-5 chunk IDs + chunk texts/metadata
- Generation produces: answer text + extracted citations
- Phase 3 (UI) will display generated answers with citation formatting

</code_context>

<specifics>
## Specific Ideas

Based on discussion:
- Citation format: `[Article I, Section 1]` (Roman numeral + Arabic section)
- Prompt must explicitly forbid fabricating citations ("如上下文不足，明确说明")
- Evaluation threshold: >80% citation precision (from ROADMAP.md)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. All Phase 2 requirements are committed.

</deferred>

---

*Phase: 2-Generation & Citations*
*Context gathered: 2026-05-12*