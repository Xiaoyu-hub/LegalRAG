"""Shared test fixtures for the ingestion pipeline tests."""

from pathlib import Path
import pytest


@pytest.fixture
def sample_pdf_text() -> str:
    """Return the content of the sample legal document."""
    fixture_path = Path(__file__).parent.parent / "data" / "test" / "sample_legal.txt"
    return fixture_path.read_text(encoding="utf-8")


@pytest.fixture
def sample_pdf_path(tmp_path) -> Path:
    """Write the sample legal text to a temp .txt file for structure testing.

    In Task 1 there is no real PDF — the test fixture text is used directly.
    This fixture provides a temp file path for modules that need file input.
    """
    fixture_path = Path(__file__).parent.parent / "data" / "test" / "sample_legal.txt"
    text = fixture_path.read_text(encoding="utf-8")
    tmp_file = tmp_path / "sample_legal.txt"
    tmp_file.write_text(text, encoding="utf-8")
    return tmp_file


@pytest.fixture
def temp_db_path(tmp_path) -> str:
    """Return a temporary SQLite database path for MetadataStore tests."""
    return str(tmp_path / "test_metadata.db")
