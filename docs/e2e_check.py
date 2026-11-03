"""端到端自检：用一套轻量语料把项目从上传跑到回答，逐项断言。

跑法（repo 根目录）：
    .venv\\Scripts\\python.exe docs\\e2e_check.py

覆盖：上传 → 解析/分块 → 索引（FAISS + BM25）→ 检索 → 网关问答 → 指标 → 重启一致性 → 同名覆盖。
不依赖 Ollama（LLM_PROVIDER=fake），但向量与重排用的是真模型。
"""
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import time

import fitz
import httpx

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8150
BASE = f"http://127.0.0.1:{PORT}"
TENANT = "e2e"
WORK = os.path.join(REPO, "data", "e2e_tmp")
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
           LLM_PROVIDER="fake", FAKE_LATENCY_MS="0")
# 本机可离线跑（模型已缓存）；CI 首次跑要联网拉模型，所以不能写死离线
if os.getenv("HF_HUB_OFFLINE"):
    ENV["HF_HUB_OFFLINE"] = os.environ["HF_HUB_OFFLINE"]

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


# ── 轻量语料：三份小 PDF ─────────────────────────────────────────────────

DOCS = {
    "regulation_a.pdf": """Article I. General Provisions
Section 1. Definitions
(a) "Person" means any individual or legal entity.
(b) "Business Day" means any day other than Saturday or Sunday.
Section 2. Scope of Application
(a) This Regulation applies to all legal persons within the jurisdiction.
Section 3. Interpretation
(a) Headings are for convenience only.
Article II. Rights and Obligations
Section 1. Rights of Data Subjects
(a) Every data subject may request access to personal data.
Section 2. Obligations of Controllers
(a) Controllers shall implement appropriate technical measures.
""",
    "regulation_b.pdf": """Article I. Enforcement and Penalties
Section 1. Regulatory Authority
(a) The Regulatory Authority shall supervise compliance.
Section 2. Investigations
(a) The Authority may request documents and records.
Section 3. Administrative Penalties
(a) A fine not exceeding five thousand dollars may be imposed.
(b) Repeated violations may lead to suspension of operations.
Article II. Appeals
Section 1. Right of Appeal
(a) An affected party may appeal within thirty days.
Section 2. Procedure
(a) Appeals shall be filed in writing with the Authority.
""",
    "regulation_c.pdf": """Article I. Data Processing Agreements
Section 1. Mandatory Clauses
(a) Processing agreements shall specify purpose and duration.
(b) The processor shall act only on documented instructions.
Section 2. Cross-Border Transfer
(a) Transfers require an adequacy decision.
Section 3. Records of Processing
(a) Each controller shall maintain records of processing activities.
Article II. Security
Section 1. Technical Measures
(a) Encryption at rest and in transit shall be applied.
Section 2. Breach Notification
(a) Breaches shall be notified within seventy-two hours.
""",
}


def make_pdfs():
    os.makedirs(WORK, exist_ok=True)
    paths = {}
    for name, text in DOCS.items():
        path = os.path.join(WORK, name)
        doc = fitz.open()
        page = doc.new_page()
        y = 50
        for line in text.split("\n"):
            if y > 780:
                page = doc.new_page()
                y = 50
            if line:
                page.insert_text((50, y), line, fontsize=10, fontname="helv")
            y += 14
        doc.save(path)
        doc.close()
        paths[name] = path
    return paths


# ── 服务生命周期 ─────────────────────────────────────────────────────────

def start_server(tag):
    log = open(os.path.join(WORK, f"server_{tag}.log"), "w", encoding="utf-8")
    # 用当前解释器：Windows 是 .venv/Scripts/python.exe，Linux CI 是 .venv/bin/python，
    # 写死路径会在 CI 上报 FileNotFoundError
    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn",
         "backend.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=REPO, env=ENV, stdout=log, stderr=subprocess.STDOUT,
    )
    t0 = time.time()
    while time.time() - t0 < 240:
        try:
            if httpx.get(f"{BASE}/api/v1/health", timeout=10).status_code == 200:
                return p, log
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("服务没能起来，见 logs")


def stop(p, log):
    p.terminate()
    try:
        p.wait(timeout=20)
    except Exception:
        p.kill()
    log.close()


def db_ids(tenant):
    conn = sqlite3.connect(os.path.join(REPO, "data", "metadata.db"))
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM chunks WHERE tenant = ? ORDER BY id", (tenant,))]
    conn.close()
    return ids


def upload(path, tenant=TENANT):
    with open(path, "rb") as f:
        r = httpx.post(f"{BASE}/api/v1/documents/upload",
                       files={"file": (os.path.basename(path), f, "application/pdf")},
                       headers={"X-Tenant-Id": tenant}, timeout=180)
    data = r.json()["data"]
    doc_id = data["document_id"]
    for _ in range(180):
        st = httpx.get(f"{BASE}/api/v1/documents/{doc_id}/status",
                       headers={"X-Tenant-Id": tenant}, timeout=10).json()["data"]
        if st["processing_status"] in ("ready", "error"):
            return doc_id, st
        time.sleep(2)
    return doc_id, {"processing_status": "timeout"}


