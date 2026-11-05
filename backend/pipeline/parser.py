import os

import fitz  # PyMuPDF
import pdfplumber


class PDFParser:
    """PDF 文本抽取：主用 PyMuPDF，失败则回退 pdfplumber。
    - D-01：PyMuPDF（fitz）为主
    - D-02：复杂版式或主解析器失败时走 pdfplumber 兜底
    - D-03：只支持文本型 PDF（不做 OCR）
    威胁缓解：
    - T-01-01：用 os.path.basename() 清洗路径，含 '..' 的拒绝
    - T-01-02：max_file_size 参数（默认 100 MB），超出直接抛 ValueError"""

    DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB

    def __init__(self, use_fallback: bool = False, max_file_size: int | None = None):
        """初始化解析器。
        参数：
        - use_fallback：为 True 时跳过 PyMuPDF 直接用 pdfplumber（测试用）
        - max_file_size：允许的最大字节数，默认 100 MB，设 None 表示不限制"""
        self.use_fallback = use_fallback
        self.max_file_size = max_file_size if max_file_size is not None else self.DEFAULT_MAX_FILE_SIZE

    def extract_text(self, file_path: str) -> str:
        """从 PDF 抽取文本。
        参数：file_path —— PDF 路径
        返回：整篇文本字符串
        异常：文件过大、路径可疑、或抽不出文本时抛 ValueError"""
        self._validate_path(file_path)
        self._check_file_size(file_path)

        if not self.use_fallback:
            text = self._try_pymupdf(file_path)
            if text:
                return text

        text = self._try_pdfplumber(file_path)
        if text:
            return text

        raise ValueError("Could not extract text from PDF")

    def page_count(self, file_path: str) -> int:
        """PDF 页数。

        单独一个方法而不是让 extract_text() 返回元组：现有调用点（单测、e2e、
        Indexer）都按「返回字符串」写的，改返回值会连锁改一圈，收益不值。
        取不到就返回 0，让前端显示「—」而不是把整条索引任务弄失败。
        """
        try:
            doc = fitz.open(file_path)
            count = doc.page_count
            doc.close()
            return count
        except Exception:
            return 0

    def _validate_path(self, file_path: str) -> None:
        """校验路径是否试图目录穿越（T-01-01）。"""
        basename = os.path.basename(file_path)
        if ".." in file_path or ".." in basename:
            raise ValueError(f"Invalid file path: {file_path}")

    def _check_file_size(self, file_path: str) -> None:
        """检查文件大小是否超过 max_file_size 上限（T-01-02）。"""
        if self.max_file_size is not None:
            actual_size = os.path.getsize(file_path)
            if actual_size > self.max_file_size:
                raise ValueError(
                    f"File size {actual_size} bytes exceeds maximum "
                    f"{self.max_file_size} bytes"
                )

    def _try_pymupdf(self, file_path: str) -> str | None:
        """用 PyMuPDF（fitz）尝试抽取文本。"""
        try:
            doc = fitz.open(file_path)
            text_parts = []
            for page in doc:
                blocks = page.get_text("blocks", sort=True)
                page_text = "\n".join(
                    b[4] for b in blocks if b[6] == 0  # block_type==0 表示文本块
                )
                text_parts.append(page_text)
            doc.close()
            full_text = "\n".join(text_parts)
            if full_text.strip():
                return full_text
        except Exception:
            pass
        return None

    def _try_pdfplumber(self, file_path: str) -> str | None:
        """用 pdfplumber 兜底抽取文本。"""
        try:
            with pdfplumber.open(file_path) as pdf:
                text_parts = [
                    page.extract_text(layout=True) for page in pdf.pages
                ]
            full_text = "\n".join(text_parts)
            if full_text.strip():
                return full_text
        except Exception:
            pass
        return None
