import { useCallback, useEffect, useState } from "react";

import { getHealth, getStats, getUsage } from "../api";
import { bytes, num } from "../components/StatusBadge";
import type { Health, Stats, Usage } from "../types";

interface MetricLine {
  name: string;
  value: string;
}

/** 从 Prometheus 文本里挑出最该看的几行，整页刷 /metrics 反而看不清重点。 */
function pickMetrics(text: string): MetricLine[] {
  const wanted = [
    "llm_requests_total",
    "llm_tokens_total",
    "llm_cost_usd_total",
    "rag_citations_total",
    "http_requests_total",
  ];
  const out: MetricLine[] = [];
  for (const line of text.split("\n")) {
    if (!line || line.startsWith("#")) continue;
    const name = line.split("{")[0].split(" ")[0];
    if (wanted.includes(name)) out.push({ name: line.trim(), value: "" });
    if (out.length >= 8) break;
  }
  return out;
}

export default function UsagePage() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [metrics, setMetrics] = useState<MetricLine[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [u, h, s] = await Promise.all([getUsage(), getHealth(), getStats()]);
      setUsage(u);
      setHealth(h);
      setStats(s);
      const resp = await fetch("/metrics");
      if (resp.ok) setMetrics(pickMetrics(await resp.text()));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const calls = usage?.models.reduce((sum, m) => sum + m.calls, 0) ?? 0;
  const tokens =
    usage?.models.reduce((sum, m) => sum + m.prompt_tokens + m.completion_tokens, 0) ?? 0;
  const budget = usage?.monthly_budget_usd ?? null;
  const spent = usage?.month_cost_usd ?? 0;
  const budgetPct = budget && budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">用量与健康</h1>
          <p className="page-desc">
            数据来源：LLM 网关的计量账本（SQLite）+ 各组件健康检查 + Prometheus 指标出口。
          </p>
        </div>
        <button className="btn" onClick={load} disabled={loading}>
          {loading ? "刷新中…" : "刷新"}
        </button>
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className="stat-grid">
        <div className="stat">
          <div className="stat-label">本月调用</div>
          <div className="stat-value gold">{num(calls)}</div>
          <div className="hint">{usage?.month || "—"} · 租户 {usage?.tenant || "—"}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Token 合计</div>
          <div className="stat-value">{num(tokens)}</div>
          <div className="hint">prompt + completion</div>
        </div>
        <div className="stat">
          <div className="stat-label">本月成本</div>
          <div className="stat-value">${spent.toFixed(4)}</div>
          <div className="hint">{budget === null ? "该租户不设预算" : `预算 $${budget}`}</div>
          {budget !== null && budget > 0 && (
            <div className="bar">
              <span style={{ width: `${budgetPct}%` }} />
            </div>
          )}
        </div>
        <div className="stat">
          <div className="stat-label">最近一分钟</div>
          <div className="stat-value">
            {num(usage?.rpm_used)} <span className="hint">/ {usage?.rpm_limit ?? "不限"}</span>
          </div>
          <div className="hint">rpm 限速按分钟窗口统计</div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-head">
            <span className="card-title">按模型计量</span>
            <span className="hint">超预算时网关返回 429</span>
          </div>
          {!usage || usage.models.length === 0 ? (
            <div className="empty">本月还没有调用记录。去问答页问一句就会有。</div>
          ) : (
            <table className="list">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>调用</th>
                  <th>prompt</th>
                  <th>completion</th>
                  <th>成本</th>
                </tr>
              </thead>
              <tbody>
                {usage.models.map((m) => (
                  <tr key={m.model}>
                    <td className="mono">{m.model}</td>
                    <td className="mono">{num(m.calls)}</td>
                    <td className="mono">{num(m.prompt_tokens)}</td>
                    <td className="mono">{num(m.completion_tokens)}</td>
                    <td className="mono">${m.cost_usd.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <div className="card-head">
            <span className="card-title">组件健康</span>
            <span className="hint">/api/v1/health</span>
          </div>
          <div className="card-body">
            {!health ? (
              <div className="loading">检测中…</div>
            ) : (
              <dl className="kv">
                {Object.entries(health).map(([key, value]) => (
                  <div key={key} style={{ display: "contents" }}>
                    <dt>{key}</dt>
                    <dd>
                      {typeof value === "object" ? (
                        Object.entries(value as Record<string, number>)
                          .map(([k, v]) => `${k}: ${v}`)
                          .join("  ·  ") || "—"
                      ) : (
                        <span className={`badge ${value === "ok" ? "ok" : "error"}`}>{String(value)}</span>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
            {stats && (
              <p className="hint" style={{ marginTop: 16 }}>
                FAISS 向量 {num(stats.vectors)} · 分块 {num(stats.chunks)} · 文档 {num(stats.documents)} · 上传目录{" "}
                {bytes(stats.storage_bytes)}
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <span className="card-title">Prometheus 指标出口</span>
          <span className="hint">/metrics · 直接给 scrape 用</span>
        </div>
        <div className="card-body">
          {metrics.length === 0 ? (
            <div className="loading">没有读到指标（问答一次后再看）</div>
          ) : (
            <pre className="mono muted" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
              {metrics.map((m) => m.name).join("\n")}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
