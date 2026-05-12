# Phase 1: Core Retrieval Engine - Research

**Researched:** 2026-05-12
**Domain:** Legal document processing, hybrid retrieval (BM25 + Vector), reranking
**Confidence:** HIGH

## Summary

This phase builds the foundational retrieval pipeline for LegalRAG: a PDF ingestion → structure extraction → legal-aware chunking → embedding → hybrid search → reranker system. The stack is entirely Python-based and designed for local CPU deployment. All decisions are locked from the discussion phase — the research confirms these choices are well-aligned with current best practices and that the selected libraries are all at their latest stable versions.

**Primary recommendation:** Implement the retrieval pipeline as six composable modules (parser, structure_extractor, legal_chunker, bm25, vector_search, reranker) tested independently before integration. The critical risk is score normalization in the hybrid merge — raw BM25 scores and FAISS inner product scores are on incompatible scales, and the weighted alpha formula (0.7 vector / 0.3 BM25) will produce incorrect results without proper normalization.

**Key environment finding:** None of the core packages (PyMuPDF, pdfplumber, faiss-cpu, sentence-transformers, torch, rank-bm25) are installed. This is expected for a greenfield project. The system has 15GB RAM, 16 CPU cores, and 79GB free disk — adequate for running BGE-large-en-v1.5 (1024-dim, 1.34GB model) and cross-encoder/ms-marco-MiniLM-L-6-v2 (approx 450MB) on CPU.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use PyMuPDF (fitz) as primary parser for text extraction
- **D-02:** Implement pdfplumber as fallback for complex table-heavy documents or when PyMuPDF fails
- **D-03:** Support text-based PDFs only for Phase 1 (OCR deferred to Phase 2)
- **D-04:** Use regex-based pattern matching to identify legal document structure
- **D-05:** Patterns to support `Article [IVX]+` / `Article \d+`, `Section \d+`, `\([a-z]\)` / `\(\d+\)` for subsections
- **D-06:** Extract legal term definitions (e.g., `"Person" means...`) for enhanced retrieval context
- **D-07:** Default to "by_section" chunking
- **D-08:** Support "by_article" as configurable alternative
- **D-09:** Preserve full hierarchy metadata: article → section → subsection → parent reference
- **D-10:** Chunk size target: 512-1024 tokens per chunk
- **D-11:** Use BGE-large-en-v1.5 embedding model
- **D-12:** Batch size: 32 for embedding generation
- **D-13:** FAISS with IndexFlatIP (Inner Product) for exact similarity search
- **D-14:** Store document metadata in SQLite with foreign key relationships
- **D-15:** Alpha weighting: 0.7 vector / 0.3 BM25
- **D-16:** Use rank_bm25 library for keyword retrieval
- **D-17:** Cross-encoder reranker: cross-encoder/ms-marco-MiniLM-L-6-v2
- **D-18:** Return top-10 chunks before reranking, top-5 after reranking
- **D-19:** Create manual test dataset with 20-30 sample queries and relevance judgments
- **D-20:** Use standard metrics: Precision@5 and Recall@5
- **D-21:** Evaluation script outputs JSON results for tracking over time

### the agent's Discretion
- Exact regex pattern implementation details
- SQLite schema design (within constraints of requirements)
- Specific error handling strategies
- Directory structure within `backend/` folder

