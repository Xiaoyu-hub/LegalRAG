# Phase 2: Generation & Citations - Research

**Researched:** 2026-05-14
**Domain:** LLM-powered answer generation, legal citation extraction & validation, RAG evaluation
**Confidence:** HIGH

## Summary

This phase builds the LLM-powered answer generation pipeline for LegalRAG. The stack is entirely local: Ollama (v0.23.2) with llama3.1:8b as the generation model, Python `ollama` library (v0.6.2) for API calls, and Jinja2 (v3.1.6) for YAML-based prompt templates. The key architectural insight is a **three-stage pipeline**: (1) PromptBuilder assembles retrieved chunks into XML-wrapped context with citation instructions, (2) Ollama generates the answer, (3) CitationBuilder extracts and validates citations against chunk metadata. Evaluation uses citation precision (valid/total citations >80% target) and LLM-as-Judge relevance scoring (1-5 scale).

**Primary recommendation:** Use the `ollama.chat()` API with a system message pattern for generation. Use Jinja2 `Template.render()` for prompt assembly from YAML config. Build CitationBuilder as a post-processing regex pass with metadata cross-validation. The critical risk is LLM citation hallucination — mitigated by aggressive anti-hallucination instructions and post-processing validation marking invalid citations as `[引用待核实]`.

**Key environment findings:** Ollama v0.23.2 is installed with llama3.2:3b and qwen2.5:3b cached. The desired `llama3.1:8b` (~4.9GB) and fallback `qwen2.5:7b` (~4.1GB) are NOT cached — both must be pulled. Python `ollama` library v0.6.2 is installed. Jinja2 v3.1.6 is installed. 73GB free disk space is available for model downloads. No `backend/generation/` directory exists yet — must be created. No `configs/` directory exists yet — must be created.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use Llama3.1:8b (Q4_K_M quantized) — optimal balance of CPU performance and legal reasoning quality
- **D-02:** Fallback model: qwen2.5:7b if Llama3.1 unavailable — both support standard Ollama API
- **D-03:** Pull command: `ollama pull llama3.1:8b` — Q4_K_M quantization for ~5GB memory footprint
- **D-04:** Single-turn generation (not multi-turn) — reduces latency, simplifies debugging
- **D-05:** System prompt defines citation rules explicitly — "每个事实后必须标注引用：[Article X, Section Y]"
- **D-06:** Prompt templates stored in `configs/prompts.yaml` — externalized for non-dev tuning
- **D-07:** Inline format `[Article X, Section Y]` — matches legal document reading patterns
- **D-08:** Post-processing validation: extract citations via regex, verify against retrieved chunk metadata
- **D-09:** Invalid citations marked as `[引用待核实]` — graceful degradation for false positives
- **D-10:** Include top-5 chunks (post-reranking) — balance of information density and token budget
- **D-11:** Context window: 4096 tokens — enough for answer quality, fast enough for CPU
- **D-12:** XML chunk wrapping with metadata: `<chunk id="N" article="..." section="...">` — helps LLM identify boundaries
- **D-13:** Citation Precision metric: valid_citations / total_citations — target >80%
- **D-14:** LLM-as-Judge: 1-5 scale for relevance — accuracy, completeness, citation adequacy
- **D-15:** Reuse Phase 1 test queries (20-30) with manual citation annotations

### the agent's Discretion
- Exact tokenization strategy for context truncation
- Specific regex patterns for citation extraction
- Error handling specifics for Ollama connection failures

