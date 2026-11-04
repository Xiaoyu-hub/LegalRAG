/**
 * LegalRAG MCP server
 *
 * 把 LegalRAG 的检索与问答暴露成 MCP tools，让任何支持 MCP 的 Agent 直接调用。
 * 三个只读工具：列文档 / 检索法条 / 带引用的问答；另加一个用量查询。
 *
 * 设计取舍：
 *  - 只做「协议适配」，不搬业务逻辑：每个 tool 就是一次 HTTP 调用，改后端不用改这里。
 *  - 错误一律转成 MCP 的 isError 文本，不抛异常：Agent 看到可读句子比看栈更有用。
 *  - 租户从环境变量取，一个进程一个租户；多租户靠起多个实例或后续加参数。
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const BASE_URL = (process.env.LEGALRAG_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
const TENANT = process.env.LEGALRAG_TENANT ?? "demo";
const TIMEOUT_MS = Number(process.env.LEGALRAG_TIMEOUT_MS ?? 120_000);
const MAX_TOP_K = 20;

type Json = Record<string, unknown>;

/** 统一请求：带租户头、超时、把后端错误翻成人话。 */
async function call(path: string, init: RequestInit = {}): Promise<Json> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-Id": TENANT,
        ...(init.headers ?? {}),
      },
    });
    const text = await res.text();
    let body: Json;
    try {
      body = JSON.parse(text) as Json;
    } catch {
      throw new Error(`后端返回了非 JSON 响应（HTTP ${res.status}）：${text.slice(0, 200)}`);
    }
    if (!res.ok) {
      const detail = typeof body.error === "string" ? body.error : JSON.stringify(body.error);
      throw new Error(`HTTP ${res.status}：${detail}`);
    }
    return body;
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error(`请求超时（${TIMEOUT_MS}ms）：${BASE_URL}${path}`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function ok(text: string) {
  return { content: [{ type: "text" as const, text }] };
}

function fail(err: unknown) {
  const msg = err instanceof Error ? err.message : String(err);
  return { content: [{ type: "text" as const, text: `调用失败：${msg}` }], isError: true };
}

const server = new McpServer({ name: "legalrag", version: "0.1.0" });

// ── 工具 1：列文档 ────────────────────────────────────────────────────────
server.registerTool(
  "list_documents",
  {
    title: "列出已索引的法律文档",
    description: "返回当前租户下所有已上传并完成索引的文档（id、文件名、chunk 数、状态）。",
    inputSchema: {},
  },
  async () => {
    try {
      const body = await call("/api/v1/documents/");
      const data = body.data as { documents?: Array<Record<string, unknown>> } | null;
      const docs = data?.documents ?? [];
      if (docs.length === 0) {
        return ok(`租户 ${TENANT} 下还没有文档。先上传 PDF 再问。`);
      }
      const lines = docs.map(
        (d) => `- #${d.id} ${d.filename}（${d.chunk_count} chunks，状态 ${d.status}）`,
      );
      return ok(`租户 ${TENANT} 共 ${docs.length} 份文档：\n${lines.join("\n")}`);
    } catch (err) {
      return fail(err);
    }
  },
);

// ── 工具 2：检索法条 ──────────────────────────────────────────────────────
server.registerTool(
  "search_documents",
  {
    title: "检索法条片段",
    description:
      "混合检索（BM25 + 向量 + cross-encoder 重排），返回条文级片段与 article/section 元数据。只查不改。",
    inputSchema: {
      query: z.string().min(1).describe("自然语言问题或条文引用，例如 Article 5, Section 2"),
      top_k: z
        .number()
        .int()
        .min(1)
        .max(MAX_TOP_K)
        .optional()
        .describe(`返回条数，默认 5，最大 ${MAX_TOP_K}`),
    },
  },
  async ({ query, top_k }) => {
    try {
      const body = await call("/api/v1/search/", {
        method: "POST",
        body: JSON.stringify({ query, top_k: top_k ?? 5 }),
      });
      const data = body.data as { results?: Array<Record<string, unknown>> } | null;
      const results = data?.results ?? [];
      if (results.length === 0) {
        return ok(`没有检索到与「${query}」相关的内容（该租户可能还没有文档）。`);
      }
      const blocks = results.map((r, i) => {
        const art = (r.article as string) ?? "?";
        const sec = (r.section as string) ?? "?";
        const score = typeof r.score === "number" ? r.score.toFixed(3) : "?";
        return `[${i + 1}] chunk#${r.chunk_id} Article ${art} / Section ${sec}（score ${score}）\n${r.text}`;
      });
      return ok(`「${query}」命中 ${results.length} 条：\n\n${blocks.join("\n\n")}`);
    } catch (err) {
      return fail(err);
    }
  },
);

// ── 工具 3：带引用的问答 ──────────────────────────────────────────────────
server.registerTool(
  "ask_question",
  {
    title: "基于法条回答问题",
    description:
      "RAG 问答：先检索、再生成，答案带条文引用。走 LLM 网关，会消耗该租户配额并计入 token 成本。",
    inputSchema: {
      question: z.string().min(1).describe("要问的问题"),
      system: z.string().optional().describe("可选的 system prompt 覆盖"),
    },
  },
  async ({ question, system }) => {
    try {
      const payload: Record<string, unknown> = { question };
      if (system) payload.system = system;
      const body = await call("/api/v1/gateway/chat", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const d = body.data as Record<string, unknown> | null;
      if (!d) return ok("后端没有返回内容。");
      const usage = `\n\n---\nmodel=${d.model} tokens=${d.prompt_tokens}+${d.completion_tokens} cost=$${d.cost_usd} latency=${d.latency_ms}ms`;
      return ok(`${d.answer}${usage}`);
    } catch (err) {
      return fail(err);
    }
  },
);

// ── 工具 4：租户用量 ──────────────────────────────────────────────────────
server.registerTool(
  "tenant_usage",
  {
    title: "查看本租户用量与配额",
    description: "返回本月按模型聚合的调用次数、token、成本，以及月预算与 rpm 使用率。",
    inputSchema: {},
  },
  async () => {
    try {
      const body = await call("/api/v1/gateway/usage");
      return ok(JSON.stringify(body.data, null, 2));
    } catch (err) {
      return fail(err);
    }
  },
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // 注意：stdout 是 MCP 协议通道，任何调试输出都必须走 stderr
  console.error(`[legalrag-mcp] ready base=${BASE_URL} tenant=${TENANT}`);
}

main().catch((err) => {
  console.error("[legalrag-mcp] fatal:", err);
  process.exit(1);
});