### Deferred Ideas (OUT OF SCOPE)
None — all Phase 1 requirements are committed.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DOC-01 | System can upload and parse PDF legal documents | PyMuPDF confirmed as robust text-parsing library. `fitz.open("pdf")` → `page.get_text("text")` for plain text, `page.get_text("dict")` for structured extraction with coordinates [VERIFIED: Context7 /pymupdf/pymupdf] |
| DOC-02 | Parser extracts text content from PDF files | `page.get_text("blocks", sort=True)` extracts text blocks in reading order. pdfplumber `page.extract_text(layout=True)` as fallback for tables [VERIFIED: Context7 /jsvine/pdfplumber] |
| DOC-03 | Structure extractor identifies Article/Section/Subsection hierarchy | PyMuPDF `page.get_text("dict")` provides span-level font info for header detection. Regex patterns (D-05) applied on extracted text lines [VERIFIED: Context7 /pymupdf/pymupdf] |
| DOC-04 | System extracts legal term definitions from documents | Regex for quoted terms followed by "means" / "means the" patterns applied after structure extraction |
| DOC-05 | Metadata stored with document reference and structure info | SQLite stores documents table with FK to chunks table. Schema at the agent's discretion |
| CHNK-01 | Legal chunker supports "by_article" strategy | Article boundaries identified by regex (Article [IVX]+/\d+). Each Article becomes a chunk with all its sections [ASSUMED — standard pattern] |
| CHNK-02 | Legal chunker supports "by_section" strategy | Section boundaries identified by regex (Section \d+). Each Section becomes a chunk with its subsections [ASSUMED — standard pattern] |
| CHNK-03 | Chunks preserve metadata (article, section, subsection, parent references) | Python dict with chunk_id, article, section, subsection, text, title, parent_article as per architecture.md |
| CHNK-04 | Text is embedded using BGE-large-en-v1.5 model | SentenceTransformer('BAAI/bge-large-en-v1.5').encode(texts, normalize_embeddings=True, batch_size=32). 1024-dim output. Instruction "Represent this sentence for searching relevant passages: " for short queries [VERIFIED: huggingface.co/BAAI/bge-large-en-v1.5] |
| CHNK-05 | Embeddings are stored in FAISS index locally | `faiss.IndexFlatIP(1024)` → `index.add(normalized_embeddings)` → `faiss.write_index(index, "path")`. L2 normalization required before adding [VERIFIED: Context7 /facebookresearch/faiss] |
| CHNK-06 | Document metadata stored in SQLite database | SQLite is available via Python's built-in sqlite3. Schema at the agent's discretion |
| RETR-01 | BM25 keyword search retrieves relevant chunks | `rank_bm25.BM25Okapi(tokenized_corpus)`. `get_scores(tokenized_query)` or `get_top_n(tokenized_query, corpus, n=10)` [VERIFIED: Context7 /dorianbrown/rank_bm25] |
| RETR-02 | Vector search retrieves semantically similar chunks | `index.search(query_embedding, k=10)` returns (D, I) where D=scores, I=indices. Query must be L2-normalized [VERIFIED: Context7 /facebookresearch/faiss] |
| RETR-03 | Hybrid search merges BM25 and vector results with configurable alpha | Weighted score combination requires score normalization first (min-max scaling). Alpha=0.7 vector, 0.3 BM25 per D-15. CRITICAL PITFALL documented below |
| RETR-04 | Cross-encoder reranker improves top-K result quality | `CrossEncoder('cross-encoder/ms-marco-MiniLM-L6-v2').rank(query, passages, top_k=5)`. Takes top-10 from hybrid, returns top-5 [VERIFIED: Context7 /huggingface/sentence-transformers] |
| RETR-05 | System returns top-N chunks with metadata and similarity scores | Combine ranked chunk IDs with their metadata from SQLite. Include final reranker score |
| EVAL-01 | Precision@5 metric for retrieval quality | `len(relevant_in_top_5) / 5`. Manual relevance judgments for 20-30 queries |
| EVAL-02 | Recall@5 metric for retrieval coverage | `len(relevant_in_top_5) / total_relevant`. Requires knowing total relevant docs per query |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| PDF parsing & text extraction | Backend | — | Pure computation on uploaded files, no UI or storage tier involvement |
| Legal structure extraction | Backend | — | Operates on extracted text, regex-based pattern matching |
| Legal-aware chunking | Backend | — | Operates on structured text, produces chunks with metadata |
| Embedding generation | Backend | — | CPU-bound model inference on chunk texts |
| Vector index storage | Backend / Data Layer | — | FAISS files on local filesystem + SQLite for metadata |
| BM25 indexing & search | Backend | — | In-memory index on chunk texts |
| Hybrid search fusion | Backend | — | Combines two retriever outputs in application tier |
| Reranking | Backend | — | Cross-encoder model inference on hybrid top-K |
| Query encoding at search time | Backend | — | Same embedding model, encodes user query to vector |
| Evaluation metrics | Backend | — | Standalone script, operates on retrieval output |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard | Source |
|---------|---------|---------|--------------|--------|
| PyMuPDF (fitz) | 1.27.2.3 | PDF text and structure extraction | Best-in-class Python PDF library. Preserves layout, provides block-level structure with coordinates and font info | [VERIFIED: pip index] |
| pdfplumber | 0.11.9 | Fallback PDF parser for complex layouts | Handles table-heavy documents better than PyMuPDF. Provides word-level bounding boxes and character detail | [VERIFIED: pip index] |
| sentence-transformers | 5.4.1 | Embedding model and CrossEncoder framework | Standard framework for BGE models and CrossEncoder rerankers. Provides unified API | [VERIFIED: pip index] |
| faiss-cpu | 1.13.2 | Vector similarity search | Industry standard for local vector search. IndexFlatIP for exact inner product search | [VERIFIED: pip index] |
| rank-bm25 | 0.2.2 | BM25 keyword retrieval | Lightweight, zero-dependency BM25Okapi implementation | [VERIFIED: pip index] |
| PyTorch | 2.x (latest) | ML backend for sentence-transformers | Required dependency for sentence-transformers. No GPU needed — CPU inference | [ASSUMED — dependency] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | 1.26.4 | Array operations, score normalization | FAISS requires float32 numpy arrays. Normalize BM25/vector scores for hybrid merge | [VERIFIED: pip list] |
| sqlite3 | built-in | Metadata storage | Standard Python library, stores documents/chunks/metadata with FK relationships | [ASSUMED] |
| tiktoken | — (not needed) | Token counting for chunk sizing | Optionally estimate tokens using `len(text.split())` or model-specific tokenizer | [ASSUMED] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| rank_bm25 | bm25s (ultrafast numpy-based) | bm25s is faster but rank_bm25 is simpler and sufficient for MVP scale | [ASSUMED] |
| FAISS | ChromaDB, Qdrant | FAISS is lighter (no server needed) and the only zero-dependency option. ChromaDB adds SQLite-backed persistence but also adds a dependency | [ASSUMED] |
| weighted score fusion | Reciprocal Rank Fusion (RRF) | RRF avoids score normalization entirely. D-15 locks in weighted alpha, so score normalization is mandatory | [CITED: sureprompts.com/blog/hybrid-search-implementation-guide] |
| BGE-large-en-v1.5 | BGE-m3 (multilingual, dense+sparse+colbert) | BGE-m3 supports hybrid search natively but requires more RAM and is overkill for English-only | [ASSUMED] |

