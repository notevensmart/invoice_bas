from __future__ import annotations

from app.engine.ocr import PDFTextExtractor
from app.engine.schemas import ExtractionStatus
from app.tests.conftest import FIXTURE_ROOT


def test_ocr_extracts_text_from_readable_pdf_fixture():
    pdf_path = FIXTURE_ROOT / "invoices" / "clean_under_1000.pdf"
    result = PDFTextExtractor().extract_from_path(pdf_path, "doc_pdf")

    assert result.status == ExtractionStatus.SUCCESS
    assert result.method == "pdf_text"
    assert "Metro Coffee Roasters Pty Ltd" in result.text


def test_ocr_empty_or_invalid_pdf_bytes_fail_explicitly():
    result = PDFTextExtractor().extract(b"", "doc_empty")

    assert result.status == ExtractionStatus.FAILED
    assert result.text == ""
    assert result.warnings