def main():
    print("=== 1. 准备语料 ===")
    pdfs = make_pdfs()
    print(f"  生成 {len(pdfs)} 份 PDF 到 {WORK}")

    # 清库，便于复现（先过一遍 MetadataStore，让老库自动补 tenant 列）
    sys.path.insert(0, REPO)
    os.chdir(REPO)
    from backend.storage.metadata_store import MetadataStore  # noqa: E402
    MetadataStore(db_path=os.path.join(REPO, "data", "metadata.db"))

    conn = sqlite3.connect(os.path.join(REPO, "data", "metadata.db"))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("DELETE FROM documents WHERE tenant = ?", (TENANT,))
    conn.commit()
    conn.close()
    idx_dir = os.path.join(REPO, "data", "index", TENANT)
    if os.path.isdir(idx_dir):
        for f in os.listdir(idx_dir):
            os.remove(os.path.join(idx_dir, f))

    p, log = start_server("a")
    try:
        print("\n=== 2. 上传与索引 ===")
        counts = {}
        for name, path in pdfs.items():
            doc_id, st = upload(path)
            counts[name] = st.get("chunk_count", 0)
            check(f"上传 {name} 且索引完成",
                  st.get("processing_status") == "ready" and st.get("chunk_count", 0) > 0,
                  f"doc_id={doc_id} chunks={st.get('chunk_count')}")

        ids = db_ids(TENANT)
        check("chunk 全部入库", len(ids) == sum(counts.values()),
              f"db={len(ids)} 状态合计={sum(counts.values())}")

        print("\n=== 3. 检索 ===")
        cases = [
            ("What is the definition of Business Day?", "regulation_a"),
            ("maximum fine for administrative penalties", "regulation_b"),
            ("how many hours to notify a breach", "regulation_c"),
        ]
        all_ids = set(ids)
        for q, expect_doc in cases:
            r = httpx.post(f"{BASE}/api/v1/search/", json={"query": q, "top_k": 5},
                           headers={"X-Tenant-Id": TENANT}, timeout=180)
            results = r.json()["data"]["results"]
            got = [x["chunk_id"] for x in results]
            ok_ids = set(got) <= all_ids
            scores = [x["score"] for x in results]
            ordered = all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))
            check(f"检索「{q[:32]}…」返回合法 chunk_id", ok_ids and len(got) > 0,
                  f"top1={got[0] if got else None}")
            check(f"  分数降序", ordered)
            top = results[0] if results else {}
            check(f"  命中包含条文元数据", bool(top.get("article") and top.get("section")),
                  f"{top.get('article')}/{top.get('section')}")

        print("\n=== 4. 网关问答 ===")
        r = httpx.post(f"{BASE}/api/v1/gateway/chat",
                       json={"question": "What is the definition of Business Day?"},
                       headers={"X-Tenant-Id": TENANT}, timeout=180)
        body = r.json()
        check("网关返回 200", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            d = body["data"]
            check("返回答案与用量",
                  bool(d["answer"]) and d["prompt_tokens"] > 0 and d["completion_tokens"] > 0,
                  f"tokens={d['prompt_tokens']}+{d['completion_tokens']} cost={d['cost_usd']}")

        print("\n=== 5. 同名重传不叠加 ===")
        before = len(db_ids(TENANT))
        doc_id, st = upload(pdfs["regulation_a.pdf"])
        after = len(db_ids(TENANT))
        check("同名重传后 chunk 数不翻倍", after <= before,
              f"{before} -> {after}（replaced 走删除重建）")

        print("\n=== 6. 指标 ===")
        m = httpx.get(f"{BASE}/metrics", timeout=30).text
        check("有 llm_requests_total", "llm_requests_total" in m)
        check("有 llm_tokens_total", 'llm_tokens_total{kind="prompt"' in m)
        check("有 llm_cost_usd_total", "llm_cost_usd_total" in m)

        print("\n=== 7. 重启一致性 ===")
        q = "maximum fine for administrative penalties"
        before_res = [x["chunk_id"] for x in httpx.post(
            f"{BASE}/api/v1/search/", json={"query": q, "top_k": 5},
            headers={"X-Tenant-Id": TENANT}, timeout=180).json()["data"]["results"]]
    finally:
        stop(p, log)

    p, log = start_server("b")
    try:
        after_res = [x["chunk_id"] for x in httpx.post(
            f"{BASE}/api/v1/search/", json={"query": q, "top_k": 5},
            headers={"X-Tenant-Id": TENANT}, timeout=180).json()["data"]["results"]]
        check("重启前后检索结果一致", before_res == after_res,
              f"{before_res} vs {after_res}")
        check("重启后 id 仍全在库内", set(after_res) <= set(db_ids(TENANT)))
        txt = open(os.path.join(WORK, "server_b.log"), encoding="utf-8", errors="ignore").read()
        check("启动日志记录了索引加载", "Loaded FAISS index" in txt)
    finally:
        stop(p, log)

    print("\n=== 汇总 ===")
    print(f"PASS {len(PASS)}  FAIL {len(FAIL)}")
    if FAIL:
        for f in FAIL:
            print("  失败项:", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
