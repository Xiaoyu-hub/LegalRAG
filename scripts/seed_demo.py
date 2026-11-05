"""生成一套演示语料并灌进后端。

用法（先起服务，再跑脚本）：
    .venv\\Scripts\\python.exe scripts\\seed_demo.py --tenant demo
    .venv\\Scripts\\python.exe scripts\\seed_demo.py --base http://127.0.0.1:8000 --no-wait

为什么要有这个脚本：
- 演示 / 截图 / 面试时手点上传太慢，而且要保证每次语料一致；
- 语料是三份英文法规（与项目的英文法条切分策略匹配），
  中文文书切不出 Article/Section 结构，引用链会断，所以不放进来。

PDF 用 PyMuPDF 现场生成：不往仓库里塞二进制样本，语料改动就是改这个文件。
"""
import argparse
import io
import os
import sys
import time

import fitz
import httpx

# ── 语料 ────────────────────────────────────────────────────────────────
# 每条 60~110 行，保证能切出十几个 chunk；条文编号用罗马数字，
# 与 structure_extractor 的 article 正则（[IVXLCDM]+|\d+）一致。

DOCS = {
    "data-protection-regulation-2025.pdf": """Article I. General Provisions
Section 1. Purpose and Scope
(a) This Regulation establishes rules for the processing of personal data.
(b) It applies to every controller and processor established within the jurisdiction.
(c) It does not apply to processing carried out by a natural person for household purposes.
Section 2. Definitions
(a) "Personal Data" means any information relating to an identified or identifiable person.
(b) "Processing" means any operation performed on personal data, including collection and storage.
(c) "Controller" means the entity that determines the purposes of processing.
(d) "Processor" means the entity that processes personal data on behalf of a controller.
(e) "Business Day" means any day other than Saturday, Sunday or a public holiday.
Section 3. Principles of Processing
(a) Personal data shall be processed lawfully, fairly and in a transparent manner.
(b) Data shall be collected for specified and legitimate purposes only.
(c) Data shall be adequate, relevant and limited to what is necessary.
(d) Data shall be accurate and kept up to date where necessary.
Article II. Rights of the Data Subject
Section 1. Right of Access
(a) Every data subject may request confirmation of whether personal data is processed.
(b) The controller shall provide a copy of the personal data free of charge.
(c) The controller shall respond within thirty days of the request.
Section 2. Right to Rectification and Erasure
(a) A data subject may request correction of inaccurate personal data.
(b) A data subject may request erasure where the data is no longer necessary.
(c) Erasure requests shall be completed within thirty days.
Section 3. Right to Object
(a) A data subject may object to processing based on legitimate interests.
(b) The controller shall stop processing unless it demonstrates compelling grounds.
Article III. Obligations of Controllers
Section 1. Records of Processing
(a) Each controller shall maintain a record of processing activities.
(b) The record shall describe categories of data, purposes and retention periods.
Section 2. Data Protection Officer
(a) A controller employing more than two hundred and fifty persons shall appoint an officer.
(b) The officer shall be involved in all matters of personal data protection.
Section 3. Security Measures
(a) Controllers shall implement encryption at rest and in transit.
(b) Access to personal data shall be restricted to authorised personnel.
(c) Security measures shall be reviewed at least once every twelve months.
Section 4. Impact Assessment
(a) A controller shall carry out an impact assessment before high risk processing.
(b) The assessment shall describe the necessity and proportionality of processing.
Article IV. Breach Notification
Section 1. Notification to the Authority
(a) A controller shall notify the supervisory authority within seventy-two hours of a breach.
(b) The notification shall describe the nature of the breach and the data affected.
(c) Where notification is late, the controller shall explain the delay.
Section 2. Notification to Data Subjects
(a) Affected data subjects shall be informed without undue delay where risk is high.
(b) Notification shall describe the likely consequences and the measures taken.
Article V. Cross-Border Transfers
Section 1. Adequacy Decisions
(a) A transfer outside the jurisdiction requires an adequacy decision.
(b) The authority shall review adequacy decisions every four years.
Section 2. Standard Contractual Clauses
(a) In the absence of an adequacy decision, standard clauses may be used.
(b) The processor shall act only on documented instructions of the controller.
Article VI. Final Provisions
Section 1. Penalties
(a) An infringement of Article III may be fined up to two percent of annual turnover.
(b) An infringement of Article IV may be fined up to four percent of annual turnover.
Section 2. Entry into Force
(a) This Regulation enters into force ninety days after publication.
""",
    "administrative-penalties-act-2024.pdf": """Article I. Enforcement Framework
Section 1. Regulatory Authority
(a) The Regulatory Authority is established as an independent body.
(b) The Authority shall supervise compliance with applicable regulations.
(c) The Authority may delegate inspection powers to regional offices.
Section 2. Inspections
(a) The Authority may request documents and records from regulated entities.
(b) Inspections shall be conducted during business hours with prior notice of five days.
(c) An entity may refuse entry only where a court order prohibits inspection.
Section 3. Evidence and Records
(a) Records shall be retained for a period of six years.
(b) Electronic records are admissible where authenticity can be verified.
Article II. Administrative Penalties
Section 1. Types of Penalty
(a) The Authority may issue a warning, a fine or a suspension of operations.
(b) Penalties shall be proportionate to the seriousness of the infringement.
(c) A warning may be issued for a first minor infringement.
Section 2. Calculation of Fines
(a) A fine not exceeding five thousand dollars may be imposed for a minor infringement.
(b) A fine not exceeding fifty thousand dollars may be imposed for a serious infringement.
(c) A fine not exceeding two hundred thousand dollars may be imposed for a repeated infringement.
(d) The Authority shall consider turnover, intent and remediation efforts.
Section 3. Suspension of Operations
(a) Repeated violations may lead to suspension of operations for up to six months.
(b) Suspension shall be ordered only where a fine is insufficient.
Section 4. Settlement
(a) An entity may settle a case by admitting the facts and paying the fine.
(b) Settlement shall be completed within twenty business days.
Article III. Appeals
Section 1. Right of Appeal
(a) An affected party may appeal within thirty days of the decision.
(b) The appeal shall be filed in writing with the Appeals Board.
Section 2. Procedure
(a) The Appeals Board shall hold a hearing within sixty days.
(b) The Board may confirm, reduce or annul the penalty.
(c) A decision of the Board is final unless a court rules otherwise.
Section 3. Judicial Review
(a) A party may seek judicial review within ninety days of the Board decision.
Article IV. Cooperation and Reporting
Section 1. Annual Reporting
(a) The Authority shall publish an annual report on enforcement activity.
(b) The report shall list the number of inspections and the total fines imposed.
Section 2. Cross-Agency Cooperation
(a) The Authority shall share information with tax and customs authorities.
(b) Shared information shall be used only for enforcement purposes.
""",
    "cross-border-data-transfer-guidelines.pdf": """Article I. Transfer Mechanisms
Section 1. General Rule
(a) A transfer of personal data outside the jurisdiction requires a lawful mechanism.
(b) The exporter remains responsible for the lawfulness of the transfer.
Section 2. Adequacy Assessment
(a) The Authority shall assess the legal framework of the recipient country.
(b) The assessment shall consider access by public authorities and redress mechanisms.
(c) An adequacy decision is valid for four years.
Section 3. Contractual Safeguards
(a) Standard contractual clauses require prior authorisation from the Authority.
(b) The clauses shall bind the importer to the same obligations as the exporter.
(c) A transfer impact assessment shall accompany the clauses.
Article II. Records and Accountability
Section 1. Transfer Register
(a) Each exporter shall maintain a register of transfers.
(b) The register shall record the recipient, the purpose and the mechanism used.
(c) The register shall be provided to the Authority on request within ten business days.
Section 2. Data Protection Officer Approval
(a) Transfers of sensitive data require approval by the data protection officer.
(b) The officer shall record the approval in the transfer register.
Article III. Prohibited Transfers
Section 1. Suspension by the Authority
(a) The Authority may suspend a transfer where safeguards are insufficient.
(b) Suspension takes effect immediately and shall be notified in writing.
Section 2. Onward Transfers
(a) An importer shall not transfer data onward without written consent.
(b) Onward transfers are subject to the same mechanism as the original transfer.
""",
}


