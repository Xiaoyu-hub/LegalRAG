"""Manual test dataset of 23 queries with relevance judgments.

Each entry:
- query: Natural language question a legal professional would ask
- relevant_chunk_ids: Set of chunk IDs that are relevant (from sample_legal.txt)
- category: Type of query for analysis
- notes: Why this query tests important retrieval behavior

CHUNK ID PLACEHOLDERS — Update these after ingesting sample_legal.txt
Run: python -c "from backend.pipeline.indexer import Indexer; idx=Indexer(); idx.process_document('data/test/sample_legal.txt'); from backend.storage.metadata_store import MetadataStore; ms=MetadataStore(); print([(c.id, c.article, c.section, c.text[:80]) for c in ms.get_all_chunks()])"
Then map each query's relevant_chunk_ids to the actual IDs.

Expected chunk layout (by_section chunking of sample_legal.txt):
  Chunk IDs will be auto-incremented from the DB, but expected order:
  Chunk ~1: Article I, Section 1 (Definitions) — Person, Entity, Writing, Business Day
  Chunk ~2: Article I, Section 2 (Scope of Application) — jurisdiction, exemptions
  Chunk ~3: Article I, Section 3 (Interpretation) — singular/plural, references
  Chunk ~4: Article II, Section 1 (Data Protection Rights) — access, rectification, erasure, portability
  Chunk ~5: Article II, Section 2 (Obligations of Data Controllers) — security, breach notification
  Chunk ~6: Article II, Section 3 (Data Processing Agreements) — processor, contract
  Chunk ~7: Article III, Section 1 (Regulatory Authority) — establishment, powers, term
  Chunk ~8: Article III, Section 2 (Investigative Powers) — information, audits, premises
  Chunk ~9: Article III, Section 3 (Administrative Fines) — fines for Art II Sec 1/2
  Chunk ~10: Article III, Section 4 (Right to Judicial Remedy) — judicial remedy, jurisdiction
"""