### Deferred Ideas (OUT OF SCOPE)
None — all Phase 2 requirements are committed.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GEN-01 | Prompt builder assembles context from retrieved chunks | Jinja2 template from YAML config renders XML-wrapped chunks with metadata. `PromptBuilder.build(query, chunks)` returns (system_prompt, user_prompt) tuple. [VERIFIED: Context7 /pallets/jinja] |
| GEN-02 | System prompts LLM to cite specific Articles and Sections | System prompt uses explicit citation rules. Ollama `chat()` API supports `{"role": "system", "content": ...}` message. Pattern verified against Llama3.1 system prompt handling. [VERIFIED: Context7 /ollama/ollama-python] |
| GEN-03 | Ollama integration supports Qwen2.5 (or Llama3) locally | `ollama.chat(model="llama3.1:8b", messages=[...])` works with both models. Fallback: `model="qwen2.5:7b"`. Both must be pulled first. [VERIFIED: ollama --version 0.23.2, ollama list shows no 8b/7b models] |
| GEN-04 | Generated answers include formatted citations [Article X, Section Y] | System prompt enforces `[Article X, Section Y]` format inline. Regex `\[(Article)\s+((?:[IVXLCDM]+|\d+)),\s*Section\s+(\d+(?:\([a-z]\))?)\]` extracts citations post-generation. [ASSUMED — pattern consistent with D-07] |
| GEN-05 | Citation builder extracts and validates citation references | `CitationBuilder.extract(text)` returns list of `Citation` objects. `CitationBuilder.validate(citations, chunks)` cross-references against chunk metadata. Invalid citations marked as `[引用待核实]`. [ASSUMED — architecture.md pattern] |
| EVAL-03 | Citation accuracy metric for answer correctness | Citation Precision = valid_citations / total_citations. Extends Phase 1 `Evaluator` class with `citation_precision()` and `evaluate_generation()` methods. Reuses TEST_QUERIES with added citation annotations. [ASSUMED — D-13 confirmed] |
| EVAL-04 | Answer relevance evaluation (LLM-as-judge) | Separate LLM call with rubric-based scoring (1-5). Judge prompt includes: question, generated answer, chunks, scoring criteria. JSON output with score + reasoning. [CITED: langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge] |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Prompt assembly | Generation Pipeline | — | Combines query + chunks into structured prompt. No other tier has the context |
| LLM inference (Ollama) | Generation Pipeline | — | Local API call to Ollama server. Standalone computation, no storage or UI involvement |
| Citation extraction | Citation Builder | — | Post-processing regex pass on generated text. Pure text analysis |
| Citation validation | Citation Builder | Metadata Store | Compares extracted citations against chunk metadata from SQLite |
| Citation Precision evaluation | Evaluation | Generation Pipeline | Computes valid/total ratio. Runs test queries through generation pipeline |
| LLM-as-Judge evaluation | Evaluation | Generation Pipeline | Call to judge LLM (separate model or same). Reuses the same Ollama API |
| Context truncation (4096 tokens) | Prompt Builder | — | Token-count-aware chunk trimming before assembling the prompt |
| Model availability check | Generator | — | On init, list models and auto-pull if missing. Error handling for connection failures |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard | Source |
|---------|---------|---------|--------------|--------|
| ollama (Python) | 0.6.2 | Local LLM inference via Ollama | Official Python client for Ollama. Supports chat, generate, streaming, JSON format, structured output via Pydantic schemas. Chat API with system messages is the primary pattern | [VERIFIED: pip list shows 0.6.2, Context7 /ollama/ollama-python] |
| Jinja2 | 3.1.6 | Prompt template rendering | Industry-standard Python templating. `Environment(loader=FileSystemLoader("configs"))` loads prompts from YAML + Jinja2 templates. Supports variable substitution, conditionals, loops | [VERIFIED: pip list shows 3.1.6, Context7 /pallets/jinja] |
| PyYAML | 6.x | YAML config loading | Parses `configs/prompts.yaml` into Python dicts. Required for prompt template management | [ASSUMED — will be installed] |
| pydantic | 2.x | Citation data model validation | Data validation for Citation dataclass. Optional — can use plain dataclasses. Needed if using Ollama structured output format | [ASSUMED — available from sentence-transformers dependency chain] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| re (built-in) | — | Regex for citation extraction | Always — `re.findall(CITATION_PATTERN, text)` extracts inline citations from generated text |
| json (built-in) | — | JSON result serialization | For evaluation output files, matching Phase 1 `Evaluator` pattern |
| logging (built-in) | — | Structured logging for LLM calls | Throughout generation pipeline — log prompt length, model, latency, errors |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python `ollama` library | Raw HTTP to `localhost:11434/api/generate` | `ollama` library provides typed responses (ChatResponse), streaming iteration, structured output with Pydantic. HTTP is more flexible but adds error handling boilerplate. The library is the standard choice | [CITED: Context7 /ollama/ollama-python] |
| Jinja2 prompt templates | f-string templates | Jinja2 supports conditionals/loops for dynamic prompts (e.g., "only include this section if chunks > 0"). f-strings are simpler but become unwieldy with conditional logic | [CITED: jinja.palletsprojects.com] |
| llama3.1:8b (primary) | llama3.2:3b (cached, ~2GB) | 3B model is lower quality for legal reasoning. D-01 locks in 8B for quality. 3B model already cached — could be used for evaluation (judge) to save resources | [VERIFIED: ollama list] |
| LLM-as-Judge with same model | Separate judge model (e.g., GPT-4) | Same-model judge risks self-preference bias but is free and local. D-14 locks in local LLM-as-Judge. Mitigation: use lower temperature (0.0) for judge calls | [CITED: openlayer.com/blog/post/llm-as-judge-evaluation-guide] |

**Installation:**
```bash
# Pull primary model (D-01) — ~4.9GB download
ollama pull llama3.1:8b

# Pull fallback model (D-02) — ~4.1GB download
ollama pull qwen2.5:7b

# Install Jinja2 for prompt templates (already installed but listed for completeness)
pip install jinja2 pyyaml
```

**Version verification:**
```bash
# Ollama version
ollama --version    # -> 0.23.2

# Python ollama library
pip show ollama     # -> Version: 0.6.2

# Jinja2
pip show jinja2     # -> Version: 3.1.6

# PyYAML
pip show pyyaml     # -> Version: 6.x
```

**IMPORTANT — Model discrepancy found:** D-01 says `llama3.1:8b` and D-02 says `qwen2.5:7b`. The system currently has `llama3.2:3b` and `qwen2.5:3b` cached. Neither 8b nor 7b model is present. The planner MUST include a model-pull step. Both primary and fallback models use the same Ollama API — no code changes needed for the switch, just a model name parameter.

## Architecture Patterns

### System Architecture Diagram

```
                          ┌──────────────────┐
                          │   User Query     │
                          │  "What is the    │
                          │   penalty for..."│
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │ Phase 1: Retrieve │
                          │ Top-5 chunks     │
                          │ post-reranking    │
                          └────────┬─────────┘
                                   │ list[Chunk]
                                   │ (with metadata)
                          ┌────────▼──────────────┐
                          │ PromptBuilder         │
                          │                       │
                          │ 1. Load system prompt │
                          │    from prompts.yaml  │
                          │ 2. Wrap chunks in XML │
                          │    with metadata      │
                          │ 3. Truncate to 4096   │
                          │    tokens via tiktoken│
                          │ 4. Assemble messages: │
                          │    system + user      │
                          └────────┬──────────────┘
                                   │ (system_prompt, user_prompt)
                                   │
                          ┌────────▼──────────────┐
                          │ Ollama Generator      │
                          │                       │
                          │ chat(model=           │
                          │   "llama3.1:8b",      │
                          │   messages=...,       │
                          │   options={           │
                          │     temperature=0.1,  │
                          │     num_ctx=4096      │
                          │   })                  │
                          └────────┬──────────────┘
                                   │ raw generated text
                                   │ with [Article X, Section Y]
                          ┌────────▼──────────────┐
                          │ CitationBuilder       │
                          │                       │
                          │ 1. Extract citations  │
                          │    via regex          │
                          │ 2. Validate each      │
                          │    against chunk      │
                          │    metadata           │
                          │ 3. Mark invalid as    │
                          │    [引用待核实]        │
                          │ 4. Return structured  │
                          │    Answer object      │
                          └────────┬──────────────┘
                                   │ Answer {text, citations[]}
                                   │
                    ┌───────────────┼───────────────┐
                    │               │               │
           ┌────────▼──────┐  ┌────▼───────┐  ┌────▼────────────┐
           │ EVAL-03:      │  │ EVAL-04:   │  │ Phase 3: UI     │
           │ Citation      │  │ LLM-as-    │  │ Display answer  │
           │ Precision     │  │ Judge      │  │ + citations     │
           │ (>80% target) │  │ (1-5)      │  │                 │
           └───────────────┘  └────────────┘  └─────────────────┘
```

