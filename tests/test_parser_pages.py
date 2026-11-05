"""页数回填：解析阶段才知道真实页数，上传时那条记录只有 0。

这两条断言守的是「前端列表里的页数不是摆设」：
parser 取得对，metadata_store 写得进。
"""
import fitz

from backend.models.document import Document
from backend.pipeline.parser import PDFParser
from backend.storage.metadata_store import MetadataStore


def _make_pdf(path, pages: int):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((54, 72), f"Article I. Page {i + 1}", fontsize=11, fontname="helv")
    doc.save(path)
    doc.close()
    return path


def test_parser_reports_page_count(tmp_path):
    pdf = _make_pdf(str(tmp_path / "three.pdf"), 3)
    assert PDFParser().page_count(pdf) == 3


def test_parser_returns_zero_for_missing_file(tmp_path):
    # 取不到就返回 0（前端显示「—」），不能让整条索引任务失败
    assert PDFParser().page_count(str(tmp_path / "nope.pdf")) == 0


def test_store_backfills_page_count(tmp_path):
    store = MetadataStore(db_path=str(tmp_path / "m.db"))
    doc_id = store.insert_document(Document(filename="a.pdf", tenant="demo"))
    assert store.get_document(doc_id, tenant="demo").page_count == 0

    assert store.set_page_count(doc_id, 7) is True
    assert store.get_document(doc_id, tenant="demo").page_count == 7
    assert store.set_page_count(9999, 3) is False
