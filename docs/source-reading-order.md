# 源码阅读顺序

按**运行时数据流**读，不按目录读。每个站点先回答它自己的问题，再往下走；
读完 1–9 站，你能独立讲清「一份 PDF 是怎么变成一个带引用的答案的」。

只给符号名不给行号：行号会随提交漂移，符号不会。

## 只有 30 分钟：四站

`backend/main.py`（startup）→ `backend/pipeline/indexer.py`（`process_document`）→
`backend/retrieval/hybrid_search.py`（`search`）→ `backend/generation/pipeline.py`（`answer_stream`）。

这四站串起来就是主链路：装配 → 入库 → 检索 → 生成。

---

## 1. 契约层：`backend/models/`

- `document.py` / `chunk.py` / `citation.py`
- 要回答：**一个 chunk 靠什么字段定位到法条？**（`article` / `section` / `parent_article` / `chunk_index`）
- `Citation.valid` 是谁写的、谁读的？先记住"有个 valid 布尔"，第 7 站会回来解释。

## 2. 装配层：`backend/main.py`

- `startup()`：构造 `MetadataStore`、`ConversationStore`、按租户的 `Indexer`、`Reranker`、`LLMGateway`
- 重点看**启动自检**：`vs.load()` 之后 `mapping_matches(expected_ids)`，不一致就 `rebuild_all()`
- 要回答：进程重启后，索引与数据库靠什么对齐？BM25 为什么每次重启都重建？
- 末尾的 `SPAStaticFiles`：为什么挂在所有路由之后，为什么要 `index.html` 回退

## 3. 入口层：`backend/api/`

顺序：`deps.py` → `documents.py` → `chat.py` → `conversations.py` → `search.py` → `gateway.py` → `stats.py`

- `deps.resolve_tenant`：全项目唯一的"什么算合法租户"，未注册 401
- `documents.upload_document`：校验 → 落盘 → 同名替换 → 建记录 → `BackgroundTasks` 索引
- `documents.delete_document`：**三处都要清**（库、磁盘、索引），少一处就是"幽灵向量"
- `chat.stream_answer`：为什么建会话是独立端点（流式一开始就发 header，塞不进响应体了）、
  为什么提问先落库、为什么流结束后要再读一次库而不是前端自己拼状态
- `_collect_sources`：`citation_valid` 是怎么按 chunk 汇出来的

## 4. 入库流水线：`backend/pipeline/`

`parser.py` → `structure_extractor.py` → `legal_chunker.py` → `indexer.py`

- `parser.extract_text`：PyMuPDF 主路径 + pdfplumber 兜底；`page_count` 为什么要单独一个方法
- `structure_extractor.PATTERNS`：`Article ([IVXLCDM]+|\d+)`、`Section (\d+)`、`(a)`，这就是"只吃英文法条"的技术原因
- `legal_chunker._chunk_by_section`：**两类边界的 flush**（遇到下一个 Section、遇到新 Article 前都要把上一个写完），
  漏一个就是整段条文被静默丢掉
- `indexer.process_document`：10 步里第 5 步先删旧 chunk、第 7–10 步向量化与落盘，顺序不能换

## 5. 存储：`backend/storage/`

- `metadata_store.py`：`_connect()` 里的两行 PRAGMA（`foreign_keys`、`busy_timeout`）决定了 CASCADE 到底生效不生效；
  `get_chunks(ids)` 为什么必须按传入顺序重排
- `conversation_store.py`：`append_message` 顺手写标题与 `updated_at`；为什么它单独一个 db 文件
- 要回答：三张表（documents / chunks / definitions）与两个新表（conversations / messages）的边界

## 6. 检索：`backend/retrieval/`

`bm25.py` → `vector_search.py` → `hybrid_search.py` → `reranker.py`

- `bm25.tokenize`：**建库与查询必须同一个分词器**，否则「Article 5, Section 2」永远匹配不上
- `vector_search`：`chunk_ids` 是 FAISS 位置 → 业务主键的映射；`save` 为什么要写两个文件、为什么要 `os.replace`
- `hybrid_search.search`：两路召回怎么融合（分数归一 / RRF），为什么两路各取 top 多一点
- `reranker`：召回 10 → 重排留 5，`corpus_id` 是"在这批里的下标"不是 chunk id

## 7. 生成：`backend/generation/`

`pipeline.py` → `prompt_builder.py` → `citation_builder.py` → `providers/*`

- `GenerationPipeline.__init__`：为什么可以注入 `gateway`（走网关）也可以什么都不注入（走裸 provider）
- `_retrieve`：召回转元数据 → 过滤文档 → 重排，`document_id` 过滤发生在重排**之前**
- `prompt_builder.build`：`<chunk id article section>` 的上下文格式；超 token 预算时从尾往前丢
- `citation_builder`：`extract` → `validate`（精确匹配 + 宽松子串）→ `mark_invalid`
- `providers/extractive.py`：`_citation_label` 为什么必须和 `CITATION_PATTERN` 同源；
  `_split_sentences` 为什么要把 `Article/Section` 标题行扔掉

## 8. 网关：`backend/gateway/`

`tenants.py` → `pricing.py` → `metering.py` → `gateway.py`

- `_check_quota`：rpm 与月预算两条闸，超了抛 `QuotaExceeded`（API 层转 429 + `Retry-After`）
- `_candidates`：主模型在前、白名单内其余模型作降级候选
- `metering.record`：为什么计量必须落库（内存计数器重启清零 ⇒ 预算形同虚设）
- 要回答：429 / 403 / 401 / 503 各对应哪种失败

## 9. 观测与规格

- `observability/metrics.py`：`llm_requests_total` / `llm_tokens_total{kind}` / `llm_cost_usd_total`
- `observability/tracing.py` + `docs/trace_demo.py`：一次问答的三段 span
- `tests/`：**当规格读**。`test_tenancy.py` 讲三层隔离，`test_vector_store.py` 讲映射校验，
  `test_conversations.py` 讲级联与租户隔离，`test_extractive_and_chat.py` 讲引用必须过校验、提问必须落库
- `docs/e2e_check.py`：22 项断言就是这份系统的验收清单

## 10. 前端：`web/src/`

`api.ts` → `types.ts` → `App.tsx` → `pages/Documents.tsx` → `pages/Chat.tsx` → `pages/Usage.tsx` → `components/Answer.tsx`

- `api.ts`：为什么租户走头不走 query、为什么流式用 `ReadableStream` 而不是 EventSource、
  为什么业务错误（HTTP 200 + `status:error`）也抛异常
- `types.ts`：与后端 dict 一一对应，改后端时它是编译期检查
- `pages/Chat.tsx`：先画本地气泡 → 流式追加 → **结束后整体从库里读回**
- `components/Answer.tsx`：引用正则与后端 `CITATION_PATTERN` 同源，失效引用画红线

---

## 读完之后应该能回答

1. 一份 PDF 到可检索状态要过几步，每步的失败长什么样
2. 为什么 `chunk_id` 与 FAISS 位置必须分开、映射丢了会怎样
3. 引用校验的三层匹配，以及「模型编了一个条文号」在界面上怎么体现
4. 会话落库为什么放在流结束后，为什么前端还要回读一次
5. 多租户隔离发生在哪三层，少一层会串什么
6. 没有模型时这条链路还能验证什么（以及验证不了什么）