**Installation:**
```bash
pip install pymupdf==1.27.2.3 pdfplumber==0.11.9 \
  sentence-transformers==5.4.1 faiss-cpu==1.13.2 \
  rank-bm25==0.2.2
# PyTorch (required by sentence-transformers):
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

**Version verification:** All versions confirmed via `pip index versions <package>` on 2026-05-12. These are the latest stable releases.

## Architecture Patterns

### System Architecture Diagram

```
                          ┌──────────────────┐
                          │   Legal PDF File  │
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │    PyMuPDF        │
                          │  page.get_text()  │
                          │ ("dict" + "text") │
                          └────────┬─────────┘
                                   │ text + spans
                                   │ with positions
                          ┌────────▼─────────┐
                          │ pdfplumber        │
                          │ (fallback for     │
                          │  table-heavy PDFs)│
                          └────────┬─────────┘
                                   │
                          ┌────────▼──────────────┐
                          │ StructureExtractor     │
                          │ Regex: Article/Section │
                          │ /Subsection detection  │
                          │ + term definitions     │
                          └────────┬──────────────┘
                                   │ structured text
                                   │ with hierarchy
                          ┌────────▼──────────────┐
                          │ LegalChunker           │
                          │ by_section (default)   │
                          │ or by_article (alt)    │
                          └────────┬──────────────┘
                                   │ chunks with
                                   │ metadata dict
                    ┌───────────────┼───────────────┐
                    │               │               │
           ┌────────▼──────┐  ┌────▼───────┐  ┌────▼────────────┐
           │ BGE Embeds    │  │ SQLite     │  │ BM25 Index      │
           │ (batch_size=32)│  │ Documents  │  │ rank_bm25       │
           │ FAISS Index   │  │ + Chunks   │  │ on chunk texts  │
           │ IndexFlatIP   │  │ metadata   │  │                 │
           └────────┬──────┘  └────┬───────┘  └────┬────────────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    │
                           ┌────────▼──────────────┐
                           │   User Query          │
                           │   "What is the        │
                           │    penalty for..."    │
                           └────────┬──────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
           ┌────────▼──────┐       │       ┌───────▼───────────┐
           │ Encode query  │       │       │ Tokenize query    │
           │ via BGE       │       │       │ BM25.get_scores() │
           │ IndexFlatIP   │       │       │                   │
           │ .search(k=20) │       │       │ get_top_n(k=20)   │
           └────────┬──────┘       │       └───────┬───────────┘
                    │              │               │
                    └──────┬───────┴───────────────┘
                           │
                   ┌───────▼────────────┐
                   │ Hybrid Merge       │
                   │ Min-max normalize  │
                   │ vector + BM25      │
                   │ 0.7*V + 0.3*B      │
                   │ Keep top-10        │
                   └───────┬────────────┘
                           │
                   ┌───────▼────────────┐
                   │ CrossEncoder       │
                   │ Reranker            │
                   │ .rank(query, chunks │
                   │  , top_k=5)        │
                   └───────┬────────────┘
                           │
                   ┌───────▼────────────┐
                   │ Top-5 chunks with  │
                   │ scores + metadata  │
                   │ (to Phase 2: Gen)  │
                   └────────────────────┘
```

### Recommended Project Structure

```
backend/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── document.py        # Document dataclass (id, filename, title, page_count, ...)
│   └── chunk.py           # Chunk dataclass (id, doc_id, article, section, subsection, text, ...)
├── pipeline/
│   ├── __init__.py
│   ├── parser.py          # PDFParser: PyMuPDF primary, pdfplumber fallback
│   ├── structure_extractor.py  # StructureExtractor: regex-based hierarchy detection
│   ├── legal_chunker.py   # LegalChunker: by_section / by_article strategies
│   └── indexer.py         # Indexer: orchestrates parse→extract→chunk→embed→index
├── retrieval/
│   ├── __init__.py
│   ├── bm25.py            # BM25Retriever: wraps rank_bm25
│   ├── vector_search.py   # VectorSearch: wraps FAISS, loads/saves index
│   ├── hybrid_search.py   # HybridSearch: merges BM25 + vector with score normalization
│   └── reranker.py        # Reranker: CrossEncoder, .rank()
├── embedding/
│   ├── __init__.py
│   └── embedder.py        # Embedder: singleton SentenceTransformer, encode()
├── storage/
│   ├── __init__.py
│   └── metadata_store.py  # MetadataStore: SQLite CRUD for docs + chunks
└── evaluation/
    ├── __init__.py
    ├── test_queries.py    # Manual test dataset (20-30 queries)
    └── evaluator.py       # Precision@5, Recall@5 computation