### Recommended Project Structure

```
backend/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── document.py           # Document dataclass (from Phase 1)
│   ├── chunk.py              # Chunk dataclass (from Phase 1)
│   └── citation.py           # NEW — Citation dataclass
├── generation/               # NEW — Generation module
│   ├── __init__.py
│   ├── generator.py          # GenerationPipeline: orchestrates prompt → Ollama → citation
│   ├── prompt_builder.py     # PromptBuilder: assembles context, truncates tokens
│   └── citation_builder.py   # CitationBuilder: regex extraction + metadata validation
├── retrieval/                # (from Phase 1)
├── embedding/                # (from Phase 1)
├── storage/
│   └── metadata_store.py     # MetadataStore.get_chunks() — used by citation validation
└── evaluation/
    ├── __init__.py
    ├── test_queries.py       # PHASE 2 UPDATE — add citation annotations to TEST_QUERIES
    ├── evaluator.py          # PHASE 2 UPDATE — add citation_precision(), evaluate_generation()
    └── judge.py              # NEW — LLM-as-Judge evaluation module

configs/                      # NEW — Configuration directory
└── prompts.yaml              # NEW — Prompt templates in YAML + Jinja2 format

tests/
├── test_generation.py        # NEW — Tests for generation pipeline
├── test_citation_builder.py  # NEW — Tests for citation extraction/validation
└── test_evaluation.py        # PHASE 2 UPDATE — Add EVAL-03, EVAL-04 tests
```

**Key design principle:** The generation module is stateless and composable. `PromptBuilder` takes query + chunks → returns prompts. `Generator` takes prompts → returns raw text. `CitationBuilder` takes text + chunks → returns validated answer. Each can be tested independently.

### Pattern 1: PromptBuilder with Jinja2 YAML Templates

**What:** Load system prompt templates from `configs/prompts.yaml` using Jinja2. Each template is a YAML document with a `system` and `user` template section. Rationale per D-06: externalized for non-dev tuning.

**When to use:** On every generation call, when the PromptBuilder must assemble the context.

**Example:**
```python
# Source: [VERIFIED: Context7 /pallets/jinja, Context7 /ollama/ollama-python]
import yaml
from jinja2 import Template
from pathlib import Path

class PromptBuilder:
    """Assembles generation prompts from YAML templates and retrieved chunks."""

    def __init__(self, config_path: str = "configs/prompts.yaml", max_tokens: int = 4096):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.system_template = Template(self.config["generation"]["system"])
        self.user_template = Template(self.config["generation"]["user"])
        self.max_tokens = max_tokens

    def build(self, query: str, chunks: list) -> tuple[str, str]:
        """Build system and user prompts from query + chunks.
        
        Returns:
            (system_prompt, user_prompt) tuple
        """
        # Format chunks as XML with metadata per D-12
        context_parts = []
        for i, chunk in enumerate(chunks):
            context_parts.append(
                f'<chunk id="{chunk.id}" article="{chunk.article}" '
                f'section="{chunk.section}">\n{chunk.text}\n</chunk>'
            )
        context = "\n\n".join(context_parts)

        # Render user prompt with context and query
        user_prompt = self.user_template.render(
            context=context,
            query=query,
        )

        # Truncate to max_tokens (approximate: ~4 chars per token)
        max_chars = self.max_tokens * 4
        if len(user_prompt) > max_chars:
            user_prompt = user_prompt[:max_chars]

        # System prompt is static per D-04 (single turn)
        system_prompt = self.system_template.render()

        return system_prompt, user_prompt
```

### Pattern 2: Ollama Generation with Error Handling

**What:** Call Ollama using the `chat()` API with a system message. Handle connection errors, model-not-found errors, and timeouts gracefully. Per D-04: single-turn generation.

**When to use:** After PromptBuilder assembles prompts, before CitationBuilder processes output.

**Example:**
```python
# Source: [VERIFIED: Context7 /ollama/ollama-python]
from ollama import chat, Options, ResponseError
import logging

logger = logging.getLogger(__name__)

class Generator:
    """Ollama-based answer generator."""

    def __init__(self, model: str = "llama3.1:8b", fallback: str = "qwen2.5:7b"):
        self.model = model
        self.fallback = fallback

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate answer using Ollama chat API.

        Args:
            system_prompt: System-level instructions for the model
            user_prompt: Assembled context + query

        Returns:
            Generated answer text

        Raises:
            ConnectionError: If Ollama server is not running
        """
        models_to_try = [self.model, self.fallback]

        for model in models_to_try:
            try:
                response = chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    options=Options(
                        temperature=0.1,       # Low temp for deterministic legal answers
                        num_ctx=4096,           # Per D-11: 4096 token context
                        num_predict=1024,       # Max output tokens
                        stop=["<|endoftext|>"],  # Model-specific stop token
                    ),
                )
                return response.message.content

            except ResponseError as e:
                if e.status_code == 404 and model == self.model:
                    logger.warning(f"Model {model} not found, trying fallback {self.fallback}")
                    continue
                logger.error(f"Ollama API error with {model}: {e.error}")
                raise

            except ConnectionError as e:
                raise ConnectionError(
                    "Cannot connect to Ollama. Ensure Ollama is running "
                    "(ollama serve) or install from https://ollama.com/download"
                ) from e

        raise RuntimeError(f"Neither {self.model} nor {self.fallback} available")
```