TEST_QUERIES = [
    # === 定义类查询（category=definition）===
    {
        "query": "What is the definition of a Person under this regulation?",
        "relevant_chunk_ids": {1},
        "category": "definition",
        "notes": "Tests exact definition extraction for 'Person' term in Section 1"
    },
    {
        "query": "How is 'Writing' defined in the general provisions?",
        "relevant_chunk_ids": {1},
        "category": "definition",
        "notes": "Tests definition retrieval for 'Writing' as recorded communication"
    },
    {
        "query": "What constitutes a Business Day according to the regulation?",
        "relevant_chunk_ids": {1},
        "category": "definition",
        "notes": "Tests definition of Business Day (excludes weekends and holidays)"
    },
    {
        "query": "Does the definition of Entity include governmental agencies?",
        "relevant_chunk_ids": {1},
        "category": "definition",
        "notes": "Tests whether definition extraction captures Entity scope including government"
    },

    # === 适用范围类查询（category=scope）===
    {
        "query": "Who has to comply with these regulations?",
        "relevant_chunk_ids": {2},
        "category": "scope",
        "notes": "Tests scope of application — applies to all legal persons operating within jurisdiction"
    },
    {
        "query": "Are there any exemptions from this regulation?",
        "relevant_chunk_ids": {2},
        "category": "scope",
        "notes": "Tests exemption provision for entities with equivalent regulatory standards"
    },
    {
        "query": "Does this regulation apply to government entities?",
        "relevant_chunk_ids": {2},
        "category": "scope",
        "notes": "Tests exclusion for governmental activities in exercise of sovereign authority"
    },

    # === 义务类查询（category=obligation）===
    {
        "query": "What are the obligations of data controllers regarding security?",
        "relevant_chunk_ids": {5},
        "category": "obligation",
        "notes": "Tests obligation to implement appropriate technical and organizational security measures"
    },
    {
        "query": "How long do data controllers have to notify about a data breach?",
        "relevant_chunk_ids": {5},
        "category": "obligation",
        "notes": "Tests 72-hour breach notification requirement — specific time-bound obligation"
    },
    {
        "query": "What records must data controllers maintain?",
        "relevant_chunk_ids": {5},
        "category": "obligation",
        "notes": "Tests obligation to maintain record of all processing activities"
    },

    # === 处罚类查询（category=penalty）===
    {
        "query": "What is the maximum fine for violating data protection rights?",
        "relevant_chunk_ids": {9},
        "category": "penalty",
        "notes": "Tests fine for Article II Section 1 violations — up to EUR 20M or 4% turnover"
    },
    {
        "query": "What are the penalties for a data controller who fails to meet their obligations?",
        "relevant_chunk_ids": {9},
        "category": "penalty",
        "notes": "Tests fine for Article II Section 2 violations — up to EUR 10M or 2% turnover"
    },
    {
        "query": "Can the regulatory authority impose sanctions for violations?",
        "relevant_chunk_ids": {7, 9},
        "category": "penalty",
        "notes": "Tests cross-article: Regulatory Authority powers (Art III Sec 1) + fines (Art III Sec 3)"
    },

    # === 禁止类查询（category=prohibition）===
    {
        "query": "What data processing activities are not allowed under this regulation?",
        "relevant_chunk_ids": {4},
        "category": "prohibition",
        "notes": "Tests understanding of data protection rights as limitations on processing"
    },
    {
        "query": "Can personal data be kept indefinitely under this regulation?",
        "relevant_chunk_ids": {4},
        "category": "prohibition",
        "notes": "Tests right to erasure — 'right to be forgotten' when data no longer necessary"
    },

    # === 权利类查询（category=rights）===
    {
        "query": "What rights do data subjects have regarding their personal data?",
        "relevant_chunk_ids": {4},
        "category": "rights",
        "notes": "Tests comprehensive data protection rights — access, rectification, erasure, portability"
    },
    {
        "query": "Can a data subject request deletion of their personal data?",
        "relevant_chunk_ids": {4},
        "category": "rights",
        "notes": "Tests right to erasure / 'right to be forgotten'"
    },
    {
        "query": "Do data subjects have the right to take legal action?",
        "relevant_chunk_ids": {10},
        "category": "rights",
        "notes": "Tests right to effective judicial remedy under Article III Section 4"
    },
    {
        "query": "How can someone access their personal data held by a company?",
        "relevant_chunk_ids": {4},
        "category": "rights",
        "notes": "Tests right of access to personal data held by data controller"
    },

    # === 程序类查询（category=procedure）===
    {
        "query": "What is the process for filing a complaint about data processing?",
        "relevant_chunk_ids": {10, 8},
        "category": "procedure",
        "notes": "Tests procedural remedy pathway — judicial remedy + investigative powers"
    },
    {
        "query": "How does the regulatory authority conduct investigations?",
        "relevant_chunk_ids": {8},
        "category": "procedure",
        "notes": "Tests investigative powers: information requests, audits, and premises inspections"
    },
    {
        "query": "Can the regulatory authority audit data controllers on-site?",
        "relevant_chunk_ids": {8},
        "category": "procedure",
        "notes": "Tests audit powers including on-site inspections with reasonable notice"
    },
    {
        "query": "Where should legal proceedings against a data controller be brought?",
        "relevant_chunk_ids": {10},
        "category": "procedure",
        "notes": "Tests jurisdiction — proceedings in courts where data controller has establishment"
    },
]


# QUERY_ANNOTATIONS：可选的标准答案标注，用来校准评委
# 把测试查询的下标映射到「期望引用 + 期望相关性」。
# 这些标注是可选的：没标注的条目照样能跑。
QUERY_ANNOTATIONS = {
    10: {  # "What is the maximum fine for violating data protection rights?"
        "expected_citations": [{"article": "III", "section": "3"}],
        "expected_relevance": 5,
    },
    11: {  # "What are the penalties for a data controller who fails to meet their obligations?"
        "expected_citations": [{"article": "III", "section": "3"}],
        "expected_relevance": 5,
    },
    14: {  # "What data processing activities are not allowed under this regulation?"
        "expected_citations": [{"article": "II", "section": "1"}],
        "expected_relevance": 4,
    },
    15: {  # "Can personal data be kept indefinitely under this regulation?"
        "expected_citations": [{"article": "II", "section": "1"}],
        "expected_relevance": 4,
    },
    16: {  # "What rights do data subjects have regarding their personal data?"
        "expected_citations": [{"article": "II", "section": "1"}],
        "expected_relevance": 5,
    },
}

QUERY_CATEGORIES = [
    "definition",    # 围绕法定术语定义的查询
    "scope",         # 围绕适用范围/对象的查询
    "obligation",    # 围绕义务/要求的查询
    "penalty",       # 围绕处罚/后果的查询
    "prohibition",   # 围绕禁止行为的查询
    "rights",        # 围绕权利/资格的查询
    "procedure",     # 围绕程序性要求的查询
]
