# legalrag-mcp

把 LegalRAG 的检索与问答暴露成 **MCP tools**，任何支持 Model Context Protocol 的 Agent
（Claude Desktop、Cursor、自建 agent）都能直接调用，不用自己写 HTTP 客户端。

## 工具

| 工具 | 参数 | 说明 |
|---|---|---|
| `list_documents` | — | 当前租户下已索引的文档（id / 文件名 / chunk 数 / 状态） |
| `search_documents` | `query`, `top_k?` | 混合检索（BM25 + 向量 + cross-encoder 重排），返回条文级片段 |
| `ask_question` | `question`, `system?` | RAG 问答，答案带引用；走 LLM 网关，计入租户配额与成本 |
| `tenant_usage` | — | 本月按模型聚合的 token / 成本，以及预算与 rpm 使用率 |

全部只读，不会改数据。租户由环境变量决定，一个进程一个租户。

## 配置

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `LEGALRAG_BASE_URL` | `http://127.0.0.1:8000` | LegalRAG 后端地址 |
| `LEGALRAG_TENANT` | `demo` | 租户 id（必须已在 `configs/tenants.yaml` 注册） |
| `LEGALRAG_TIMEOUT_MS` | `120000` | 单次请求超时 |

## 跑起来

```bash
# 1) 起后端（另开一个终端，在 repo 根目录）
python -m uvicorn backend.main:app --port 8000

# 2) 装依赖并编译
cd mcp-server
npm install
npm run build

# 3) 冒烟：列出工具 + 各调一次
$env:LEGALRAG_BASE_URL="http://127.0.0.1:8000"
$env:LEGALRAG_TENANT="demo"
node scripts/smoke.mjs
```

接进 Claude Desktop / Cursor 时，在它的 MCP 配置里写：

```json
{
  "mcpServers": {
    "legalrag": {
      "command": "node",
      "args": ["D:/program/open/legalrag/mcp-server/dist/index.js"],
      "env": { "LEGALRAG_BASE_URL": "http://127.0.0.1:8000", "LEGALRAG_TENANT": "demo" }
    }
  }
}
```

## 设计说明

- **只做协议适配**：每个 tool 就是一次 HTTP 调后端，业务逻辑留在 Python 侧。
  换后端不用改 MCP 层，也不用在两处维护检索参数。
- **错误变成文本**：后端 4xx/5xx 会转成 `isError: true` 的可读句子（带状态码与后端 error 字段），
  Agent 拿到的是「HTTP 429：tenant=demo quota exceeded」而不是一段栈。
- **stdout 只走协议**：所有日志走 stderr —— MCP 用 stdout 传 JSON-RPC，混进一行 print 就会破协议。

## 已知限制

- 单进程单租户（多租户靠起多个实例）；没做 token 鉴权，靠内网部署
- `ask_question` 走非流式接口：Agent 场景下一次性拿全量回答更好处理，代价是首字延迟