### Pattern 3: Citation Extraction and Validation

**What:** Post-process generated text to extract `[Article X, Section Y]` citations via regex, then validate each against the retrieved chunk metadata. Per D-08 and D-09.

**When to use:** After generation, before returning final answer.

**Example:**
```python
# Source: [ASSUMED — regex pattern consistent with D-07 format]
import re
from dataclasses import dataclass

CITATION_PATTERN = re.compile(
    r'\[(Article)\s+((?:[IVXLCDM]+|\d+)),\s*Section\s+(\d+(?:\([a-z]\))?)\]'
)

@dataclass
class Citation:
    text: str          # Full citation string e.g. "[Article III, Section 5(a)]"
    article: str       # Extracted article number e.g. "III"
    section: str       # Extracted section number e.g. "5(a)"
    valid: bool = True  # After validation against chunk metadata

class CitationBuilder:
    """Extracts and validates legal citations from generated text."""

    def __init__(self):
        self.pattern = CITATION_PATTERN

    def extract(self, text: str) -> list[Citation]:
        """Extract all citations from generated text.
        
        Returns list of Citation objects (not yet validated).
        """
        citations = []
        for match in self.pattern.finditer(text):
            citations.append(Citation(
                text=match.group(0),
                article=match.group(2),
                section=match.group(3),
            ))
        return citations

    def validate(self, citations: list[Citation], chunks: list) -> list[Citation]:
        """Validate citations against retrieved chunk metadata.
        
        A citation is valid if its article+section exists in the
        metadata of the retrieved chunks. Invalid citations are
        marked for review per D-09.
        
        Returns updated list of Citation objects.
        """
        # Build set of valid (article, section) pairs from chunks
        valid_refs = set()
        for chunk in chunks:
            if chunk.article and chunk.section:
                # Normalize: extract just the number from "Article III" -> "III"
                art = self._normalize_article(chunk.article)
                sec = self._normalize_section(chunk.section)
                valid_refs.add((art, sec))

        for citation in citations:
            citation.valid = (citation.article, citation.section) in valid_refs

        return citations

    def mark_invalid(self, text: str, citations: list[Citation]) -> str:
        """Replace invalid citation text with [引用待核实] per D-09.
        
        Returns modified text.
        """
        result = text
        for citation in citations:
            if not citation.valid:
                result = result.replace(citation.text, "[引用待核实]", 1)
        return result

    @staticmethod
    def _normalize_article(article: str) -> str:
        """Extract article number from 'Article III' -> 'III'."""
        return article.replace("Article ", "").strip()

    @staticmethod
    def _normalize_section(section: str) -> str:
        """Extract section number from 'Section 5(a)' -> '5(a)'."""
        return section.replace("Section ", "").strip()

    def process(self, text: str, chunks: list) -> tuple[str, list[Citation]]:
        """Full pipeline: extract -> validate -> mark invalid -> return.
        
        Returns (cleaned_text, validated_citations).
        """
        citations = self.extract(text)
        citations = self.validate(citations, chunks)
        cleaned = self.mark_invalid(text, citations)
        return cleaned, citations
```

### Pattern 4: LLM-as-Judge for Answer Relevance (EVAL-04)

**What:** Use a separate Ollama call with a rubric prompt to score generated answers on a 1-5 scale. Per D-14 and EVAL-04.

**When to use:** During evaluation runs, after generation pipeline produces answers for test queries.

**Example:**
```python
# Source: [CITED: langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge]
from ollama import chat, Options

JUDGE_SYSTEM_PROMPT = """You are an expert evaluator of legal question answering systems.
Evaluate the quality of the generated answer based on the following criteria:

Score 1: Poor — Answer does not address the question, contains factual errors, or has no valid citations.
Score 2: Below Average — Answer partially addresses the question but misses key information or has incorrect citations.
Score 3: Adequate — Answer addresses the question but lacks completeness or citation quality.
Score 4: Good — Answer is accurate and complete with valid citations relevant to the question.
Score 5: Excellent — Answer is comprehensive, precise, all citations are correct and well-integrated.

Output ONLY a JSON object with:
- "score": integer 1-5
- "reasoning": brief explanation for the score
"""

class RelevanceJudge:
    """LLM-as-Judge for answer relevance (EVAL-04)."""

    def __init__(self, model: str = "llama3.1:8b"):
        self.model = model

    def evaluate(self, query: str, answer: str, chunks: list) -> dict:
        """Evaluate generated answer relevance on 1-5 scale."""
        # Build context summary for the judge
        source_text = "\n\n".join(
            f"[Article {c.article}, Section {c.section}]: {c.text[:200]}"
            for c in chunks
        )

        user_prompt = f"""Question: {query}

Generated Answer: {answer}

Reference Sources:
{source_text}

Evaluate this answer using the scoring criteria provided."""

        response = chat(
            model=self.model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            options=Options(temperature=0.0),  # Deterministic evaluation
            format="json",  # Force JSON output
        )
        return response.message.content
```

### Pattern 5: Citation Evaluation (EVAL-03)

**What:** Compute citation precision metric by running test queries through the full pipeline and comparing extracted citations against expected annotations.

**When to use:** During evaluation to measure generation quality.