```

**Key design principle:** Each module has a single responsibility and a clear interface. The `Indexer` orchestrator in `pipeline/` wires them together for the document ingestion flow. The `HybridSearch` module orchestrates the retrieval flow.

### Pattern 1: PDF Parsing with Fallback
**What:** Try PyMuPDF first; fall back to pdfplumber if extraction fails or yields empty text.
**When to use:** On every document ingest call.
**Example:**
```python
# Source: [VERIFIED: Context7 /pymupdf/pymupdf, /jsvine/pdfplumber]
import pymupdf
import pdfplumber

def extract_text_from_pdf(path: str) -> str:
    """Primary: PyMuPDF. Fallback: pdfplumber for complex layouts."""
    try:
        doc = pymupdf.open(path)
        text_parts = []
        for page in doc:
            blocks = page.get_text("blocks", sort=True)
            page_text = "\n".join(b[4] for b in blocks if b[6] == 0)  # block_type==0 is text
            text_parts.append(page_text)
        doc.close()
        full_text = "\n".join(text_parts)
        if full_text.strip():
            return full_text
    except Exception:
        pass

    # Fallback to pdfplumber
    with pdfplumber.open(path) as pdf:
        text_parts = [page.extract_text(layout=True) for page in pdf.pages]
    return "\n".join(text_parts)
```

### Pattern 2: Structure Extraction with Regex
**What:** Process plain text line-by-line, match Article/Section/Subsection patterns, build hierarchy tree.
**When to use:** After PDF parsing, before chunking.
**Example:**
```python
# Source: [ASSUMED — standard regex pattern for legal docs]
import re

# Patterns from D-05
PATTERNS = {
    "article": re.compile(r"^(Article)\s+((?:[IVXLCDM]+|\d+))", re.IGNORECASE),
    "section": re.compile(r"^(Section)\s+(\d+)", re.IGNORECASE),
    "subsection_letter": re.compile(r"^\(([a-z])\)"),
    "subsection_num": re.compile(r"^\((\d+)\)"),
    "definition": re.compile(r'"([^"]+)"\s+means\s+'),
}

def extract_structure(text: str) -> list[dict]:
    lines = text.split("\n")
    hierarchy: list[dict] = []
    current_article = None
    current_section = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if m := PATTERNS["article"].match(stripped):
            current_article = {"type": "article", "number": m.group(2).strip(), "text": stripped}
            current_section = None
            hierarchy.append(current_article)
        elif m := PATTERNS["section"].match(stripped):
            current_section = {"type": "section", "number": m.group(2), "text": stripped,
                               "parent_article": current_article["number"] if current_article else None}
            hierarchy.append(current_section)
        elif current_section and (m := PATTERNS["subsection_letter"].match(stripped)):
            hierarchy.append({"type": "subsection", "label": m.group(1), "text": stripped,
                              "parent_section": current_section["number"]})
        elif current_section and (m := PATTERNS["subsection_num"].match(stripped)):
            hierarchy.append({"type": "subsection", "label": m.group(1), "text": stripped,
                              "parent_section": current_section["number"]})
        else:
            # Belongs to current section/article
            ...

    return hierarchy
```

### Pattern 3: Embedding with BGE Query Instruction
**What:** For short-query-to-long-passage retrieval, prepend the instruction to queries (not passages). Use `normalize_embeddings=True`.
**When to use:** Whenever encoding queries or passages via SentenceTransformer.
**Example:**
```python
# Source: [VERIFIED: huggingface.co/BAAI/bge-large-en-v1.5]
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-large-en-v1.5")

# For short queries to long passages (s2p), add instruction
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

def encode_query(query: str) -> np.ndarray:
    return model.encode(
        [QUERY_INSTRUCTION + query],
        normalize_embeddings=True,
        batch_size=1
    )[0]

def encode_passages(passages: list[str]) -> np.ndarray:
    # No instruction for passages
    return model.encode(
        passages,
        normalize_embeddings=True,
        batch_size=32
    )
```

### Pattern 4: Hybrid Search with Score Normalization
**What:** Normalize both score vectors to [0,1] before weighted combination. Min-max per query.
**When to use:** In the hybrid search module, after getting BM25 scores and FAISS distances.
**Example:**
```python
# Source: [CITED: sureprompts.com/blog/hybrid-search-implementation-guide]
import numpy as np

def normalize_scores(scores: np.ndarray) -> np.ndarray:
    """Min-max normalize scores to [0, 1] per query."""
    min_s, max_s = scores.min(), scores.max()
    if max_s == min_s:
        return np.zeros_like(scores)
    return (scores - min_s) / (max_s - min_s)

