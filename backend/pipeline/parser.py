import os

import fitz  # PyMuPDF
import pdfplumber


class PDFParser:
    """Extract text from PDF files using PyMuPDF with pdfplumber fallback.

    Per D-01: PyMuPDF (fitz) is the primary parser.
    Per D-02: pdfplumber fallback for complex layouts or when PyMuPDF fails.
    Per D-03: Supports text-based PDFs only (no OCR).

    Mitigations (threat model):
    - T-01-01: File path sanitized via os.path.basename(); paths with '..' rejected
    - T-01-02: max_file_size parameter (default 100MB); raises ValueError if exceeded
    """

    DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB

    def __init__(self, use_fallback: bool = False, max_file_size: int | None = None):
        """Initialize PDFParser.

        Args:
            use_fallback: When True, skip PyMuPDF and go directly to pdfplumber.
                          Used for testing.
            max_file_size: Maximum allowed file size in bytes.
                           Defaults to 100 MB. Set to None to disable.
        """
        self.use_fallback = use_fallback
        self.max_file_size = max_file_size if max_file_size is not None else self.DEFAULT_MAX_FILE_SIZE

    def extract_text(self, file_path: str) -> str:
        """Extract text from a PDF file.

        Args:
            file_path: Path to the PDF file.

        Returns:
            Extracted text content as a single string.

        Raises:
            ValueError: If file is too large, path is suspicious, or text
                        could not be extracted.
        """
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

    def _validate_path(self, file_path: str) -> None:
        """Validate file path for directory traversal attempts (T-01-01)."""
        basename = os.path.basename(file_path)
        if ".." in file_path or ".." in basename:
            raise ValueError(f"Invalid file path: {file_path}")

    def _check_file_size(self, file_path: str) -> None:
        """Check file size against max_file_size limit (T-01-02)."""
        if self.max_file_size is not None:
            actual_size = os.path.getsize(file_path)
            if actual_size > self.max_file_size:
                raise ValueError(
                    f"File size {actual_size} bytes exceeds maximum "
                    f"{self.max_file_size} bytes"
                )

    def _try_pymupdf(self, file_path: str) -> str | None:
        """Attempt text extraction using PyMuPDF (fitz)."""
        try:
            doc = fitz.open(file_path)
            text_parts = []
            for page in doc:
                blocks = page.get_text("blocks", sort=True)
                page_text = "\n".join(
                    b[4] for b in blocks if b[6] == 0  # block_type==0 is text
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
        """Attempt text extraction using pdfplumber (fallback)."""
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
