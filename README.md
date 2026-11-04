# LegalRAG — 多租户 RAG 服务 + LLM 网关

面向英文法律文书的检索增强生成服务，同时提供一个多租户 LLM 网关。
上传 PDF 即可提问，答案带行内引用，可直接定位到 Article / Section。

> 2026-11 定位升级：从「单租户法律文书问答」变成「多租户 RAG 服务 + LLM 网关」。
> 新增：租户隔离（元数据 / 向量 / 关键词）、
> LLM 网关（多后端路由、主备降级、配额、token 计量与成本归因）、
> Prometheus 指标与 OpenTelemetry span、FAISS 与 pgvector 双后端。

## 自检与 CI

```bash
python -m pytest tests -q          # 199 个单测与契约测试
python docs/e2e_check.py           # 端到端：上传 → 索引 → 检索 → 问答 → 重启一致（22 项断言）
python docs/trace_demo.py          # 打印一次问答的 span 树
python docs/loadtest.py            # 并发压测，出「并发 vs P99」表（需先起服务）
```

GitHub Actions（`.github/workflows/ci.yml`）跑同样的三步：单测 → 端到端自检 →
带 pgvector 服务容器的契约测试。生成段用 `LLM_PROVIDER=fake`，不依赖真模型服务。

## 架构

- **FastAPI 后端**：文档处理、混合检索（BM25 + 向量）、基于 LLM 的问答
- **Streamlit 前端**：文档上传、对话界面、结构预览
- **Ollama**：本地跑 LLM 推理（数据不出本机，不调云端 API）
- **FAISS** 做向量存储，**SQLite** 存元数据

## 快速开始

### 环境要求

- Docker 与 Docker Compose（推荐）
- 或 Python 3.11+ 与 Ollama（本地开发）

### Docker 部署（推荐）

```bash
git clone <repo-url>
cd legalrag
docker-compose up
```

前端入口：http://localhost:8501

### 本地开发

1. 安装依赖：
```bash
pip install -r requirements.txt
pip install streamlit
```

2. 确认 Ollama 已启动：
```bash
ollama serve
```

3. 拉取模型：
```bash
ollama pull llama3.1:8b
```

4. 启动后端：
```bash
uvicorn backend.main:app --reload --port 8000
```

5. 启动前端：
```bash
streamlit run app/main.py --server.port=8501
```

## 使用流程

1. 在 Documents 页面**上传**一份 PDF 法律文档
2. **等待**索引完成（状态徽标：琥珀色 → 绿色）
3. 在侧边栏**选中**该文档
4. 在 Chat 页面**提问**
5. 在每条答案下方**查看**召回来源
6. 在 Preview 页面**预览**文档结构

截图待补。

## 项目结构

```
legalrag/
├── app/                           # Streamlit 前端
│   ├── main.py                    # 入口，含侧边栏导航
│   ├── pages/
│   │   ├── 1_Documents.py         # 文档上传与管理
│   │   ├── 2_Chat.py              # 问答界面（带引用）
│   │   └── 3_Preview.py           # 文档结构预览
│   └── components/
│       ├── citation_box.py        # 引用渲染工具
│       └── doc_preview.py         # 文档树构建
├── backend/                       # FastAPI 后端
│   ├── main.py                    # FastAPI 入口：单例装配、按租户加载索引
│   ├── api/
│   │   ├── documents.py           # 文档上传 / 列表 / 状态 / 分片接口
│   │   ├── search.py              # 混合检索接口
│   │   ├── chat.py                # 流式问答接口
│   │   ├── gateway.py             # 网关用量与配额接口
│   │   └── deps.py                # 租户校验依赖（全项目唯一口径）
│   ├── pipeline/                  # 文档处理：解析 → 结构抽取 → 法律分块 → 建索引
│   │   ├── parser.py              # PDF 文本抽取
│   │   ├── structure_extractor.py # Article / Section / Subsection 层级识别
│   │   ├── legal_chunker.py       # 按条款边界切分，保留层级关系
│   │   └── indexer.py             # 串起分块、向量化与 BM25 建索引
│   ├── embedding/embedder.py      # BGE 向量化
│   ├── retrieval/
│   │   ├── bm25.py                # 关键词检索
│   │   ├── vector_search.py       # FAISS 检索（含 .ids.npy 侧车校验与回退）
│   │   ├── hybrid_search.py       # 混合召回与分数融合
│   │   ├── reranker.py            # Cross-Encoder 重排
│   │   └── stores/                # 向量存储抽象：FAISS / pgvector 双实现
│   ├── generation/
│   │   ├── pipeline.py            # 生成主链路：召回 → 重排 → prompt → 引用校验
│   │   ├── prompt_builder.py      # 拼 prompt（受 token 预算约束）
│   │   ├── generator.py           # 模型调用与主备降级
│   │   ├── citation_builder.py    # 引用抽取与有效性校验
│   │   ├── tokens.py              # 输入 token 预算
│   │   └── providers/             # 三种后端：ollama / OpenAI 兼容 / fake
│   ├── gateway/                   # LLM 网关
│   │   ├── gateway.py             # 路由、降级、配额检查、流式出口
│   │   ├── tenants.py             # 租户注册表
│   │   ├── pricing.py             # 模型单价表
│   │   └── metering.py            # token 计量与成本归因
│   ├── observability/             # Prometheus 指标 + OpenTelemetry span
│   ├── evaluation/                # 效果评估：评判、跑批、测试问题集
│   ├── storage/metadata_store.py  # SQLite 元数据，唯一持久化真相
│   └── models/                    # 数据模型：Document / Chunk / Citation
├── configs/                       # 三份配置：租户、prompt 模板、模型单价
├── mcp-server/                    # TypeScript MCP server，把检索与问答暴露成 Agent 工具
├── data/                          # 文档（按租户分目录）、FAISS 索引、SQLite 库
├── docs/
│   ├── e2e_check.py               # 端到端自检（22 项断言）
│   ├── trace_demo.py              # 打印一次问答的 span 树
│   ├── loadtest.py                # 并发压测，出「并发 vs P99」表
│   └── loadtest.md                # 压测实测结果
├── tests/                         # 单测与契约测试（199 项）
├── .github/workflows/ci.yml       # 单测 → 端到端 → pgvector 契约测试
├── architecture.md                # 架构设计文档
├── Dockerfile                     # 多阶段构建（backend / frontend 两个目标）
└── docker-compose.yml             # 一键部署：Ollama + 后端 + 前端
```

## 技术栈

| 层次 | 技术 | 用途 |
|------|------|------|
| 前端 | Streamlit | 纯 Python 快速搭界面 |
| 后端 API | FastAPI | 异步 REST 接口 |
| PDF 解析 | PyMuPDF + pdfplumber | 文本与表格抽取 |
| 向量化 | BGE-large-en-v1.5 | 英文法律文档向量 |
| 向量库 | FAISS | 本地向量检索 |
| BM25 | rank_bm25 | 关键词检索 |
| 重排 | Cross-Encoder (ms-marco) | 检索结果重排 |
| LLM | Ollama (Qwen2.5 / Llama3) | 本地 LLM 推理 |
| 元数据 | SQLite | 文档与分片存储 |
| 部署 | Docker | 容器化部署 |

## 许可证

MIT