def hybrid_search(query_vec: np.ndarray, tokenized_query: list[str],
                  faiss_index, bm25_model, chunks: list[dict],
                  alpha: float = 0.7, top_k_pre: int = 20,
                  top_k_post: int = 10) -> list[tuple[int, float]]:
    # Vector search
    vec_distances, vec_indices = faiss_index.search(query_vec.reshape(1, -1), top_k_pre)
    vec_scores = np.zeros(len(chunks))
    vec_scores[vec_indices[0]] = vec_distances[0]

    # BM25 search
    bm25_scores = np.array(bm25_model.get_scores(tokenized_query))

    # Normalize both to [0, 1]
    vec_norm = normalize_scores(vec_scores)
    bm25_norm = normalize_scores(bm25_scores)

    # Weighted combination
    hybrid = alpha * vec_norm + (1.0 - alpha) * bm25_norm

    # Get top-K indices
    top_indices = np.argsort(hybrid)[::-1][:top_k_post]
    return [(idx, hybrid[idx]) for idx in top_indices]
```

### Pattern 5: Cross-Encoder Reranking
**What:** Load CrossEncoder once (singleton), call `.rank(query, passages, top_k=5)` on the hybrid merged results.
**When to use:** After hybrid search, before returning final results.
**Example:**
```python
# Source: [VERIFIED: Context7 /huggingface/sentence-transformers]
from sentence_transformers import CrossEncoder

class Reranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L6-v2"):
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, passages: list[str], top_k: int = 5) -> list[dict]:
        """Rank passages by relevance to query. Returns sorted list."""
        results = self.model.rank(query, passages, top_k=top_k, return_documents=True)
        return [
            {"corpus_id": r["corpus_id"], "score": r["score"], "text": r["text"]}
            for r in results
        ]
```

### Anti-Patterns to Avoid
- **Storing FAISS index in SQLite BLOB:** FAISS `serialize_index` produces large byte arrays. Save index as separate `.faiss` file; keep only the file path in SQLite.
- **Normalizing once during indexing but not at query time:** FAISS queries need the same L2 normalization applied to the query vector as was applied to indexed vectors.
- **Forgetting to normalize BM25 scores before weighted fusion:** Raw BM25 scores are unbounded. Without min-max normalization per query, one retriever dominates regardless of alpha weight.
- **Rebuilding BM25 index on every query:** BM25 corpus should be built once at ingest time and persisted (or rebuilt on app startup from chunk texts in SQLite).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF text extraction | Custom PDF parser | PyMuPDF | PDF format is extremely complex (fonts, encodings, compression, layout). PyMuPDF wraps MuPDF (C library, 20+ years of edge case handling) |
| Table extraction from PDFs | Custom coordinate math | pdfplumber | pdfplumber has built-in `page.find_tables()` and `page.extract_table()` with configurable tolerance |
| Keyword search ranking | TF-IDF from scratch | rank_bm25 | BM25 is TF-IDF's successor with saturation and length normalization. The rank_bm25 library has it implemented correctly in <200 lines |
| Vector similarity search | Custom numpy dot-product loop | FAISS | FAISS is optimized (BLAS, SIMD, multi-threaded) and handles batch queries, persistent indexes, and future scaling to IVF/HNSW |
| Embedding model training | Fine-tuning BERT from scratch | SentenceTransformer(BGE) | BGE-large-en-v1.5 is pre-trained and instruction-tuned for retrieval. Fine-tuning requires thousands of labeled legal query-document pairs |
| Reranker/CrossEncoder | Training a custom relevance model | cross-encoder/ms-marco-MiniLM | MS MARCO is the standard passage ranking dataset. This model is already fine-tuned for query-document relevance scoring |
| Score normalization for hybrid search | Assuming raw scores are comparable | Min-max normalization per query | BM25 and FAISS IP scores are on different scales. Direct weighted sum without normalization is the #1 hybrid search bug |
| LLM-as-judge evaluation | Manual relevance scoring of results | Scripted Precision@5 / Recall@5 | For Phase 1, the retriever is evaluated independently. LLM-as-judge deferred to Phase 2 (EVAL-04) |

**Key insight:** Every item in this table represents a known-hard problem with an off-the-shelf solution. Custom implementations would each take days and introduce subtle bugs. The ecosystem libraries are battle-tested at scale.

## Common Pitfalls

### Pitfall 1: Score Scale Mismatch in Hybrid Fusion
**What goes wrong:** Weighted hybrid formula `0.7 * vec_score + 0.3 * bm25_score` produces garbage results because raw BM25 scores (e.g., 0-15) dwarf FAISS inner product scores (e.g., 0.6-0.95), or vice versa.
**Why it happens:** BM25 scores are corpus-dependent and unbounded. FAISS IndexFlatIP returns inner products (for normalized vectors, this is cosine similarity in [-1, 1]). These are fundamentally incompatible scales.
**How to avoid:** Always min-max normalize BOTH score distributions per query before applying the alpha weight. Test with edge cases (zero-score queries, single-term queries, very long queries).
**Warning signs:** The top results are dominated by one retriever consistently, regardless of alpha value.

### Pitfall 2: L2 Normalization Inconsistency
**What goes wrong:** FAISS IndexFlatIP with non-normalized vectors produces meaningless similarity scores because inner product of non-normalized vectors confuses magnitude with similarity.
**Why it happens:** IndexFlatIP computes dot product. For cosine similarity (which BGE embeddings are trained for), all vectors must be unit-length.
**How to avoid:** `faiss.normalize_L2(embeddings)` before `index.add()` AND `faiss.normalize_L2(query)` before `index.search()`. Use `model.encode(..., normalize_embeddings=True)` for consistency.
**Warning signs:** Vectors with larger magnitudes always rank higher regardless of semantic content.

### Pitfall 3: Chunking That Destroys Legal Context
**What goes wrong:** Sections split mid-paragraph, article boundaries ignored, "Section 4.2(b)" references separated from parent Section 4.2 text.
**Why it happens:** Character-count or token-count splitting disregards document structure.
**How to avoid:** Always chunk on natural boundaries (Article/Section/Subsection). Preserve full hierarchy as metadata. The `by_article` and `by_section` strategies in LegalChunker must detect these boundaries BEFORE splitting.
**Warning signs:** Retrieved chunks contain orphan subsections without their parent heading, or references to "Section 2" appear without identifying which Article they belong to.

### Pitfall 4: Cross-Encoder Token Limit Truncation
**What goes wrong:** The cross-encoder/ms-marco-MiniLM-L-6-v2 model has a 512-token max length. Chunks that exceed this get silently truncated before scoring, producing unreliable reranking scores.
**Why it happens:** Legal document sections can easily exceed 512 tokens. The model's tokenizer truncates input silently.
**How to avoid:** Either (a) enforce chunk size <= 512 tokens during chunking, or (b) set `max_length=512` explicitly on CrossEncoder init and log truncation warnings.
**Warning signs:** Reranker scores seem uniform across top results, or long chunks consistently get lower-than-expected scores.

### Pitfall 5: BM25 Tokenization Mismatch
**What goes wrong:** Queries are split on whitespace but documents were split differently (e.g., including punctuation), so "penalty." and "penalty" don't match.
**Why it happens:** BM25 is a pure token-matching algorithm. Tokenization must be identical for indexing and querying.
**How to avoid:** Define a single `tokenize(text: str) -> list[str]` function used for both corpus building and query. At minimum: lowercase, split on whitespace, strip punctuation. Consider stemming for legal terms (e.g., "regulate" vs "regulation").
**Warning signs:** Relevant documents with exact keyword matches get zero BM25 score.

### Pitfall 6: FAISS Index Persistence Staleness
**What goes wrong:** After adding documents to FAISS and saving, a subsequent ingest clears and rebuilds but the old .faiss file remains, causing query-time crashes (dimension mismatch) or stale results.
**Why it happens:** FAISS is stateful. If the index grows, the file must be rewritten atomically.
**How to avoid:** Write to a temp file then rename. Always validate `index.ntotal` and `index.d` on load. Consider versioning the index file (e.g., `index_v2.faiss`).

## Code Examples

### Complete Document Ingestion Pipeline (Pseudocode)
```python
# Source: [VERIFIED: all library APIs via Context7]