def build_pdf(lines: list[str]) -> bytes:
    """把文本行渲成 PDF；英文语料用内置 helv 字体，避免依赖系统字体。"""
    doc = fitz.open()
    page = doc.new_page()
    y = 60
    for line in lines:
        if y > 780:
            page = doc.new_page()
            y = 60
        page.insert_text((54, y), line, fontsize=9.5, fontname="helv")
        y += 13.5
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def wait_ready(client: httpx.Client, doc_id: int, headers: dict, timeout: float = 240):
    started = time.time()
    while time.time() - started < timeout:
        resp = client.get(f"/api/v1/documents/{doc_id}/status", headers=headers)
        data = resp.json().get("data") or {}
        status = data.get("processing_status")
        if status in ("ready", "error"):
            return status, data.get("chunk_count", 0)
        time.sleep(1.5)
    return "timeout", 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.getenv("LEGALRAG_BASE", "http://127.0.0.1:8000"))
    ap.add_argument("--tenant", default=os.getenv("LEGALRAG_TENANT", "demo"))
    ap.add_argument("--no-wait", action="store_true", help="只上传，不等索引")
    ap.add_argument("--out", default="data/demo_corpus", help="生成的 PDF 落地目录")
    args = ap.parse_args()

    headers = {"X-Tenant-Id": args.tenant}
    os.makedirs(args.out, exist_ok=True)

    ok = True
    with httpx.Client(base_url=args.base, timeout=300) as client:
        health = client.get("/api/v1/health")
        if health.status_code != 200:
            print(f"后端不可用：{args.base}/api/v1/health → {health.status_code}")
            return 1

        for name, text in DOCS.items():
            pdf = build_pdf(text.split("\n"))
            local = os.path.join(args.out, name)
            with open(local, "wb") as f:
                f.write(pdf)

            resp = client.post(
                "/api/v1/documents/upload",
                files={"file": (name, pdf, "application/pdf")},
                headers=headers,
            )
            body = resp.json()
            if body.get("status") != "ok":
                print(f"[FAIL] {name}: {body.get('error')}")
                ok = False
                continue
            doc_id = body["data"]["document_id"]
            print(f"[upload] {name} → doc_id={doc_id} ({len(pdf)} bytes)")

            if not args.no_wait:
                status, chunks = wait_ready(client, doc_id, headers)
                flag = "ok" if status == "ready" else "FAIL"
                print(f"[{flag}] {name} status={status} chunks={chunks}")
                ok = ok and status == "ready"

        stats = client.get("/api/v1/stats", headers=headers).json().get("data") or {}
        print(
            f"\n租户 {args.tenant}: 文档 {stats.get('documents')} · "
            f"分块 {stats.get('chunks')} · 向量 {stats.get('vectors')}"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
