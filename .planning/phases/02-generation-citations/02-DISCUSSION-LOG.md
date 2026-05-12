# Phase 2: Generation & Citations - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-12
**Phase:** 2-Generation & Citations
**Areas discussed:** LLM Model Selection, Prompt Engineering, Citation Format, Context Assembly, Evaluation Strategy

---

## 1. LLM Model Selection

| Option | Description | Selected |
|--------|-------------|----------|
| llama3.1:8b Q4_K_M | Best legal reasoning, CPU-friendly, ~5GB | ✓ |
| qwen2.5:7b Q4_K_M | Alternative, slightly faster | |
| llama3.1:13b | Better quality but higher memory | |
| qwen2.5:14b | Higher capacity but slower | |

**User's choice:** llama3.1:8b (Q4_K_M) — confirmed
**Notes:** User approved recommendation without modifications

---

## 2. Prompt Engineering Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Single-turn System Prompt + YAML config | Simple, fast, easy to debug | ✓ |
| Multi-turn conversation | More flexible but complex | |
| Few-shot examples in prompt | Better instruction following | |
| External prompt management service | Overkill for MVP | |

**User's choice:** Single-turn System Prompt + YAML config — confirmed
**Notes:** User approved recommendation without modifications

---

## 3. Citation Format & Validation

| Option | Description | Selected |
|--------|-------------|----------|
| Inline [Article X, Section Y] | Matches legal document patterns | ✓ |
| Footnotes with numbering | Traditional academic style | |
| Parenthetical (Art. X, Sec. Y) | Compact inline | |
| Hover tooltips with full reference | Rich but complex UI | |

**User's choice:** Inline [Article X, Section Y] with post-processing validation — confirmed
**Notes:** User approved recommendation without modifications

---

## 4. Context Assembly

| Option | Description | Selected |
|--------|-------------|----------|
| Top-5 chunks, 4096 token budget, XML wrapped | Balanced information density | ✓ |
| Top-3 chunks only | Faster but less context | |
| Top-10 chunks, longer context window | More info but slower | |
| Dynamic chunk selection by relevance | Complex to implement | |

**User's choice:** Top-5 chunks, 4096 token budget, XML chunk wrapping — confirmed
**Notes:** User approved recommendation without modifications

---

## 5. Evaluation Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Citation Precision + LLM-as-Judge (1-5) | Matches ROADMAP target, measurable | ✓ |
| ROUGE/BLEU metrics | Not suitable for citations | |
| Human evaluation only | Too expensive for MVP | |
| Custom citation F1 score | Good but complex | |

**User's choice:** Citation Precision (>80%) + LLM-as-Judge relevance — confirmed
**Notes:** User approved recommendation without modifications

---

## Agent's Discretion

All 5 areas had concrete recommendations provided. User confirmed all choices without modifications:
- Tokenization implementation details
- Regex patterns for citation extraction
- Error handling for Ollama connection failures

## Deferred Ideas

None — discussion stayed within phase scope. All Phase 2 requirements addressed.

---

*Log created: 2026-05-12*
*Phase: 2-Generation & Citations*