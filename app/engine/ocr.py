from __future__ import annotations

from io import BytesIO
from pathlib import Path

from app.engine.schemas import ExtractionStatus, OCRResult


class PDFTextExtractor:
    def extract(self, file_bytes: bytes, document_id: str) -> OCRResult:
        warnings: list[str] = []
        text = self._extract_pdf_text(file_bytes, warnings)
        if text.strip():
            return OCRResult(
                document_id=document_id,
                text=text.strip(),
                method="pdf_text",
                status=ExtractionStatus.SUCCESS,
                warnings=warnings,
            )

        ocr_text = self._extract_ocr_text(file_bytes, warnings)
        if ocr_text.strip():
            return OCRResult(
                document_id=document_id,
                text=ocr_text.strip(),
                method="tesseract_ocr",
                status=ExtractionStatus.SUCCESS,
                warnings=warnings,
            )

        if not warnings:
            warnings.append("No text could be extracted from the PDF.")
        return OCRResult(
            document_id=document_id,
            text="",
            method="none",
            status=ExtractionStatus.FAILED,
            warnings=warnings,
        )

    def extract_from_path(self, path: str | Path, document_id: str) -> OCRResult:
        return self.extract(Path(path).read_bytes(), document_id)

    def _extract_pdf_text(self, file_bytes: bytes, warnings: list[str]) -> str:
        try:
            from PyPDF2 import PdfReader
        except Exception as exc:  # pragma: no cover - depends on optional install
            warnings.append(f"PyPDF2 unavailable: {exc}")
            return ""

        try:
            reader = PdfReader(BytesIO(file_bytes))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            warnings.append(f"PDF text extraction failed: {exc}")
            return ""

    def _extract_ocr_text(self, file_bytes: bytes, warnings: list[str]) -> str:
        try:
            from pdf2image import convert_from_bytes
            import pytesseract
        except Exception as exc:  # pragma: no cover - depends on optional install
            warnings.append(f"OCR dependencies unavailable: {exc}")
            return ""

        try:
            images = convert_from_bytes(file_bytes)
            return "\n".join(pytesseract.image_to_string(image) for image in images)
        except Exception as exc:
            warnings.append(f"Tesseract OCR failed: {exc}")
            return ""


# Backwards-compatible facade for older imports. The new engine uses OCRResult.
class OCRService(PDFTextExtractor):
    def extract_text(self, file_input) -> str:
        if isinstance(file_input, (bytes, bytearray)):
            return self.extract(bytes(file_input), "legacy_doc").text
        return self.extract_from_path(file_input, "legacy_doc").text
