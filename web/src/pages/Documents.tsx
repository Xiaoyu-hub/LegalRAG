import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  deleteDocument,
  documentChunks,
  getStats,
  listDocuments,
  reindexDocument,
  uploadDocument,
} from "../api";
import StatusBadge, { bytes, num } from "../components/StatusBadge";
import type { ChunkItem, DocumentItem, Stats } from "../types";

const POLL_MS = 2000;

export default function Documents() {
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [hot, setHot] = useState(false);
  const [openDoc, setOpenDoc] = useState<DocumentItem | null>(null);
  const [chunks, setChunks] = useState<ChunkItem[]>([]);
  const [chunkLoading, setChunkLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    try {
      const [list, s] = await Promise.all([listDocuments(), getStats()]);
      setDocs(list.documents);
      setStats(s);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 索引是后台任务：只要还有 processing，就轮询 /documents/ 直到状态收敛。
  // 用 setTimeout 串行而不是 setInterval：请求偶尔比 2s 慢时不会堆叠。
  const hasProcessing = docs.some((d) => d.status === "processing");
  useEffect(() => {
    if (!hasProcessing) return;
    const timer = window.setTimeout(() => {
      refresh();
    }, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [hasProcessing, docs, refresh]);

  const doUpload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("只支持 PDF（后端校验 content_type=application/pdf）");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await uploadDocument(file);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDrop = async (event: React.DragEvent) => {
    event.preventDefault();
    setHot(false);
    const file = event.dataTransfer.files?.[0];
    if (file) await doUpload(file);
  };

  const openPreview = async (doc: DocumentItem) => {
    setOpenDoc(doc);
    setChunkLoading(true);
    setChunks([]);
    try {
      const data = await documentChunks(doc.id);
      setChunks(data.chunks);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setChunkLoading(false);
    }
  };

  const remove = async (doc: DocumentItem) => {
    if (!window.confirm(`删除「${doc.filename}」？库记录、磁盘文件与索引向量会一起清掉。`)) return;
    try {
      await deleteDocument(doc.id);
      if (openDoc?.id === doc.id) setOpenDoc(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const reindex = async (doc: DocumentItem) => {
    try {
      await reindexDocument(doc.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  // 按 Article 分组以后再看 preview：法条的自然单位是「条」，不是 chunk
  const grouped = useMemo(() => {
    const map = new Map<string, ChunkItem[]>();
    for (const c of chunks) {
      const key = c.article ? `Article ${c.article}` : "未标注条号";
      const list = map.get(key) || [];
      list.push(c);
      map.set(key, list);
    }
    return [...map.entries()];
  }, [chunks]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">文档库</h1>
          <p className="page-desc">
            上传 PDF → 解析 → 结构抽取 → 分块 → 向量化 + BM25。索引在后台跑，状态自动刷新。
          </p>
        </div>
        <div className="row">
          <button className="btn" onClick={refresh} disabled={busy}>
            刷新
          </button>
          <button className="btn btn-primary" onClick={() => fileRef.current?.click()} disabled={busy}>
            {busy ? "上传中…" : "上传 PDF"}
          </button>
        </div>
      </div>

      {stats && (
        <div className="stat-grid">
          <div className="stat">
            <div className="stat-label">Documents</div>
            <div className="stat-value gold">{num(stats.documents)}</div>
            <div className="hint">就绪 {stats.documents_ready} · 索引中 {stats.documents_processing}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Chunks</div>
            <div className="stat-value">{num(stats.chunks)}</div>
            <div className="hint">FAISS 向量 {num(stats.vectors)}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Conversations</div>
            <div className="stat-value">{num(stats.conversations)}</div>
            <div className="hint">消息 {num(stats.messages)}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Storage</div>
            <div className="stat-value">{bytes(stats.storage_bytes)}</div>
            <div className="hint">租户 {stats.tenant} 的上传目录</div>
          </div>
        </div>
      )}

      <div
        className={`dropzone${hot ? " hot" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setHot(true);
        }}
        onDragLeave={() => setHot(false)}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
      >
        把 PDF 拖到这里，或<strong> 点此选择文件</strong>
        <div className="hint" style={{ marginTop: 6 }}>
          单文件上限 50 MB；同名文件视为替换（旧 chunk 与向量会一起清掉）
        </div>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="application/pdf"
        style={{ display: "none" }}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (file) await doUpload(file);
          e.target.value = "";
        }}
      />

      {error && <p className="error-text">{error}</p>}

      <div className="card" style={{ marginTop: 18 }}>
        <div className="card-head">
          <span className="card-title">文档列表</span>
          <span className="hint">{docs.length} 份</span>
        </div>
        {docs.length === 0 ? (
          <div className="empty">还没有文档。先上传一份法律文书，再回问答页提问。</div>
        ) : (
          <table className="list">
            <thead>
              <tr>
                <th>文件</th>
                <th>状态</th>
                <th>分段</th>
                <th>页数</th>
                <th>大小</th>
                <th>创建时间</th>
                <th style={{ textAlign: "right" }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <span className="filename" onClick={() => openPreview(doc)}>
                      {doc.filename}
                    </span>
                    <div className="hint mono">#{doc.id}</div>
                  </td>
                  <td>
                    <StatusBadge status={doc.status} />
                  </td>
                  <td className="mono">{doc.chunk_count}</td>
                  <td className="mono">{doc.page_count || "—"}</td>
                  <td className="mono">{bytes(doc.file_size)}</td>
                  <td className="mono muted">{doc.created_at}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button className="btn btn-ghost" onClick={() => navigate(`/chat?doc=${doc.id}`)}>
                      提问
                    </button>
                    <button className="btn btn-ghost" onClick={() => openPreview(doc)}>
                      结构
                    </button>
                    <button className="btn btn-ghost" onClick={() => reindex(doc)} disabled={doc.status === "processing"}>
                      重建
                    </button>
                    <button className="btn btn-ghost btn-danger" onClick={() => remove(doc)}>
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {openDoc && (
        <div className="card chunk-panel">
          <div className="card-head">
            <span className="card-title">
              {openDoc.filename} · 分段结构
            </span>
            <button className="btn btn-ghost" onClick={() => setOpenDoc(null)}>
              收起
            </button>
          </div>
          <div className="card-body">
            {chunkLoading && <div className="loading">加载分块…</div>}
            {!chunkLoading && grouped.length === 0 && <div className="empty">这份文档还没有分块</div>}
            {grouped.map(([article, items]) => (
              <div key={article}>
                <div className="chunk-article">{article}</div>
                {items.map((c) => (
                  <div className="chunk-item" key={c.id}>
                    <div className="chunk-meta">
                      chunk #{c.id} · Section {c.section || "—"} · index {c.chunk_index}
                    </div>
                    <div className="chunk-text">{c.text}</div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
