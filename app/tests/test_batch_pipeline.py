from __future__ import annotations

import pytest

from app.engine.batch import BatchProcessor
from app.engine.parser import InvoiceParser
from app.engine.processor import InvoiceProcessor
from app.persistence.repositories import InMemoryInvoiceRepository


def test_batch_pipeline_counts_statuses(text_loader):
    processor = InvoiceProcessor(
        repository=InMemoryInvoiceRepository(),
        parser=InvoiceParser(use_llm=False),
    )
    batch = BatchProcessor(processor).process_texts(
        [
            ("clean_under_1000.pdf", text_loader("clean_under_1000")),
            ("invalid_abn.pdf", text_loader("invalid_abn")),
            ("subtotal_mismatch.pdf", text_loader("subtotal_mismatch")),
        ]
    )

    assert batch.uploaded == 3
    assert batch.ready == 1
    assert batch.needs_review == 1
    assert batch.failed == 1
    assert str(batch.detected_gst_total) == "82.00"


def test_duplicate_supplier_abn_and_invoice_number_is_reviewed(text_loader):
    processor = InvoiceProcessor(
        repository=InMemoryInvoiceRepository(),
        parser=InvoiceParser(use_llm=False),
    )
    batch = BatchProcessor(processor).process_texts(
        [
            ("duplicate_a.pdf", text_loader("duplicate_a")),
            ("duplicate_b.pdf", text_loader("duplicate_b")),
        ]
    )

    assert batch.results[0].status.value == "ready"
    assert batch.results[1].status.value == "needs_review"
    assert "DUPLICATE_INVOICE" in {issue.code for issue in batch.results[1].validation.issues}


@pytest.mark.parametrize(
    "case_name",
    [
        "clean_under_1000",
        "clean_over_1000",
        "small_receipt",
        "small_receipt_missing_abn",
        "clear_line_items",
        "messy_fallback",
        "officeworks",
        "cleaning",
        "produce",
        "subscription",
        "unmapped_ready",
        "missing_abn",
        "invalid_abn",
        "gst_not_shown",
        "over_1000_missing_buyer",
        "subtotal_mismatch",
        "line_item_mismatch",
        "unsupported_currency",
        "missing_invoice_number",
        "poor_ocr",
    ],
)
def test_fixture_expected_statuses_and_zero_false_ready(
    case_name,
    expected_cases,
    text_loader,
):
    expected = expected_cases[case_name]
    processor = InvoiceProcessor(
        repository=InMemoryInvoiceRepository(),
        parser=InvoiceParser(use_llm=False),
    )
    result = processor.process_text(f"{case_name}.pdf", text_loader(case_name))

    assert result.status.value == expected["status"]
    actual_codes = {issue.code for issue in result.validation.issues}
    assert set(expected["issue_codes"]).issubset(actual_codes)
    if expected["status"] != "ready":
        assert result.status.value != "ready"
    if result.status.value == "ready":
        assert result.xero_payload is not None


def test_small_receipt_missing_abn_can_be_ready_but_normal_invoice_cannot(
    text_loader,
):
    processor = InvoiceProcessor(
        repository=InMemoryInvoiceRepository(),
        parser=InvoiceParser(use_llm=False),
    )

    small = processor.process_text(
        "small_receipt_missing_abn.pdf",
        text_loader("small_receipt_missing_abn"),
    )
    normal = processor.process_text("missing_abn.pdf", text_loader("missing_abn"))

    assert small.status.value == "ready"
    assert small.extraction.supplier_abn is None
    assert small.xero_payload is not None
    assert "MISSING_SUPPLIER_ABN" not in {issue.code for issue in small.validation.issues}
    assert normal.status.value == "needs_review"
    assert "MISSING_SUPPLIER_ABN" in {issue.code for issue in normal.validation.issues}
    assert normal.xero_payload is None