def ingest_document(pdf_path: str, metadata_store: MetadataStore) -> int:
    # 1. Parse PDF
    raw_text = extract_text_from_pdf(pdf_path)  # Pattern 1

    # 2. Extract structure
    structure = extract_structure(raw_text)  # Pattern 2

    # 3. Chunk
    chunker = LegalChunker(strategy="by_section")  # default per D-07
    chunks = chunker.chunk(structure)  # list of Chunk dataclass

    # 4. Save metadata to SQLite
    doc_id = metadata_store.insert_document(pdf_path)
    metadata_store.insert_chunks(doc_id, chunks)

    # 5. Embed
    embedder = Embedder.get_instance()  # singleton
    chunk_texts = [c.text for c in chunks]
    embeddings = embedder.encode(chunk_texts)  # -> np.ndarray (n_chunks, 1024)

    # 6. Add to FAISS
    vector_index = VectorSearch.get_instance()  # singleton IndexFlatIP
    vector_index.add(embeddings, chunk_ids=[c.id for c in chunks])

    # 7. Rebuild BM25
    bm25 = BM25Retriever.get_instance()
    bm25.build_index(chunk_texts, chunk_ids=[c.id for c in chunks])

    return doc_id
```

### Complete Query Pipeline (Pseudocode)
```python
# Source: [VERIFIED: all library APIs via Context7]

