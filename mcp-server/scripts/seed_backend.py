"""起后端 + 灌一份样例文档，用于 MCP server 冒烟（也可手动跑）。

用法：.venv\\Scripts\\python.exe mcp-server\\scripts\\seed_backend.py
它会常驻并打印 "READY"，Ctrl+C 结束。
"""
import os
import sys
import time

import httpx

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)


def main():
    base = os.getenv("LEGALRAG_BASE_URL", "http://127.0.0.1:8000")
    tenant = os.getenv("LEGALRAG_TENANT", "demo")
    pdf = os.path.join(REPO, "data", "e2e_tmp", "regulation_a.pdf")
    if not os.path.exists(pdf):
        print(f"缺样例 PDF：{pdf}（先跑 python docs/e2e_check.py 生成，或自己放一份）")
        sys.exit(1)

    for _ in range(120):
        try:
            if httpx.get(f"{base}/api/v1/health", timeout=5).status_code == 200:
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        print("后端没起来")
        sys.exit(1)

    with open(pdf, "rb") as f:
        r = httpx.post(
            f"{base}/api/v1/documents/upload",
            files={"file": (os.path.basename(pdf), f, "application/pdf")},
            headers={"X-Tenant-Id": tenant},
            timeout=120,
        )
    doc_id = r.json()["data"]["document_id"]
    for _ in range(180):
        st = httpx.get(f"{base}/api/v1/documents/{doc_id}/status",
                       headers={"X-Tenant-Id": tenant}, timeout=10).json()["data"]
        if st["processing_status"] in ("ready", "error"):
            print(f"READY doc_id={doc_id} status={st}")
            return
        time.sleep(2)
    print("索引超时")


if __name__ == "__main__":
    main()
