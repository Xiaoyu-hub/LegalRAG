# LegalRAG: 法规问答系统架构设计

> **目标：** 开发面向英文法律法规的个人开源项目
>
> **定位：** 针对英文法律条文（法规、条例、司法解释）的智能问答系统

---

## 一、项目概述

### 1.1 解决什么问题

英文法律法规文档检索存在以下痛点：

| 痛点 | 说明 |
|------|------|
| **关键词检索不准确** | 法律术语同义词多（"shall"="must"="is required to"），关键词匹配召回率低 |
| **条文结构丢失** | 普通分块把一条法律切成多段，检索结果碎片化 |
| **答案缺乏来源** | 传统 RAG 返回答案但不标注引用哪条法规 |
| **数据隐私顾虑** | 企业法律文档敏感，客户不愿上传到第三方 API |

### 1.2 项目定位

```
LegalRAG
├── 英文法律文档解析
│   └── 自动识别 Article / Section / Subsection 结构
│
├── 法律专用分块策略
│   └── 按条款边界切分，保留层级关系
│
├── 本地检索生成
│   └── BGE 嵌入 + Ollama Qwen，本地运行，数据不出本机
│
└── 带引用的问答界面
    └── 答案附条文编号和原文引用
```

### 1.3 目标用户

- 律所 / 企业法务（需要快速检索法规）
- 法律科技初创公司（需要 RAG 能力的技术验证）
- 法律 AI 研究者（评测法律文档检索效果）

---

## 二、系统架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      LegalRAG                                │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           Frontend (web/ · React + TypeScript)          │ │
│  │  ┌──────────────┐  ┌──────────────────────────────┐ │ │
│  │  │  Documents   │  │  Chat                        │ │ │
│  │  │  上传 /   状态  │  │  - 流式答案 + 行内引用        │ │ │
│  │  │  结构预览       │  │  - 召回来源 / 引用校验       │ │ │
│  │  └──────────────┘  └──────────────────────────────┘ │ │
│  │  构建产物 web/dist 由 FastAPI 同源托管（单端口）        │ │
│  └────────────────────────────────────────────────────────┘ │
│                              ↕                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Backend (FastAPI)                          │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │ │
│  │  │ Document     │  │ Retrieval    │  │ Generation │  │ │
│  │  │ Pipeline     │  │ Engine       │  │ Pipeline   │  │ │
│  │  │              │  │              │  │            │  │ │
│  │  │ - PDF Parser  │  │ - BM25       │  │ - Ollama   │  │ │
│  │  │ - Structure   │  │ - Vector     │  │ - Citation │  │ │
│  │  │   Extractor   │  │ - Hybrid     │  │   Builder  │  │ │
│  │  │ - Legal       │  │   Search     │  │            │  │ │
│  │  │   Chunker     │  │ - Re-ranker  │  │            │  │ │
│  │  └──────────────┘  └──────────────┘  └────────────┘  │ │
│  └────────────────────────────────────────────────────────┘ │
│                              ↕                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Data Layer                                │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │ │
│  │  │ FAISS        │  │ SQLite       │  │ Local FS   │  │ │
│  │  │ (Vectors)    │  │ (Metadata)   │  │ (PDFs)     │  │ │
│  │  └──────────────┘  └──────────────┘  └────────┘  │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
legalrag/
├── web/                          # 前端（React 18 + TypeScript + Vite）
│   ├── src/api.ts                # 唯一 HTTP 出口：租户头 / 错误归一 / 流式读
│   ├── src/pages/Documents.tsx   # 上传、状态轮询、结构预览
│   ├── src/pages/Chat.tsx        # 会话、流式问答、引用与来源
│   ├── src/pages/Usage.tsx       # 计量、健康、Prometheus
│   └── src/components/Answer.tsx # 引用高亮（含失效引用）
│
├── backend/                       # FastAPI 后端
│   ├── main.py                   # FastAPI 入口
│   ├── api/
│   │   ├── documents.py          # 文档上传/解析/索引 API
│   │   ├── chat.py              # 问答 API
│   │   └── search.py            # 检索 API
│   ├── pipeline/
│   │   ├── parser.py            # PDF 解析器
│   │   ├── structure_extractor.py  # 法律结构提取
│   │   ├── legal_chunker.py     # 法律专用分块器
│   │   └── indexer.py           # 索引构建
│   ├── retrieval/
│   │   ├── bm25.py             # BM25 关键词检索
│   │   ├── vector_search.py     # 向量检索
│   │   ├── hybrid_search.py    # 混合检索
│   │   └── reranker.py         # 重排
│   ├── generation/
│   │   ├── prompt_builder.py    # Prompt 构建
│   │   └── citation_builder.py  # 引用构建
│   └── models/
│       ├── document.py          # 文档模型
│       ├── chunk.py            # 分块模型
│       └── citation.py         # 引用模型
│
├── configs/
│   ├── chunking.yaml           # 分块配置
│   └── prompts.yaml            # Prompt 模板
│
├── data/
│   ├── documents/             # PDF 原文存储
│   └── index/                  # FAISS 索引
│
├── tests/
├── README.md
├── requirements.txt
└── Dockerfile
```

### 2.3 核心数据流

```
文档上传
         │
         ▼
Parser (PDF → text)
         │
         ▼
StructureExtractor (识别 Article/Section/Subsection)
         │
         ▼
LegalChunker (按条款边界分块，保留元数据)
         │
         ▼
Embedding (BGE-large-en → vector)
         │
         ▼
FAISS 索引存储
         │
         ▼
用户提问
         │
         ▼
Embedding (question → vector)
         │
         ├── BM25 检索（关键词匹配）
         └── Vector 检索（语义相似度）
         │
         ▼
