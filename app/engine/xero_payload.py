from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.engine.schemas import (
    AccountCodeSuggestion,
    InvoiceExtraction,
    InvoiceStatus,
    LineItem,
    XeroDraftBillPayload,
)


class XeroPayloadBuilder:
    def build(
        self,
        extraction: InvoiceExtraction | None,
        account: AccountCodeSuggestion | None,
        status: InvoiceStatus,
    ) -> XeroDraftBillPayload | None:
        if extraction is None or status != InvoiceStatus.READY:
            return None
        if not self._is_draftable(extraction):
            return None

        suggestion = account or AccountCodeSuggestion(
            suggested_account_code="UNMAPPED",
            suggested_account_name="Needs mapping review",
            confidence="low",
            reason="No account mapping suggestion was available.",
            status="needs_mapping_review",
        )

        return XeroDraftBillPayload(
            Contact={"Name": extraction.supplier_name},
            InvoiceNumber=extraction.invoice_number or "",
            Date=extraction.invoice_date or "",
            DueDate=extraction.due_date,
            LineAmountTypes="Exclusive",
            LineItems=[
                self._line_item_payload(item, suggestion)
                for item in self._line_items_for_payload(extraction)
            ],
        )

    def _is_draftable(self, extraction: InvoiceExtraction) -> bool:
        return bool(
            extraction.supplier_name
            and extraction.invoice_number
            and extraction.invoice_date
            and extraction.total is not None
            and extraction.line_items
        )

    def _line_items_for_payload(self, extraction: InvoiceExtraction) -> list[LineItem]:
        if extraction.line_items:
            return extraction.line_items
        amount = extraction.subtotal
        if amount is None and extraction.total is not None and extraction.gst is not None:
            amount = extraction.total - extraction.gst
        return [
            LineItem(
                description=f"Invoice {extraction.invoice_number or extraction.document_id}",
                quantity=Decimal("1.00"),
                unit_price=amount or Decimal("0.00"),
                amount=amount or Decimal("0.00"),
                gst_amount=extraction.gst or Decimal("0.00"),
                tax_treatment="GST" if (extraction.gst or Decimal("0.00")) > 0 else "GST_FREE",
                source="fallback_single_line",
            )
        ]

    def _line_item_payload(
        self,
        item: LineItem,
        suggestion: AccountCodeSuggestion,
    ) -> dict[str, Any]:
        quantity = item.quantity or Decimal("1.00")
        unit_amount = item.unit_price
        if unit_amount is None:
            unit_amount = item.amount or Decimal("0.00")
        line_amount = item.amount or (quantity * unit_amount)
        gst_amount = item.gst_amount or Decimal("0.00")
        return {
            "Description": item.description or "Supplier invoice line",
            "Quantity": self._json_number(quantity),
            "UnitAmount": self._json_number(unit_amount),
            "AccountCode": suggestion.suggested_account_code or "UNMAPPED",
            "TaxType": "INPUT" if gst_amount > Decimal("0.00") else "NONE",
            "LineAmount": self._json_number(line_amount),
            "AccountCodeSuggestion": {
                "suggested_account_code": suggestion.suggested_account_code,
                "suggested_account_name": suggestion.suggested_account_name,
                "confidence": suggestion.confidence,
                "reason": suggestion.reason,
                "status": suggestion.status,
            },
        }

    def _json_number(self, value: Decimal) -> int | float:
        normalized = value.normalize()
        if normalized == normalized.to_integral():
            return int(normalized)
        return float(value)