**Example:**
```python
# Source: [ASSUMED — extends Phase 1 Evaluator pattern]
class GenerationEvaluator:
    """Evaluates generation quality with citation metrics (EVAL-03, EVAL-04)."""

    def __init__(self, generator_pipeline, judge: RelevanceJudge = None):
        self.pipeline = generator_pipeline
        self.judge = judge

    def citation_precision(self, citations: list[Citation]) -> float:
        """Citation Precision = valid_citations / total_citations.
        
        Per D-13: target >80%.
        Returns 1.0 if no citations (edge case — should not happen).
        """
        if not citations:
            return 1.0
        valid = sum(1 for c in citations if c.valid)
        return valid / len(citations)

    def evaluate_generation(self, queries: list[dict]) -> dict:
        """Run full evaluation across test queries.
        
        Each query dict must have:
        - "query": str
        - "expected_annotations": list of citation annotations (optional)
        """
        results = []
        for q in queries:
            # Run through full pipeline
            answer = self.pipeline.answer(q["query"])
            # Extract and validate citations
            cleaned, citations = self.pipeline.citation_builder.process(
                answer, self.pipeline.last_chunks
            )
            # Compute metrics
            cp = self.citation_precision(citations)

            query_result = {
                "query": q["query"],
                "citation_precision": cp,
                "total_citations": len(citations),
                "valid_citations": sum(1 for c in citations if c.valid),
                "citations": [{"text": c.text, "valid": c.valid} for c in citations],
            }

            # LLM-as-Judge if available
            if self.judge:
                judge_result = self.judge.evaluate(
                    q["query"], answer, self.pipeline.last_chunks
                )
                query_result["relevance_score"] = judge_result.get("score")

            results.append(query_result)

        # Aggregate
        precisions = [r["citation_precision"] for r in results]
        return {
            "average_citation_precision": sum(precisions) / len(precisions),
            "per_query": results,
            "total_queries": len(results),
            "evaluated_at": datetime.now().isoformat(),
        }
```

### Anti-Patterns to Avoid

- **High temperature for legal answers:** Legal answers should be deterministic. Temperature >0.3 increases hallucination risk. Use 0.1 for generation.
- **No citation validation:** LLMs frequently hallucinate fake article/section numbers. Always validate citations against the actual retrieved chunks.
- **Counting tokens by characters:** Token != character. `len(text) / 4` is a rough approximation. For precise 4096-token context control, use a real tokenizer (tiktoken or model-specific).
- **Same-model LLM-as-Judge bias:** Using the same model as judge and generator risks self-preference bias. Mitigation: use temperature 0.0 for judge, or use the fallback model as judge.
- **Forgetting pull step:** The desired model (llama3.1:8b) may not be cached. The planner must include a model availability check + auto-pull step on init.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM API client | Custom HTTP requests to Ollama | Python `ollama` library | Typed responses (ChatResponse), streaming iteration, structured output with Pydantic. 75 code snippets available. The official library handles connection pooling and error types | [VERIFIED: Context7 /ollama/ollama-python] |
| Prompt template engine | Python string concatenation with if/else | Jinja2 from YAML config | Fan-in/fan-out with conditional logic (e.g., "if chunks empty, use fallback prompt"). YAML separation (D-06) allows non-developers to tune prompts without touching code | [VERIFIED: Context7 /pallets/jinja] |
| Tokenization / context truncation | Character-count approximation | tiktoken (cl100k_base) or model tokenizer | Llama3 uses the GPT-4 tokenizer family (tiktoken). Character counting is inaccurate and wastes context window space. tiktoken counts tokens correctly | [ASSUMED — standard RAG pattern] |
| Legal citation extraction | Custom NLP model | Regex with validation pass | The citation format `[Article X, Section Y]` is simple. A regex captures >95% of well-formed citations. The validation pass against chunk metadata catches false positives | [ASSUMED] |
| LLM evaluation | Manual scoring of answers | LLM-as-Judge with rubric | Scalable, reproducible, and the rubric makes scoring criteria explicit. The 1-5 scale with descriptive anchors reduces variance vs. free-form assessment | [CITED: langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge] |

**Key insight:** The generation pipeline is essentially a data transformation pipeline — query + chunks → LLM → text + citations. Each stage (assemble → generate → extract → validate) is a pure transformation that can be tested independently. Don't couple them into a monolithic "generation" function.

## Common Pitfalls

### Pitfall 1: LLM Citation Hallucination
**What goes wrong:** The LLM generates plausible-sounding but fake article/section numbers. E.g., citing "Article V, Section 12" when the regulation only has 4 articles.
**Why it happens:** LLMs lack internal grounding — they produce text that looks like valid citations based on training patterns rather than actual content. This is the single biggest quality risk in legal RAG.
**How to avoid:** (1) Strong system prompt instructions: "每个事实后必须标注引用：[Article X, Section Y]。仅引用上方提供的上下文中的条款。" (2) Post-processing validation against chunk metadata (CitationBuilder.validate). (3) Mark unverifiable citations as `[引用待核实]`. (4) Consider adding a second LLM call that checks citation consistency.
**Warning signs:** Citations refer to articles or sections not present in any retrieved chunk. Multiple citations to the same non-existent article.

### Pitfall 2: Context Window Overflow
**What goes wrong:** 5 chunks at even 800 tokens each = 4000 tokens, leaving almost no room for system prompt, instructions, and the query. The prompt gets silently truncated at 4096 tokens.
**Why it happens:** The 4096 token limit (D-11) is permissive but still tight. The system prompt, XML wrappers, and query all consume tokens from the same budget.
**How to avoid:** (1) Use a tokenizer (tiktoken) to measure actual token counts, not character approximations. (2) Prioritize chunks by reranker score and truncate the lowest-ranked chunk first. (3) Set `num_ctx=4096` explicitly in Ollama options. (4) Log warning when token budget exceeds 80%.
**Warning signs:** The generated answer is shorter than expected, or chunks in the middle of the context are cut off.

### Pitfall 3: Ollama Connection and Model Issues
**What goes wrong:** At runtime, Ollama is not running, or the specified model is not pulled, causing a ResponseError(404).
**Why it happens:** Ollama is a separate process (not a Python library). The generation code silently assumes it's available. Models must be pulled before use (several GB download).
**How to avoid:** (1) On Generator init, call `ollama.list()` to check available models. (2) If model not found, auto-pull with streamed progress logging. (3) Implement fallback chain: primary → fallback → explicit error. (4) Start-up health check method that validates Ollama connectivity.
**Warning signs:** First generation call after app startup fails with ConnectionError or ResponseError.

