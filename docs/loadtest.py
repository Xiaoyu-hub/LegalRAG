"""并发压测：并发 vs P50/P95/P99 vs 每千 token 成本。

两段：
  A. 检索链路 /api/v1/search（真模型、真 FAISS、真重排）——测 CPU 型接口在并发下的表现
  B. 网关链路 /api/v1/gateway/chat（FakeProvider + 人为 30ms 延迟）——测网关自身开销与配额

输出 Markdown 表格，直接可贴进文档/简历。
"""
import asyncio
import json
import os
import statistics
import subprocess
import time

import httpx

REPO = r"D:\program\open\legalrag"
PDF = r"D:\tmp\legalrag_verify\sample_legal.pdf"
PORT = 8143
BASE = f"http://127.0.0.1:{PORT}"
TENANT = "bench"
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
           HF_HUB_OFFLINE="1", LLM_PROVIDER="fake", FAKE_LATENCY_MS="30")


def pct(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round((p / 100.0) * (len(values) - 1)))))
    return values[k]


async def run_level(client, url, body, headers, concurrency, total):
    """固定总请求数、固定并发度，返回 (wall, latencies, statuses)。"""
    sem = asyncio.Semaphore(concurrency)
    latencies = []
    statuses = []

    async def one():
        async with sem:
            t0 = time.perf_counter()
            try:
                r = await client.post(url, json=body, headers=headers, timeout=300)
                statuses.append(r.status_code)
            except Exception:
                statuses.append(-1)
            latencies.append((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    await asyncio.gather(*[one() for _ in range(total)])
    wall = time.perf_counter() - t0
    return wall, latencies, statuses


async def bench(client, label, url, body, headers, levels, total):
    rows = []
    for c in levels:
        wall, lat, st = await run_level(client, url, body, headers, c, total)
        ok = sum(1 for s in st if s == 200)
        rows.append({
            "label": label, "concurrency": c, "total": total, "ok": ok,
            "wall_s": wall, "rps": total / wall,
            "p50": pct(lat, 50), "p95": pct(lat, 95), "p99": pct(lat, 99),
            "mean": statistics.fmean(lat),
            "errors": len([s for s in st if s != 200]),
            "statuses": sorted(set(st)),
        })
        print(f"  {label} c={c:<3} wall={wall:6.2f}s rps={total/wall:7.2f} "
              f"p50={pct(lat,50):7.1f}ms p95={pct(lat,95):7.1f}ms p99={pct(lat,99):7.1f}ms "
              f"ok={ok}/{total} status={sorted(set(st))}")
    return rows


def metric_value(text, name, **labels):
    """从 /metrics 文本里抠某个样本的值。"""
    for line in text.splitlines():
        if not line.startswith(name + "{"):
            continue
        if all(f'{k}="{v}"' in line for k, v in labels.items()):
            return float(line.rsplit(" ", 1)[1])
    return 0.0


def main():
    log = open(r"D:\tmp\legalrag_verify\server_load.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [os.path.join(REPO, ".venv", "Scripts", "python.exe"), "-m", "uvicorn",
         "backend.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=REPO, env=ENV, stdout=log, stderr=subprocess.STDOUT,
    )
    try:
        t0 = time.time()
        while time.time() - t0 < 240:
            try:
                if httpx.get(f"{BASE}/api/v1/health", timeout=10).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(3)

        # 准备数据：往 bench 租户上传一份 PDF
        with open(PDF, "rb") as f:
            doc_id = httpx.post(f"{BASE}/api/v1/documents/upload",
                                files={"file": ("bench.pdf", f, "application/pdf")},
                                headers={"X-Tenant-Id": TENANT}, timeout=120).json()["data"]["document_id"]
        for _ in range(180):
            st = httpx.get(f"{BASE}/api/v1/documents/{doc_id}/status",
                           headers={"X-Tenant-Id": TENANT}, timeout=10).json()
            if st["data"]["processing_status"] in ("ready", "error"):
                break
            time.sleep(2)
        print("索引就绪:", st["data"])

        before = httpx.get(f"{BASE}/metrics", timeout=30).text

        async def main_async():
            limits = httpx.Limits(max_connections=64, max_keepalive_connections=64)
            async with httpx.AsyncClient(limits=limits) as client:
                search_rows = await bench(
                    client, "search", f"{BASE}/api/v1/search/",
                    {"query": "definition of Business Day", "top_k": 5},
                    {"X-Tenant-Id": TENANT}, [1, 4, 8], 24)

                gateway_rows = await bench(
                    client, "gateway", f"{BASE}/api/v1/gateway/chat",
                    {"question": "hi"}, {"X-Tenant-Id": TENANT}, [1, 8, 16], 48)
            return search_rows, gateway_rows

        search_rows, gateway_rows = asyncio.run(main_async())

        after = httpx.get(f"{BASE}/metrics", timeout=30).text

        # 每千 token 的成本：从 metrics 差值算
        tok_before = (metric_value(before, "llm_tokens_total", tenant=TENANT, kind="prompt")
                      + metric_value(before, "llm_tokens_total", tenant=TENANT, kind="completion"))
        tok_after = (metric_value(after, "llm_tokens_total", tenant=TENANT, kind="prompt")
                     + metric_value(after, "llm_tokens_total", tenant=TENANT, kind="completion"))
        cost_after = metric_value(after, "llm_cost_usd_total", tenant=TENANT)
        tokens = tok_after - tok_before
        total_gw = sum(r["total"] for r in gateway_rows)
        total_wall = sum(r["wall_s"] for r in gateway_rows)

        print("\n=== 汇总 ===")
        print(f"网关调用 {total_gw} 次，累计 {tokens:.0f} token，累计成本 ${cost_after:.6f}")
        if tokens:
            print(f"每千 token 成本: ${cost_after / tokens * 1000:.6f}（本地模型按 0 计价）")
            print(f"每千 token 的墙钟时间: {total_wall / tokens * 1000:.3f} 秒")

        out = {
            "search": search_rows,
            "gateway": gateway_rows,
            "tokens": tokens,
            "cost_usd": cost_after,
            "per_1k_tokens_cost": (cost_after / tokens * 1000) if tokens else 0.0,
            "per_1k_tokens_wall_s": (total_wall / tokens * 1000) if tokens else 0.0,
        }
        with open(r"D:\tmp\legalrag_verify\loadtest.json", "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print("\n结果已写 D:\\tmp\\legalrag_verify\\loadtest.json")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()
        log.close()


if __name__ == "__main__":
    main()
