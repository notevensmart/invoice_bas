from __future__ import annotations

import json
from decimal import Decimal


def test_xero_payload_is_accpay_draft_for_ready_invoice(processor, text_loader):
    result = processor.process_text("clean_under_1000.pdf", text_loader("clean_under_1000"))

    assert result.status.value == "ready"
    assert result.xero_payload is not None
    payload = result.xero_payload
    assert payload.Type == "ACCPAY"
    assert payload.Status == "DRAFT"
    assert payload.Contact["Name"] == "Metro Coffee Roasters Pty Ltd"
    assert payload.InvoiceNumber == "MCR-1001"
    assert payload.Date == "2026-05-12"
    assert payload.LineAmountTypes == "Exclusive"
    assert payload.LineItems
    assert payload.LineItems[0]["TaxType"] == "INPUT"
    assert payload.LineItems[0]["AccountCodeSuggestion"]["confidence"] == "high"


def test_xero_payload_serializes_line_amounts_as_json_numbers(processor, text_loader):
    result = processor.process_text("clean_under_1000.pdf", text_loader("clean_under_1000"))

    assert isinstance(result.extraction.total, Decimal)
    serialized = json.loads(result.xero_payload.model_dump_json())
    line = serialized["LineItems"][0]
    assert isinstance(line["Quantity"], (int, float))
    assert isinstance(line["UnitAmount"], (int, float))
    assert isinstance(line["LineAmount"], (int, float))
    assert not isinstance(line["Quantity"], str)
    assert not isinstance(line["UnitAmount"], str)
    assert not isinstance(line["LineAmount"], str)


def test_no_final_payload_for_needs_review_invoice(processor, text_loader):
    result = processor.process_text("invalid_abn.pdf", text_loader("invalid_abn"))

    assert result.status.value == "needs_review"
    assert result.xero_payload is None


def test_no_payload_for_failed_invoice(processor, text_loader):
    result = processor.process_text("subtotal_mismatch.pdf", text_loader("subtotal_mismatch"))

    assert result.status.value == "failed"
    assert result.xero_payload is None