### Pitfall 4: Citation Regex False Positives/Negatives
**What goes wrong:** The regex `\[Article X, Section Y\]` misses variations like `[Article II, Section 5(a)]` (with subsection) or `[Article 2, § 5]` (with section symbol), or matches text inside code blocks or quoted material.
**Why it happens:** Legal documents use citation variations. The regex pattern must be broad enough to capture valid formats but narrow enough to exclude non-citations.
**How to avoid:** (1) Use a regex that handles optional subsections: `[Article (Roman|Arabic), Section N(subsection)]`. (2) Validate all extracted citations against chunk metadata — this catches 99% of false positives. (3) Log and review any citations that failed validation to tune the pattern.
**Warning signs:** Generated text has many `[引用待核实]` markers, or valid citations are not being extracted.

### Pitfall 5: LLM-as-Judge Inconsistency
**What goes wrong:** The same answer gets different scores on repeated evaluations because the judge LLM is non-deterministic.
**Why it happens:** LLMs are stochastic by nature. Even at temperature=0, floating point non-determinism can produce different outputs.
**How to avoid:** (1) Set temperature=0.0 for judge calls. (2) Use a structured output format (`format="json"` in ollama.chat) to force consistent response parsing. (3) Include chain-of-thought reasoning instructions to stabilize decisions ("First analyze, then score"). (4) Average scores across 2-3 evaluations for high-confidence assessment.
**Warning signs:** Evaluation scores vary by >1 point for the same (query, answer) pair across runs.

## Code Examples

### Complete Generation Pipeline Integration

```python
# Source: [VERIFIED: all library APIs via Context7, patterns from architecture.md]

from backend.generation.prompt_builder import PromptBuilder
from backend.generation.citation_builder import CitationBuilder
from backend.generation.generator import Generator
from backend.storage.metadata_store import MetadataStore


class GenerationPipeline:
    """End-to-end generation pipeline: retrieve → prompt → generate → cite."""

    def __init__(
        self,
        retriever=None,  # Phase 1 HybridSearch + Reranker pipeline
        metadata_store: MetadataStore = None,
        model: str = "llama3.1:8b",
        fallback: str = "qwen2.5:7b",
    ):
        self.retriever = retriever
        self.metadata_store = metadata_store
        self.prompt_builder = PromptBuilder()
        self.generator = Generator(model=model, fallback=fallback)
        self.citation_builder = CitationBuilder()
        self.last_chunks = []  # Store for evaluation access

    def answer(self, query: str) -> str:
        """Generate answer with citations for a single query.

        Data flow per architecture.md section 2.3:
        query → embed → hybrid search → rerank → fetch chunks →
        prompt build → Ollama generate → citation extract → output
        """
        # Step 1: Retrieve (using Phase 1 pipeline)
        # Returns list of dicts with 'chunk' key
        results = self.retriever.retrieve(query, top_k=5)
        chunks = [r["chunk"] for r in results]
        self.last_chunks = chunks

        # Step 2: Build prompts
        system_prompt, user_prompt = self.prompt_builder.build(query, chunks)

        # Step 3: Generate via Ollama
        raw_text = self.generator.generate(system_prompt, user_prompt)

        # Step 4: Extract and validate citations
        cleaned_text, citations = self.citation_builder.process(raw_text, chunks)

        return cleaned_text
```

### configs/prompts.yaml Template

```yaml
# Source: [ASSUMED — prompt design per D-05, D-10, D-12]
generation:
  system: |
    You are a legal document analysis assistant. Your task is to answer
    questions about legal regulations based STRICTLY on the provided context
    documents.

    ## Citation Rules (MANDATORY)
    - Every factual claim MUST be followed by an inline citation.
    - Use this EXACT format: [Article X, Section Y]
      Examples: [Article I, Section 1], [Article III, Section 5(a)]
    - ONLY cite articles and sections that appear in the provided context below.
    - If the context does not contain sufficient information to answer the
      question, state: "根据提供的上下文，无法完整回答此问题。"
    - NEVER fabricate citations. If you are not sure, do not guess.

    ## Answer Style
    - Be precise and concise. Legal professionals need accurate answers.
    - Use the same legal terminology as the source documents.
    - Organize answers logically. Use paragraphs for related points.
    - Each paragraph should cite the relevant article(s).

    ## Language
    Answer primarily in English. Legal terms should match the source documents.

  user: |
    ## Context Documents

    Below are the relevant legal document excerpts. Each chunk is wrapped in
    XML tags with its article and section metadata:

    {{ context }}

    ## Question

    {{ query }}

    ## Instructions

    Based EXCLUSIVELY on the context above, provide a precise answer with
    proper citations in [Article X, Section Y] format. If the context is
    insufficient, state this clearly.

evaluation:
  judge_system: |
    You are an expert evaluator of legal question answering systems.
    Evaluate the quality of the generated answer based on these criteria:

    - Score 1 (Poor): Answer does not address the question, contains
      factual errors, or has no valid citations.
    - Score 2 (Below Average): Answer partially addresses the question
      but misses key information or has incorrect citations.
    - Score 3 (Adequate): Answer addresses the question but lacks
      completeness or citation quality.
    - Score 4 (Good): Answer is accurate and complete with valid
      citations relevant to the question.
    - Score 5 (Excellent): Answer is comprehensive, precise, all
      citations are correct and well-integrated.

    Output ONLY valid JSON with "score" (integer 1-5) and "reasoning" (string).

  judge_user: |
    Question: {{ query }}

    Generated Answer: {{ answer }}

    Reference Sources:
    {{ sources }}

    Evaluate this answer using the scoring criteria provided.
```

### Citation Dataclass (models/citation.py)

