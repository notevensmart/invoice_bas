from __future__ import annotations

from decimal import Decimal

from app.engine.intake import new_batch_id
from app.engine.schemas import BatchResult, InvoiceResult, InvoiceStatus


FileSpec = tuple[str, str | None, bytes]
TextSpec = tuple[str, str]


class BatchProcessor:
    def __init__(self, processor):
        self.processor = processor
        self.repository = processor.repository

    def process_pdfs(self, files: list[FileSpec]) -> BatchResult:
        batch_id = new_batch_id()
        results = [
            self.processor.process_pdf(filename, content_type, file_bytes, batch_id)
            for filename, content_type, file_bytes in files
        ]
        return self._build_and_save(batch_id, results)

    def process_texts(self, texts: list[TextSpec]) -> BatchResult:
        batch_id = new_batch_id()
        results = [
            self.processor.process_text(filename, text, batch_id)
            for filename, text in texts
        ]
        return self._build_and_save(batch_id, results)

    def _build_and_save(self, batch_id: str, results: list[InvoiceResult]) -> BatchResult:
        detected_gst_total = sum(
            (
                result.extraction.gst
                for result in results
                if result.extraction is not None and result.extraction.gst is not None
            ),
            Decimal("0.00"),
        )
        batch = BatchResult(
            batch_id=batch_id,
            uploaded=len(results),
            ready=sum(1 for result in results if result.status == InvoiceStatus.READY),
            needs_review=sum(
                1 for result in results if result.status == InvoiceStatus.NEEDS_REVIEW
            ),
            failed=sum(1 for result in results if result.status == InvoiceStatus.FAILED),
            detected_gst_total=detected_gst_total,
            results=results,
        )
        self.repository.save_batch(batch)
        return batch
