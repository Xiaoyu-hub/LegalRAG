"""前端 UI 冒烟：用真浏览器（系统 Edge）把三个页面走一遍。

跑法：
    python scripts\\ui_smoke.py                     # 默认 http://127.0.0.1:8000
    python scripts\\ui_smoke.py --headful           # 想自己看着它点

断言的是「人能不能用」：表格有行、上传后状态变绿、提问后出现带引用的答案、
召回来源能展开、用量页有数字。截图落在 docs/screenshots/。
"""
import argparse
import os
import sys
import time

from playwright.sync_api import sync_playwright

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "docs", "screenshots")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def _make_pdf() -> str:
    """现场生成一份带时间戳的小法规 PDF：每次上传都是新文件名，
    这样「列表行数变多」才可验证（同名会走替换分支，行数不变）。"""
    import tempfile

    import fitz

    stamp = time.strftime("%H%M%S")
    path = os.path.join(tempfile.gettempdir(), f"ui-smoke-{stamp}.pdf")
    lines = [
        "Article I. Smoke Test Provisions",
        "Section 1. Demo Clause",
        "(a) The retention period for audit records is ten business days.",
        "(b) The responsible officer shall publish a quarterly summary.",
    ]
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((54, y), line, fontsize=10, fontname="helv")
        y += 16
    doc.save(path)
    doc.close()
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--headful", action="store_true")
    ap.add_argument("--question", default="What is the maximum fine for a repeated infringement?")
    ap.add_argument("--upload", default="", help="指定要上传的 PDF；不传则现场生成一份")
    ap.add_argument("--no-upload", action="store_true", help="跳过上传环节")
    args = ap.parse_args()

    os.makedirs(SHOTS, exist_ok=True)
    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=EDGE, headless=not args.headful)
        page = browser.new_page(viewport={"width": 1440, "height": 940})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # ── 1. 文档库 ──
        page.goto(f"{args.base}/documents", wait_until="networkidle")
        page.wait_for_selector("table.list, .empty", timeout=20000)
        title = page.title()
        rows = page.locator("table.list tbody tr").count()
        check("文档库打开", "LegalRAG" in title, title)
        check("文档列表有数据", rows > 0, f"{rows} 行")
        page.screenshot(path=os.path.join(SHOTS, "01-documents.png"), full_page=True)

        # 点一下文件名，展开分段结构（这是后端 /chunks 的实数据）
        if rows > 0:
            page.locator("span.filename").first.click()
            page.wait_for_selector(".chunk-item", timeout=20000)
            chunks = page.locator(".chunk-item").count()
            check("分段结构可展开", chunks > 0, f"{chunks} 个 chunk")
            page.screenshot(path=os.path.join(SHOTS, "02-document-structure.png"), full_page=True)

        # 上传一份 PDF，走一遍后台索引 + 状态轮询（不传 --upload 就现场生成）
        if not args.no_upload:
            upload_path = args.upload or _make_pdf()
            before = page.locator("table.list tbody tr").count()
            page.set_input_files("input[type=file]", upload_path)
            ok = False
            for _ in range(90):
                page.wait_for_timeout(1000)
                page.reload(wait_until="networkidle")
                page.wait_for_selector("table.list, .empty", timeout=20000)
                badges = page.locator("table.list tbody tr td:nth-child(2)").all_inner_texts()
                if len(badges) > before and all("索引中" not in b for b in badges):
                    ok = True
                    break
            check("上传后索引完成", ok, os.path.basename(upload_path))

        # ── 2. 问答 ──
        page.goto(f"{args.base}/chat", wait_until="networkidle")
        page.wait_for_selector(".composer textarea", timeout=20000)
        # 新会话，避免接到历史里已有的消息
        page.get_by_role("button", name="新会话").click()
        page.wait_for_timeout(400)
        page.fill(".composer textarea", args.question)
        started = time.time()
        page.keyboard.press("Enter")
        page.wait_for_selector(".msg.assistant .bubble", timeout=120000)
        # 等流式结束：气泡里出现引用标记
        cite = page.locator(".msg.assistant .bubble .cite").first
        cite.wait_for(timeout=120000)
        elapsed = time.time() - started
        answer = page.locator(".msg.assistant .bubble").last.inner_text()
        check("拿到带引用的答案", "[Article" in answer, f"{elapsed:.1f}s")
        check("引用渲染成可点标签", page.locator(".msg.assistant .bubble .cite").count() > 0)

        # 展开召回来源
        toggle = page.locator(".sources-toggle").last
        if toggle.count() > 0:
            toggle.click()
            page.wait_for_selector(".source", timeout=20000)
            sources = page.locator(".source").count()
            check("召回来源可展开", sources > 0, f"{sources} 条")
        page.screenshot(path=os.path.join(SHOTS, "03-chat.png"), full_page=True)

        # 再问一句，验证同一会话里多轮 + 侧栏计数
        page.fill(".composer textarea", "When must a controller notify a breach?")
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        for _ in range(60):
            if page.locator(".msg.assistant").count() >= 2:
                break
            page.wait_for_timeout(1000)
        check("同一会话支持多轮", page.locator(".msg.assistant").count() >= 2,
              f"{page.locator('.msg.assistant').count()} 条回答")
        page.screenshot(path=os.path.join(SHOTS, "04-chat-multi-turn.png"), full_page=True)

        # ── 3. 用量 ──
        page.goto(f"{args.base}/usage", wait_until="networkidle")
        page.wait_for_selector(".stat-value", timeout=20000)
        stat_texts = page.locator(".stat-value").all_inner_texts()
        check("用量页有数字", any(t.strip() not in ("", "0") for t in stat_texts), " / ".join(stat_texts))
        check("指标出口有输出", page.locator("pre.mono").count() > 0)
        page.screenshot(path=os.path.join(SHOTS, "05-usage.png"), full_page=True)

        # ── 4. 刷新后仍是单页应用（SPA 回退）──
        page.goto(f"{args.base}/chat", wait_until="networkidle")
        page.wait_for_selector(".composer textarea", timeout=20000)
        check("刷新客户端路由不 404", page.locator(".composer textarea").count() == 1)

        browser.close()

    print("\n=== 汇总 ===")
    print(f"PASS {len(PASS)}  FAIL {len(FAIL)}")
    if errors:
        print("console errors:")
        for e in errors[:10]:
            print("   ", e)
    check("浏览器无 console 错误", len(errors) == 0, f"{len(errors)} 条")
    print(f"截图目录：{SHOTS}")
    if FAIL:
        print("失败项:", FAIL)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
