import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { TENANTS, getHealth, getTenant, setTenant } from "./api";
import Documents from "./pages/Documents";
import Chat from "./pages/Chat";
import Usage from "./pages/Usage";

const NAV = [
  { to: "/documents", label: "文档库", idx: "01" },
  { to: "/chat", label: "检索问答", idx: "02" },
  { to: "/usage", label: "用量与健康", idx: "03" },
];

export default function App() {
  const [tenant, setTenantState] = useState(getTenant());
  const [health, setHealth] = useState<"up" | "down" | "unknown">("unknown");

  // 侧栏底部的健康点：只回答「后端还活着吗」，细节在「用量与健康」页
  useEffect(() => {
    let alive = true;
    const ping = async () => {
      try {
        await getHealth();
        if (alive) setHealth("up");
      } catch {
        if (alive) setHealth("down");
      }
    };
    ping();
    const timer = window.setInterval(ping, 30000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [tenant]);

  const onTenant = (value: string) => {
    setTenant(value);
    setTenantState(value);
    // 换租户等于换一整套数据视角，整页重载最不容易留下脏状态
    window.location.reload();
  };

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">LR</div>
          <div>
            <div className="brand-name">LegalRAG</div>
            <div className="brand-sub">多租户 RAG 服务 · LLM 网关</div>
          </div>
        </div>

        <nav className="nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <span>{item.label}</span>
              <span className="idx">{item.idx}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-foot">
          <label className="hint" htmlFor="tenant">
            租户（X-Tenant-Id）
          </label>
          <select
            id="tenant"
            className="select"
            value={tenant}
            onChange={(e) => onTenant(e.target.value)}
          >
            {TENANTS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <div className="row" style={{ gap: 8 }}>
            <span className={`badge ${health === "up" ? "ok" : health === "down" ? "error" : "plain"}`}>
              {health === "up" ? "API 在线" : health === "down" ? "API 不可达" : "检测中"}
            </span>
          </div>
        </div>
      </aside>

      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/documents" replace />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/usage" element={<Usage />} />
          <Route path="*" element={<Navigate to="/documents" replace />} />
        </Routes>
      </main>
    </div>
  );
}
