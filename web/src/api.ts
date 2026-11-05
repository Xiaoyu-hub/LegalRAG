// 所有 HTTP 调用都从这里走，页面里不出现 fetch。
//
// 两个刻意的设计：
// 1. 租户走 `X-Tenant-Id` 头而不是查询参数 —— 与后端 resolve_tenant 的唯一口径一致，
//    也避免租户 id 出现在 URL 日志里被随意改。
// 2. 流式问答用 ReadableStream 逐块读，而不是 EventSource：后端返回的是
//    `text/plain` 的 token 流，不走 SSE 的 event/data 帧格式。

import type {
  ApiEnvelope,
  ChunkItem,
  ConversationDetail,
  ConversationSummary,
  DocumentItem,
  Health,
  SearchHit,
  Stats,
  Usage,
} from "./types";

export const TENANT_KEY = "legalrag.tenant";
export const TENANTS = ["demo", "legal", "bench", "e2e"];

export function getTenant(): string {
  return localStorage.getItem(TENANT_KEY) || "demo";
}

export function setTenant(tenant: string) {
  localStorage.setItem(TENANT_KEY, tenant);
}

function headers(extra?: Record<string, string>): Record<string, string> {
  return { "X-Tenant-Id": getTenant(), ...(extra || {}) };
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(`/api/v1${path}`, {
    ...init,
    headers: headers(init.headers as Record<string, string> | undefined),
  });
  const text = await resp.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    throw new ApiError(`响应不是 JSON：${text.slice(0, 120)}`, resp.status);
  }
  const env = body as ApiEnvelope<T> | { detail?: string };
  if (!resp.ok) {
    const detail = (env as { detail?: string }).detail;
    const error = (env as ApiEnvelope<T>).error;
    throw new ApiError(detail || error || `HTTP ${resp.status}`, resp.status);
  }
  const wrapped = env as ApiEnvelope<T>;
  // 业务错误（HTTP 200 + status=error）也当异常抛：页面只需要处理一种失败路径
  if (wrapped.status === "error") {
    throw new ApiError(wrapped.error || "请求失败", resp.status);
  }
  return wrapped.data as T;
}

// ── 文档 ──

export function listDocuments(): Promise<{ documents: DocumentItem[] }> {
  return request("/documents/");
}

export function uploadDocument(file: File): Promise<{ document_id: number; status: string }> {
  const form = new FormData();
  form.append("file", file);
  return request("/documents/upload", { method: "POST", body: form });
}

export function deleteDocument(id: number): Promise<{ deleted: number; file_removed: boolean }> {
  return request(`/documents/${id}`, { method: "DELETE" });
}

export function reindexDocument(id: number): Promise<{ document_id: number; status: string }> {
  return request(`/documents/${id}/reindex`, { method: "POST" });
}

export function documentChunks(id: number): Promise<{ chunks: ChunkItem[] }> {
  return request(`/documents/${id}/chunks`);
}

export function search(query: string, topK = 8): Promise<{ results: SearchHit[] }> {
  return request("/search/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
}

// ── 会话 ──

export function listConversations(): Promise<{ conversations: ConversationSummary[] }> {
  return request("/conversations");
}

export function createConversation(documentId?: number | null): Promise<ConversationSummary> {
  return request("/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId ?? null }),
  });
}

export function getConversation(id: number): Promise<ConversationDetail> {
  return request(`/conversations/${id}`);
}

export function deleteConversation(id: number): Promise<{ deleted: number }> {
  return request(`/conversations/${id}`, { method: "DELETE" });
}

// ── 统计 / 用量 / 健康 ──

export function getStats(): Promise<Stats> {
  return request("/stats");
}

export function getUsage(): Promise<Usage> {
  return request("/gateway/usage");
}

export function getHealth(): Promise<Health> {
  return request("/health");
}

// ── 流式问答 ──

export interface StreamHandlers {
  onToken: (token: string) => void;
  signal?: AbortSignal;
}

/**
 * 发一次提问并按块读回答案。
 *
 * 不用 `resp.body.getReader()` 的前提是浏览器支持；Edge/Chrome 都支持，
 * 但为了在老环境里也不白屏，这里做了一次兜底：拿不到 body 时退回整段读。
 */
export async function streamChat(
  payload: { question: string; conversation_id: number; document_id: number | null },
  { onToken, signal }: StreamHandlers,
): Promise<void> {
  const resp = await fetch("/api/v1/chat/", {
    method: "POST",
    headers: headers({ "Content-Type": "application/json" }),
    body: JSON.stringify({ ...payload, session_id: `web-${payload.conversation_id}` }),
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(text.slice(0, 200) || `HTTP ${resp.status}`, resp.status);
  }

  const reader = resp.body?.getReader();
  if (!reader) {
    onToken(await resp.text());
    return;
  }

  // 用 TextDecoder 的 stream 模式：多字节的中文可能被切在两个 chunk 之间
  const decoder = new TextDecoder("utf-8");
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const piece = decoder.decode(value, { stream: true });
    if (piece) onToken(piece);
  }
  const tail = decoder.decode();
  if (tail) onToken(tail);
}
