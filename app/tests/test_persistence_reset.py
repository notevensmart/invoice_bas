from __future__ import annotations

from app.engine.parser import InvoiceParser
from app.engine.processor import InvoiceProcessor
from app.persistence.repositories import InvoiceRepository


def test_sqlite_demo_reset_clears_duplicate_detection_state(tmp_path, text_loader):
    repository = InvoiceRepository(tmp_path / "demo.sqlite3")
    processor = InvoiceProcessor(
        repository=repository,
        parser=InvoiceParser(use_llm=False),
    )

    first = processor.process_text("duplicate_a.pdf", text_loader("duplicate_a"))
    second = processor.process_text("duplicate_b.pdf", text_loader("duplicate_b"))
    assert first.status.value == "ready"
    assert second.status.value == "needs_review"
    assert "DUPLICATE_INVOICE" in {issue.code for issue in second.validation.issues}

    repository.reset_demo_data()
    after_reset = processor.process_text("duplicate_b.pdf", text_loader("duplicate_b"))

    assert after_reset.status.value == "ready"
    assert after_reset.validation.issues == []
