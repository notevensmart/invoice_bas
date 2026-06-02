from __future__ import annotations

from app.engine.schemas import InvoiceExtraction
from app.engine.validator import InvoiceValidator


def test_mixed_taxable_and_gst_free_invoice_uses_explicit_gst_not_total_eleventh_rule():
    extraction = InvoiceExtraction.model_validate(
        {
            "document_id": "doc_mixed",
            "supplier_name": "Green Market Wholesalers Pty Ltd",
            "supplier_abn": "51 824 753 556",
            "invoice_number": "GMW-620",
            "invoice_date": "2026-05-17",
            "buyer_name": "Luna Cafe Pty Ltd",
            "subtotal": "160.00",
            "gst": "10.00",
            "total": "170.00",
            "currency": "AUD",
            "line_items": [
                {
                    "description": "Coffee syrups",
                    "quantity": "1",
                    "unit_price": "100.00",
                    "amount": "100.00",
                    "gst_amount": "10.00",
                    "tax_treatment": "GST",
                },
                {
                    "description": "Fresh apples",
                    "quantity": "1",
                    "unit_price": "60.00",
                    "amount": "60.00",
                    "gst_amount": "0.00",
                    "tax_treatment": "GST_FREE",
                },
            ],
        }
    )

    result = InvoiceValidator().validate(extraction)

    assert result.status.value == "ready"
    assert "GST_TOTAL_MISMATCH" not in {issue.code for issue in result.issues}