def retrieve(query: str, alpha: float = 0.7, top_k: int = 10) -> list[dict]:
    # 1. Encode query
    embedder = Embedder.get_instance()
    query_vec = embedder.encode_query(query)

    # 2. Tokenize query for BM25
    bm25 = BM25Retriever.get_instance()
    tokenized_query = bm25.tokenize(query)

    # 3. Vector search
    vec_indices, vec_scores = vector_search.search(query_vec, k=20)

    # 4. BM25 search
    bm25_scores = bm25.get_scores(tokenized_query)

    # 5. Hybrid merge (Pattern 4)
    hybrid_results = hybrid_merge(
        vec_indices, vec_scores,
        np.arange(len(bm25_scores)), bm25_scores,
        alpha=alpha, top_k=top_k
    )  # -> list[(chunk_id, score)]

    # 6. Fetch chunk texts from SQLite
    chunk_ids = [r[0] for r in hybrid_results]
    chunks = metadata_store.get_chunks(chunk_ids)

    # 7. Rerank (Pattern 5)
    reranker = Reranker.get_instance()
    reranked = reranker.rerank(
        query=query,
        passages=[c.text for c in chunks],
        top_k=5
    )

    # 8. Attach metadata
    return [
        {"chunk": chunks[r["corpus_id"]], "score": r["score"]}
        for r in reranked
    ]
```

### Evaluation Script
```python
# Source: [ASSUMED — standard IR evaluation pattern]

