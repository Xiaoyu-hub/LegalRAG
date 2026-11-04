"""入库流水线测试共用的 fixture。"""

from pathlib import Path
import pytest


@pytest.fixture
def sample_pdf_text() -> str:
    """返回样例法条文档的全文。"""
    fixture_path = Path(__file__).parent.parent / "data" / "test" / "sample_legal.txt"
    return fixture_path.read_text(encoding="utf-8")


@pytest.fixture
def sample_pdf_path(tmp_path) -> Path:
    """把样例法条文本写进临时 .txt，供结构抽取测试用。
    当时还没有真 PDF，所以直接用 fixture 文本；这个 fixture 只是给「需要文件路径」的模块一个临时文件。"""
    fixture_path = Path(__file__).parent.parent / "data" / "test" / "sample_legal.txt"
    text = fixture_path.read_text(encoding="utf-8")
    tmp_file = tmp_path / "sample_legal.txt"
    tmp_file.write_text(text, encoding="utf-8")
    return tmp_file


@pytest.fixture
def temp_db_path(tmp_path) -> str:
    """给元数据存储测试返回一个临时 SQLite 路径。"""
    return str(tmp_path / "test_metadata.db")