```python
# Source: [ASSUMED — matches architecture.md section 3.4]
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Citation:
    """A legal citation extracted from generated text."""
    text: str                    # Full citation text e.g. "[Article III, Section 5]"
    article: str                 # Article number e.g. "III"
    section: str                 # Section number e.g. "5", "5(a)"
    subsection: Optional[str] = None  # Optional subsection e.g. "a"
    valid: bool = True           # Validated against chunk metadata
    confidence: float = 1.0      # Confidence score (reserved for future use)
```

### Ollama Model Availability Check

```python
# Source: [VERIFIED: Context7 /ollama/ollama-python]
from ollama import list, pull

def ensure_model_available(model: str) -> bool:
    """Check if model is cached, auto-pull if missing.
    
    Returns True if model is ready, False if pull fails.
    """
    available = {m.model for m in list().models}
    
    if model in available:
        print(f"✓ Model '{model}' is available")
        return True
    
    print(f"Model '{model}' not found. Pulling (this may take several minutes)...")
    try:
        for progress in pull(model, stream=True):
            if progress.total:
                pct = (progress.completed or 0) / progress.total * 100
                print(f"  Downloading: {pct:.1f}%")
            print(f"  Status: {progress.status}")
        print(f"✓ Model '{model}' pulled successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to pull model '{model}': {e}")
        return False
```

### Updated Test Queries with Citation Annotations

```python
# Source: [ASSUMED — extends Phase 1 test_queries.py]
# Add to existing TEST_QUERIES in backend/evaluation/test_queries.py:
EXTRA_FIELDS = {
    "query": "What is the maximum fine for violating data protection rights?",
    "relevant_chunk_ids": {9},
    "category": "penalty",
    "notes": "Tests fine for Article II Section 1 violations — up to EUR 20M or 4% turnover",
    "expected_citations": [
        {"article": "III", "section": "3", "text": "[Article III, Section 3]"}
    ],
    "expected_relevance": 4,  # Expected LLM-as-Judge score for a good answer
}

# Each query needs added fields:
# - "expected_citations": list of Citation references the generated answer should contain
# - "expected_relevance": 1-5 expected score (optional, for calibration)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| OpenAI API for RAG generation | Ollama local LLM (privacy-first) | 2024-2025 | Full data privacy. Local Llama3.1:8b provides comparable quality for legal QA to GPT-3.5 |
| Complex multi-turn prompting | Single-turn system prompt (D-04) | Best practice for RAG | Lower latency, easier debugging, less token waste. The context window is the "memory" |
| NLP-based citation extraction | Regex + metadata validation | Standard for structured citations | For simple formats like `[Article X, Section Y]`, regex is faster and more reliable than NLP models |
| F-string templates | YAML + Jinja2 templates (D-06) | 2024+ | Separation of concerns. Non-developers can tune prompts. Conditional logic (loops, if/else) without touching Python |
| Human-only evaluation | LLM-as-Judge | 2024-ongoing | Scalable evaluation with structured rubrics. Correlates well with human judgment (>80% agreement with GPT-4 per MT-Bench paper) |

**Deprecated/outdated:**
- **Multi-turn chat for RAG:** Each turn re-sends the entire context, wasting tokens. Single-turn with full context is simpler and equally effective.
- **Manual JSON parsing for LLM output:** Use `format="json"` in `ollama.chat()` or Pydantic schemas to enforce structured output.
- **Character-count token approximation:** Use actual tokenizers (tiktoken, model-specific) for context window management. `len(text)//4` is inaccurate and wastes context.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ollama.chat(model, messages, options, format)` API remains stable in v0.6.2 for our use case | Standard Stack | Low — API is well-documented with 75 code snippets. The library has been stable for multiple versions |
| A2 | Llama3.1:8b Q4_K_M quantized model fits in available memory (73GB disk, ~16GB RAM) | Environment | Medium — Llama3.1:8b requires ~8GB RAM at Q4_K_M. The system has 16GB RAM (from Phase 1 research — 15GB but needs confirmation). If RAM is insufficient, fall back to qwen2.5:7b (~6GB) |
| A3 | tiktoken (cl100k_base) produces accurate token counts for Llama3.1 | Context Truncation | Low — Llama3.1 uses the same tokenizer as GPT-4 family. tiktoken's cl100k_base is the correct encoding |
| A4 | LLM-as-Judge with llama3.1:8b at temperature=0.0 produces consistent scores | Evaluation | Medium — Local 8B models have higher variance than GPT-4 as judges. If inconsistency >0.5 points, average across 3 runs or use a separate evaluation rubric |
| A5 | Regex pattern `\[(Article)\s+([IVXLCDM]+),\s*Section\s+(\d+(?:\([a-z]\))?)\]` covers all citation formats in generated answers | Citation Extraction | Medium — The pattern assumes Roman numeral articles and Arabic sections with optional letter subsections. If the LLM uses all-Arabic ("Article 2, Section 5") or all-Roman ("Article II, Section V"), the pattern may miss citations. Mitigation: make the regex handle both formats |

**This table has 5 assumptions.** The planner should confirm RAM availability (A2) and LLM-as-Judge consistency (A4) before committing to the evaluation plan.

## Open Questions

1. **Which model should serve as the LLM judge?**
   - What we know: Using the same model as generator and judge risks self-preference bias. Using a smaller/faster model saves resources.
   - What's unclear: Is the 3B model (llama3.2:3b, already cached) adequate for judging? Does llama3.1:8b show self-preference bias?
   - Recommendation: Use the FALLBACK model (qwen2.5:7b) as the judge to avoid same-model bias. If 7B is too slow, use llama3.2:3b (already cached, 2GB). Test with a validation set.

2. **Token counting strategy for 4096 context window?**
   - What we know: Characters/tokens ratio varies. System prompt + 5 XML-wrapped chunks + user query can easily exceed 4096 tokens.
   - What's unclear: Should we use tiktoken (requires dependency) or the ollama tokenize API endpoint?
   - Recommendation: Use tiktoken with cl100k_base encoding (matches Llama3 tokenizer). Fall back to approximate 4:1 char:token ratio. Truncate lowest-ranked chunk first if over budget.