Hybrid Merge（合并两个检索结果）
         │
         ▼
Re-ranker（Cross-Encoder 重排）
         │
         ▼
PromptBuilder（组装上下文 + 引用指令）
         │
         ▼
Ollama (Qwen2.5) 生成答案
         │
         ▼
CitationBuilder（提取条文编号）
         │
         ▼
前端展示答案 + 引用来源
```

---

## 三、核心模块设计

### 3.1 法律文档解析（Legal Document Parser）

**功能：** 将英文法律 PDF 转换为结构化文本，识别层级关系。

法律文档的典型结构：

```
Article I. General Provisions
  Section 1. Definitions
    (a) "Person" means...
    (b) "Entity" means...
  Section 2. Scope
  Section 3. Application

Article II. Rights and Obligations
  Section 1. Right to...
  Section 2. Obligation to...
```

解析器需要识别：
- `Article [Num]` / `§ [Num]` — 一级标题
- `Section [Num]` — 二级标题
- `(a)`, `(b)`, `(1)`, `(2)` — 子条款
- `("term")` / `"term"` — 法律术语定义

### 3.2 法律专用分块器（Legal Chunker）

**痛点：** 普通固定长度分块会把一条完整的法律条款切成碎片，导致检索结果丢失上下文。

**分块策略：**

| 策略 | 描述 | 适用场景 |
|------|------|---------|
| `by_article` | 以 Article 为最小单位，跨 Article 合并 | 单条款问答 |
| `by_section` | 以 Section 为最小单位 | 需要引用具体条款的场景 |
| `semantic_window` | 以 Article 为核心，窗口扩展周围条款 | 需要上下文的推理 |

**元数据保留：**
```python
{
  "chunk_id": "art2_sec1",
  "article": "Article II",
  "section": "Section 1",
  "subsection": "(a)",
  "text": "...",
  "title": "Right to...",
  "parent_article": "Article II. Rights and Obligations"
}
```

### 3.3 混合检索（Hybrid Search）

**为什么需要混合检索：**

| 检索方式 | 优势 | 劣势 |
|---------|------|------|
| 向量检索 | 语义相似 | 专有名词精确匹配差 |
| BM25 | 关键词精确匹配 | 同义词召回差 |

**法律场景举例：**
- 问："What is the penalty for data breach?"
- 向量检索能匹配"data breach"和"penalty"的语义相关段落
- BM25 能精确匹配"penalty"和"data breach"这两个关键词

**合并策略：**
```
score = alpha * vector_score + (1 - alpha) * bm25_score
```
alpha 可配置，默认 0.7（向量优先）。

### 3.4 引用构建（Citation Builder）

**功能：** 从检索结果中提取条文编号，附在答案中。

**Prompt 指令示例：**
```
Based on the provided legal context, answer the question.
You MUST cite the specific Article and Section numbers in your answer.
Format citations as: [Article X, Section Y]
```

**输出示例：**
```
Under Article III, Section 5(a), any data processor must obtain
prior written consent before processing personal data [Article III, Section 5(a)].
```

### 3.5 评测指标

| 指标 | 说明 |
|------|------|
| Precision@5 | top-5 检索结果中相关文档的比例 |
| Recall@5 | 全部相关文档中 top-5 召回的比例 |
| Citation Accuracy | 答案中引用正确的比例 |
| Answer Relevance | LLM-as-judge 评估答案相关性 |

---

## 四、技术栈

| 层级 | 技术 | 理由 |
|------|------|------|
| 前端 | React 18 + TypeScript + Vite | 流式渲染与状态管理要细粒度控制，Streamlit 的重跑模型做不到 |
| 后端 API | FastAPI | 异步，支持长任务（文档解析） |
| PDF 解析 | PyMuPDF + pdfplumber | 文本和表格提取 |
| Embedding | BGE-large-en-v1.5 | 英文最优开源嵌入模型，CPU 可跑 |
| 向量存储 | FAISS | 本地，零依赖 |
| BM25 | rank_bm25 | 轻量 BM25 实现 |
| 重排 | Cross-Encoder (cross-encoder/ms-marco) | 提升 top-K 排序质量 |
| LLM | Ollama (Qwen2.5 / Llama3) | 本地运行，隐私友好 |
| 数据存储 | SQLite | 轻量，存储文档元数据 |
| 部署 | Docker | 一键部署 |

---

## 五、MVP 开发计划

### 阶段 1：核心检索引擎（第 1-2 周）

- [ ] 项目脚手架（目录结构、依赖、Git 初始化）
- [ ] PDF 解析器（文本提取 + 表格提取）
- [ ] 法律结构提取器（识别 Article / Section / Subsection）
- [ ] 法律专用分块器（by_article / by_section 两种模式）
- [ ] 向量检索 + BM25 检索
- [ ] 混合检索合并
- [ ] 基础评测脚本（Precision / Recall）

### 阶段 2：生成与引用（第 3 周）

- [ ] Prompt 模板系统（英文法律问答）
- [ ] Ollama 接入（Qwen2.5）
- [ ] Citation Builder（引用提取）
- [ ] 引用准确性评测

### 阶段 3：UI 与发布（第 4 周）

- [x] 文档库页面（上传 / 索引状态轮询 / 结构预览）——实现为 `web/src/pages/Documents.tsx`
- [x] 问答页面（流式答案 + 引用高亮 + 召回来源）——`web/src/pages/Chat.tsx`
- [x] Docker 一键部署（四阶段镜像，前后端同源单端口）
- [x] README + 截图（`docs/screenshots/`）
- [x] GitHub 发布

---

*文档版本：v1.0 | 更新日期：2026-05-08*
