import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  listDocuments,
  streamChat,
} from "../api";
import Answer from "../components/Answer";
import type { ChatMessage, ConversationSummary, DocumentItem } from "../types";

export default function Chat() {
  const [params] = useSearchParams();
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [convs, setConvs] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState("");
  const [sending, setSending] = useState(false);
  const [question, setQuestion] = useState("");
  const [docId, setDocId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [openSources, setOpenSources] = useState<Record<number, boolean>>({});
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loadConvs = useCallback(async () => {
    try {
      const data = await listConversations();
      setConvs(data.conversations);
      return data.conversations;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return [];
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [docList, convList] = await Promise.all([listDocuments(), loadConvs()]);
        setDocs(docList.documents);
        const fromUrl = params.get("doc");
        if (fromUrl) setDocId(Number(fromUrl));
        // 打开页面自动接上最近一次会话，避免左边有历史、右边空着
        if (convList.length > 0) {
          await openConversation(convList[0].id);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
    // 只在首次挂载时跑：之后由显式操作驱动
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scrollToBottom = () => {
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }));
  };

  const openConversation = async (id: number) => {
    setError("");
    try {
      const detail = await getConversation(id);
      setActiveId(id);
      setMessages(detail.messages);
      if (detail.document_id) setDocId(detail.document_id);
      scrollToBottom();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const newChat = () => {
    abortRef.current?.abort();
    setActiveId(null);
    setMessages([]);
    setStreaming("");
    setQuestion("");
    setError("");
  };

  const removeConversation = async (id: number, event: React.MouseEvent) => {
    event.stopPropagation();
    if (!window.confirm("删除这个会话？消息会一起删掉。")) return;
    try {
      await deleteConversation(id);
      if (activeId === id) newChat();
      await loadConvs();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const send = async () => {
    const text = question.trim();
    if (!text || sending) return;

    setSending(true);
    setError("");
    setStreaming("");
    setQuestion("");

    // 本地先画一版用户气泡，等接口回来再用库里的正式记录替换
    const draft: ChatMessage = {
      id: -Date.now(),
      role: "user",
      content: text,
      sources: [],
      citations: [],
      latency_ms: 0,
      token_count: 0,
      created_at: new Date().toISOString(),
    };
    const baseMessages = activeId === null ? [] : messages;
    setMessages([...baseMessages, draft]);
    scrollToBottom();

    let convId = activeId;
    try {
      if (convId === null) {
        const conv = await createConversation(docId);
        convId = conv.id;
        setActiveId(convId);
      }

      const controller = new AbortController();
      abortRef.current = controller;
      await streamChat(
        { question: text, conversation_id: convId, document_id: docId },
        {
          onToken: (token) => {
            setStreaming((prev) => prev + token);
            scrollToBottom();
          },
          signal: controller.signal,
        },
      );

      // 流结束后从数据库读回整条会话：sources / citations / 延迟都以库为准，
      // 而不是把这些状态在前端再拼一遍（那才是两套口径的开始）
      const detail = await getConversation(convId);
      setMessages(detail.messages);
      setStreaming("");
      await loadConvs();
      scrollToBottom();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStreaming("");
    } finally {
      setSending(false);
      abortRef.current = null;
    }
  };

  const askSuggestion = (text: string) => {
    setQuestion(text);
  };

  const docOptions = useMemo(
    () => docs.filter((d) => d.status === "ready"),
    [docs],
  );

  const selectedDoc = docs.find((d) => d.id === docId) || null;

  return (
    <div className="page narrow">
      <div className="chat-layout" style={{ margin: "-28px -32px -40px", height: "calc(100% + 68px)" }}>
        <div className="conv-pane">
          <div className="card-head" style={{ padding: "14px 16px" }}>
            <span className="card-title">会话</span>
            <button className="btn btn-ghost" onClick={newChat}>
              新会话
            </button>
          </div>
          <div className="conv-list">
            {convs.length === 0 && <div className="empty">还没有历史会话</div>}
            {convs.map((c) => (
              <div
                key={c.id}
                className={`conv-item${c.id === activeId ? " active" : ""}`}
                onClick={() => openConversation(c.id)}
              >
                <div>
                  <div className="conv-title">{c.title || "未命名会话"}</div>
                  <div className="conv-meta">
                    #{c.id} · {c.message_count} 条 · {c.updated_at.slice(5, 16)}
                  </div>
                </div>
                <button className="btn btn-ghost btn-danger" onClick={(e) => removeConversation(c.id, e)}>
                  删
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="thread">
          <div className="thread-head">
            <div className="row">
              <span className="hint">检索范围</span>
              <select
                className="select"
                style={{ width: 260 }}
                value={docId ?? ""}
                onChange={(e) => setDocId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">全库（所有已就绪文档）</option>
                {docOptions.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename} · {d.chunk_count} 段
                  </option>
                ))}
              </select>
            </div>
            <div className="row">
              {selectedDoc && <span className="badge plain">{selectedDoc.filename}</span>}
              <span className="badge plain">BM25 + 向量 + Cross-Encoder 重排</span>
            </div>
          </div>

          <div className="thread-body">
            {messages.length === 0 && !streaming && (
              <div className="empty">
                <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 6 }}>
                  {activeId === null ? "新建一个会话开始提问" : "这个会话还没有消息"}
                </div>
                <div className="hint">答案里的 [Article X, Section Y] 可以直接点开看来源片段</div>
                <div className="row" style={{ justifyContent: "center", marginTop: 14, flexWrap: "wrap" }}>
                  {[
                    "What is the definition of Business Day?",
                    "What is the maximum fine for a repeated infringement?",
                    "When must a controller notify a supervisory authority of a breach?",
                  ].map((q) => (
                    <button key={q} className="btn" onClick={() => askSuggestion(q)}>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m) => (
              <div key={m.id} className={`msg ${m.role}`}>
                <span className="hint mono">
                  {m.role === "user" ? "you" : `assistant · ${m.latency_ms.toFixed(0)} ms`}
                </span>
                {m.role === "assistant" ? (
                  <>
                    <Answer
                      content={m.content}
                      citations={m.citations}
                      onCiteClick={() => setOpenSources((s) => ({ ...s, [m.id]: true }))}
                    />
                    {m.sources.length > 0 && (
                      <div className="sources">
                        <button
                          className="sources-toggle"
                          onClick={() => setOpenSources((s) => ({ ...s, [m.id]: !s[m.id] }))}
                        >
                          {openSources[m.id] ? "− 收起来源" : `+ ${m.sources.length} 条召回来源`}
                        </button>
                        {openSources[m.id] &&
                          m.sources.map((s) => (
                            <div className="source open" key={s.chunk_id}>
                              <div className="source-head">
                                <span>
                                  #{s.chunk_id} · Article {s.article || "—"} / Section {s.section || "—"}
                                </span>
                                <span className={`badge ${s.citation_valid ? "valid" : "invalid"}`}>
                                  {s.citation_valid ? "引用命中" : "引用存疑"}
                                </span>
                              </div>
                              <div className="source-text">{s.text}</div>
                            </div>
                          ))}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="bubble">{m.content}</div>
                )}
              </div>
            ))}

            {streaming && (
              <div className="msg assistant">
                <span className="hint mono">assistant · 生成中</span>
                <div className="bubble typing">{streaming}</div>
              </div>
            )}

            {error && <p className="error-text">{error}</p>}
            <div ref={bottomRef} />
          </div>

          <div className="composer">
            <textarea
              className="textarea"
              placeholder="就这份文书提问，Enter 发送 / Shift+Enter 换行"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button className="btn btn-primary" onClick={send} disabled={sending || !question.trim()}>
              {sending ? "生成中…" : "发送"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