3. **How to annotate test queries with expected citations?**
   - What we know: Phase 1 has 23 TEST_QUERIES with `relevant_chunk_ids`. For EVAL-03, we need expected citation annotations.
   - What's unclear: Do we manually annotate which citations each answer should produce? This depends on query and retrieved chunks.
   - Recommendation: For the initial evaluation, use a "semi-supervised" approach: generate answers, manually verify citations for 5-10 queries to establish ground truth, then measure precision on the full set automatically.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Ollama | LLM inference | ✓ | 0.23.2 | — |
| llama3.2:3b | (cached, not primary model) | ✓ | 3B (q4) | — |
| qwen2.5:3b | (cached, not fallback model) | ✓ | 3B (q4) | — |
| llama3.1:8b | Generation (D-01 PRIMARY) | ✗ | — | Must pull (~4.9GB) |
| qwen2.5:7b | Generation (D-02 FALLBACK) | ✗ | — | Must pull (~4.1GB) |
| Python ollama library | Generation API | ✓ | 0.6.2 | Raw HTTP to localhost:11434 |
| Jinja2 | Prompt templates | ✓ | 3.1.6 | f-strings (worse for YAML) |
| PyYAML | Config file parsing | ✗ | — | `pip install pyyaml` |
| tiktoken | Token counting | ✗ | — | Character approximation (less accurate) |
| sqlite3 | Chunk metadata retrieval | ✓ | built-in | — |
| Python 3.11 | Runtime | ✓ | 3.11.15 | — |
| Disk space | Model downloads | 73GB free | — | Sufficient for both models (~9GB total) |

**Missing dependencies with no fallback:**
- `llama3.1:8b` — must be pulled via `ollama pull llama3.1:8b` (~4.9GB, 5-15 min depending on bandwidth)

**Missing dependencies with fallback:**
- `qwen2.5:7b` — fallback model, also needs pulling (~4.1GB)
- PyYAML — `pip install pyyaml` (simple install)
- tiktoken — `pip install tiktoken` (simple install)

## Validation Architecture

> Skipped — `workflow.nyquist_validation` is explicitly set to `false` in `.planning/config.json`.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Validate queries length (reject >4K chars), sanitize prompts (no injection via query) |
| V6 Cryptography | no | No data encryption for MVP. All data stays local (Ollama, no network egress) |

### Known Threat Patterns for Ollama/LLM Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via user query | Tampering | System prompt acts as delimiter boundary. Use XML-wrapped context that is parsed by the template, not raw concatenation. Log all queries for audit |
| Model serving DoS (Ollama crash) | Denial of Service | Implement timeout on Ollama calls (30s default). ConnectionError handling with user-friendly message. Fallback to cached model if primary fails |
| Sensitive data in Ollama logs | Information Disclosure | Ensure `ollama serve` logs don't include full prompt text. Configure logging to mask/truncate query content |

**Risk profile for Phase 2:** LOW-MEDIUM. The primary risk is prompt injection where a malicious user query tries to override the system prompt and make the LLM reveal instructions or ignore citation rules. Mitigation: the query is inserted via Jinja2 template (contextual escaping), and the system prompt explicitly states "You are a legal document analysis assistant" with strict instructions.

## Sources

### Primary (HIGH confidence)
- [Context7 /ollama/ollama-python] — `chat()`, `generate()`, `pull()`, `list()`, `ResponseError`, `ConnectionError`, `Options`, `format` parameter for structured output. 75 code snippets confirmed.
- [Context7 /pallets/jinja] — `Environment(loader=FileSystemLoader)`, `Template.render()`, template syntax (variables, for-loops, conditionals), sandboxing.
- [pip list — ollama 0.6.2, Jinja2 3.1.6, Python 3.11.15] — Version verification for installed packages.
- [ollama --version 0.23.2, ollama list] — Ollama server version and cached models verified.

### Secondary (MEDIUM confidence)
- [CITED: docs.ollama.com/api/generate] — `POST /api/generate` endpoint parameters: system, prompt, options, format, stream.
- [CITED: docs.ollama.com/api/errors] — HTTP status codes: 404 (model not found), 502 (bad gateway).
- [CITED: jinja.palletsprojects.com/en/stable/templates] — Template syntax reference, whitespace control, inheritance.
- [CITED: langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge] — LLM-as-Judge pattern: evaluation criteria, input context, scoring rubric, structured output.
- [CITED: openlayer.com/blog/post/llm-as-judge-evaluation-guide] — LLM-as-Judge best practices: chain-of-thought prompting, few-shot examples, position bias mitigation, self-preference bias.

### Tertiary (LOW confidence)
- [WebSearch: legal citation regex patterns] — Multiple sources confirm `re.findall()` with pattern matching is standard for legal citation extraction from structured text. Eyecite library (freelawproject/eyecite) exists for case law citations but is overkill for our Article/Section format.
- [WebSearch: LLM-as-Judge RAG evaluation] — RAG Triad (Context Relevance, Groundedness, Answer Relevance) is the standard framework. Our EVAL-03 and EVAL-04 map to Groundedness and Answer Relevance respectively.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — ollama Python library v0.6.2, Jinja2 v3.1.6, PyYAML — all verified via pip list or confirmed available.
- Architecture: HIGH — PromptBuilder → Generator → CitationBuilder pipeline is a standard pattern validated across multiple RAG implementations.
- Pitfalls: HIGH — Citation hallucination and context overflow are well-documented failure modes in legal RAG literature.
- Evaluation: MEDIUM — LLM-as-Judge with local 8B models has known consistency challenges. The rubric-based approach mitigates but does not eliminate variance.

**Research date:** 2026-05-14
**Valid until:** 2026-06-14 (ollama library at v0.6.2 — re-verify if >30 days old)