def evaluate(retriever, test_queries: list[dict], k: int = 5) -> dict:
    """test_queries: [{"query": str, "relevant_chunk_ids": set}]
    Returns precision@k, recall@k per query and averaged.
    """
    precisions, recalls = [], []

    for tq in test_queries:
        results = retriever.retrieve(tq["query"], top_k=k)
        retrieved_ids = {r["chunk"]["id"] for r in results}
        relevant = tq["relevant_chunk_ids"]

        true_positives = len(retrieved_ids & relevant)
        precisions.append(true_positives / k)
        recalls.append(true_positives / len(relevant) if relevant else 0)

    return {
        f"precision@{k}": sum(precisions) / len(precisions),
        f"recall@{k}": sum(recalls) / len(recalls),
        "per_query": [
            {"query": tq["query"], "p": p, "r": r}
            for tq, p, r in zip(test_queries, precisions, recalls)
        ]
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fixed-size chunking (256/512 tokens) | Legal-aware structural chunking | 2024-2025 | +15-25% retrieval accuracy for legal documents per multiple studies |
| TF-IDF keyword search | BM25 (Okapi BM25) | Standard since 2010s | Better term saturation and doc-length normalization |
| Pure vector search | Hybrid (BM25 + Vector + Reranker) | 2023-2024 | +8-15% NDCG@10 over single retriever approach |
| cosine-similarity with non-normalized vectors | L2-normalized inner product (cosine via IndexFlatIP) | Always applicable | Correct similarity semantics |
| Zero-shot embeddings without instruction | Instruction-tuned embeddings (BGE v1.5) | 2024-01 (v1.5 release) | +3-5% retrieval accuracy on BEIR benchmark |

**Deprecated/outdated:**
- **BGE-v1 (original)**: The v1.5 series fixes the similarity distribution saturation issue where all pairs scored >0.9. Always use v1.5.
- **all-MiniLM-L6-v2 embeddings**: 384-dim, less capable for domain-specific retrieval. BGE-large-en-v1.5 (1024-dim) is the current open-source leader for English retrieval.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | sentence-transformers 5.4.1 is backward-compatible with BGE-large-en-v1.5 | Standard Stack | Low — BGE model uses standard SentenceTransformer API unchanged across versions |
| A2 | torch CPU-only install is sufficient for BGE-large-en-v1.5 inference | Standard Stack | Medium — embedding generation on CPU with 1024-dim model at batch_size=32 may be slow (expect ~2-5 sec per 32 chunks) |
| A3 | The cross-encoder/ms-marco-MiniLM-L-6-v2 model is still available on HuggingFace Hub | Standard Stack | Low — it's a foundational model with 1M+ downloads, unlikely to be removed |
| A4 | Min-max normalization per query is the best approach for hybrid score fusion | Hybrid Search | Medium — RRF avoids normalization issues entirely but D-15 locks in weighted alpha. If normalization proves fragile, planner should flag for re-discussion |
| A5 | The regex patterns (D-05) cover standard English legal document formats | Structure Extraction | Medium — specialized legal documents (court opinions, regulatory filings) may use different conventions. Mitigation: make regexes configurable |

**This table has 5 assumptions flagged.** The planner should flag these for user confirmation during the discuss-phase if not already covered.

## Open Questions

1. **How to persist BM25 index between restarts?**
   - What we know: rank_bm25 BM25Okapi is an in-memory object with no built-in save/load.
   - What's unclear: Should we rebuild BM25 from SQLite chunk texts on every app restart, or pickle/serialize the BM25 object?
   - Recommendation: Rebuild from SQLite on startup. With <10K chunks this takes <1 second. If chunk count grows, switch to pickling. This is within the agent's discretion.

2. **What tokenizer to use for BM25?**
   - What we know: legal terms include multi-word phrases ("data breach"), punctuation ("§ 5(a)"), and hyphenated terms.
   - What's unclear: Simple whitespace splitting loses information. Stemming may help ("regulates"→"regulate").
   - Recommendation: Start with lowercase + regex `\w+` (alphanumeric tokens only). Add stemming if evaluation shows poor recall for inflected terms.

3. **How to handle documents with no recognized structure?**
   - What we know: regex patterns (D-05) assume standard Article/Section format.
   - What's unclear: Some legal PDFs may use different conventions or have no clear structure.
   - Recommendation: Fall back to paragraph-based chunking (split on double newlines) for unstructured documents. Log a warning. This is within the agent's discretion.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | All | ✓ | 3.11.15 | — |
| pip | Package install | ✓ | 24.0 | — |
| numpy | FAISS, score normalization | ✓ | 1.26.4 | — |
| sqlite3 (built-in) | Metadata storage | ✓ | built-in | — |
| PyTorch (CPU) | sentence-transformers | ✗ | — | `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| PyMuPDF (fitz) | PDF parsing | ✗ | — | `pip install pymupdf==1.27.2.3` |
| pdfplumber | PDF fallback | ✗ | — | `pip install pdfplumber==0.11.9` |
| sentence-transformers | BGE & CrossEncoder | ✗ | — | `pip install sentence-transformers==5.4.1` |
| faiss-cpu | Vector search | ✗ | — | `pip install faiss-cpu==1.13.2` |
| rank-bm25 | BM25 search | ✗ | — | `pip install rank-bm25==0.2.2` |
| huggingface_hub | Model download | ✓ | 1.14.0 | Just installed |
| fastapi | (Phase 3, not needed now) | ✓ | 0.136.1 | — |

**Missing dependencies with no fallback:** None — all dependencies can be installed via pip.

**Missing dependencies with fallback:** None — all dependencies are mandatory core libs.

**Model download requirements:**
- BGE-large-en-v1.5: ~1.34GB (download once, cached in ~/.cache/huggingface/)
- cross-encoder/ms-marco-MiniLM-L-6-v2: ~450MB
- Total disk needed: ~2GB for models

## Validation Architecture

> Skipped — `workflow.nyquist_validation` is explicitly set to `false` in `.planning/config.json`.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single-user local deployment. No user accounts in Phase 1 |
| V3 Session Management | no | No sessions in Phase 1 (purely programmatic API) |
| V4 Access Control | no | Single-user, no multi-tenancy |
| V5 Input Validation | yes | Validate file paths to prevent directory traversal during PDF upload |
| V6 Cryptography | no | No data at rest encryption requirements for MVP |

### Known Threat Patterns for Python/FAISS Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| PDF path traversal (malicious filename like `../../etc/passwd`) | Tampering | Sanitize filenames: `os.path.basename()`, reject paths with `..` |
| Large PDF memory exhaustion | Denial of Service | Set max file size (e.g., 100MB), stream parsing for large files |
| Unsafe pickle deserialization (if pickling BM25) | Tampering | Pickle is not safe to load from untrusted sources. Use only for local BM25 persistence. Never accept pickled objects from network |

**Risk profile for Phase 1:** LOW. No network-facing endpoints exist in Phase 1 (API layer is Phase 3). The security boundary is the filesystem — document upload paths and model cache integrity.

## Sources

### Primary (HIGH confidence)
- [Context7 /pymupdf/pymupdf] — PDF text extraction, font analysis, block-level structure
- [Context7 /jsvine/pdfplumber] — Text extraction, layout preservation, table extraction
- [Context7 /facebookresearch/faiss] — IndexFlatIP setup, L2 normalization, I/O operations
- [Context7 /huggingface/sentence-transformers] — SentenceTransformer.encode(), CrossEncoder.rank(), usage patterns
- [Context7 /dorianbrown/rank_bm25] — BM25Okapi initialization, get_scores, get_top_n
- [pip index] — Version verification for all packages (pymupdf 1.27.2.3, pdfplumber 0.11.9, faiss-cpu 1.13.2, sentence-transformers 5.4.1, rank-bm25 0.2.2)

### Secondary (MEDIUM confidence)
- [CITED: huggingface.co/BAAI/bge-large-en-v1.5] — Model dimensions (1024), sequence length (512), query instruction
- [CITED: sureprompts.com/blog/hybrid-search-implementation-guide] — Hybrid search fusion strategies, RRF vs weighted, score normalization pitfalls
- [CITED: mbrenndoerfer.com/writing/hybrid-search-bm25-dense-retrieval-fusion] — Reciprocal rank fusion explained, weighted combination tradeoffs
- [CITED: blog.serghei.pl/posts/reciprocal-rank-fusion-explained] — RRF mathematics, industry adoption (Elasticsearch, OpenSearch, Weaviate, Qdrant)
- [CITED: arxiv.org/pdf/2603.25333] — Adaptive chunking framework for RAG, legal document chunking evaluation metrics

### Tertiary (LOW confidence)
- [WebSearch: legal RAG chunking practices] — Multiple sources confirm heading-based/structural chunking is the legal RAG best practice

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — All package versions verified against pip registry
- Architecture: HIGH — Patterns confirmed against Context7 library docs
- Pitfalls: HIGH — Based on documented failure modes from hybrid search literature and legal RAG research
- Hybrid search normalization: MEDIUM — Weighted score combination is correct per D-15 but normalization strategy choice (min-max vs z-score) may need tuning

**Research date:** 2026-05-12
**Valid until:** 2026-06-12 (libraries at latest versions; re-verify if >30 days old)
