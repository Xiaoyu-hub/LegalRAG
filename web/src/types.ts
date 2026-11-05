// 后端响应与实体的类型定义。字段名与 backend/api/*.py 里的 dict 保持一一对应，
// 改后端时这张表就是前端的编译期检查。

export interface ApiEnvelope<T> {
  status: "ok" | "error";
  data: T | null;
  error: string | null;
}

export type DocStatus = "processing" | "ready" | "error" | "unknown";

export interface DocumentItem {
  id: number;
  filename: string;
  title: string;
  page_count: number;
  file_path: string;
  file_size: number;
  created_at: string;
  status: DocStatus;
  chunk_count: number;
}

export interface ChunkItem {
  id: number;
  chunk_index: number;
  text: string;
  article: string | null;
  section: string | null;
  subsection: string | null;
  title: string;
  parent_article: string | null;
}

export interface Source {
  article: string | null;
  section: string | null;
  title?: string;
  text: string;
  chunk_id: number;
  citation_valid: boolean;
}

export interface Citation {
  text: string;
  article: string;
  section: string;
  valid: boolean;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  citations: Citation[];
  latency_ms: number;
  token_count: number;
  created_at: string;
}

export interface ConversationSummary {
  id: number;
  title: string;
  document_id: number | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetail {
  id: number;
  title: string;
  document_id: number | null;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface Stats {
  tenant: string;
  documents: number;
  documents_ready: number;
  documents_processing: number;
  documents_failed: number;
  chunks: number;
  vectors: number;
  conversations: number;
  messages: number;
  storage_bytes: number;
  recent_documents: {
    id: number;
    filename: string;
    page_count: number;
    file_size: number;
    status: DocStatus;
  }[];
}

export interface UsageModelRow {
  model: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
}

export interface Usage {
  tenant: string;
  month: string;
  models: UsageModelRow[];
  month_cost_usd: number;
  monthly_budget_usd: number | null;
  rpm_limit: number | null;
  rpm_used: number;
}

export interface Health {
  ollama: string;
  sqlite: string;
  faiss: string;
  faiss_vectors: Record<string, number>;
  bm25: string;
  embedder: string;
}

export interface SearchHit {
  chunk_id: number;
  score: number;
  article: string | null;
  section: string | null;
  text: string;
}
