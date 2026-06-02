from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.engine.schemas import (
    AccountCodeSuggestion,
    CorrectionRecord,
    CorrectionRequest,
    CorrectionUpdate,
    InvoiceExtraction,
    InvoiceResult,
)
from app.engine.xero_payload import XeroPayloadBuilder
from app.persistence.repositories import InvoiceRepository


EDITABLE_EXTRACTION_FIELDS = {
    "supplier_name",
    "supplier_abn",
    "invoice_number",
    "invoice_date",
    "due_date",
    "buyer_name",
    "buyer_abn",
    "subtotal",
    "gst",
    "total",
    "currency",
    "line_items",
}


class CorrectionService:
    def __init__(self, processor):
        self.processor = processor
        self.repository: InvoiceRepository = processor.repository
        self.payload_builder = XeroPayloadBuilder()

    def apply(self, document_id: str, request: CorrectionRequest) -> InvoiceResult:
        result = self.repository.load_invoice_result(document_id)
        if result is None:
            raise KeyError(f"Invoice {document_id} was not found.")
        updates = request.normalized_updates()
        if not updates:
            raise ValueError("No correction updates were supplied.")

        working = result.model_copy(deep=True)
        for update in updates:
            record = self._apply_one(working, working.extraction, update)
            working.corrections.append(record)
            self.repository.save_correction(document_id, record)

        if working.extraction is None:
            self.repository.save_invoice_result(working)
            return working

        return self.processor.rebuild_result(working, working.extraction)

    def _apply_one(
        self,
        result: InvoiceResult,
        extraction: InvoiceExtraction | None,
        update: CorrectionUpdate,
    ) -> CorrectionRecord:
        field = update.field
        if field.startswith("account_code"):
            return self._apply_account_code_correction(result, update)

        if extraction is None:
            raise ValueError("Cannot apply invoice-field correction without an extraction.")

        top_level = field.split(".", 1)[0]
        if top_level not in EDITABLE_EXTRACTION_FIELDS:
            raise ValueError(f"Field {field} is not editable.")

        data = extraction.model_dump()
        original_value = self._get_path(data, field)
        self._set_path(data, field, update.value)
        data["field_sources"] = dict(data.get("field_sources") or {})
        data["field_sources"][field] = "user_correction"
        data["original_extracted_values"] = extraction.original_extracted_values
        result.extraction = InvoiceExtraction.model_validate(data)
        return CorrectionRecord(
            field=field,
            original_value=original_value,
            corrected_value=update.value,
        )

    def _apply_account_code_correction(
        self,
        result: InvoiceResult,
        update: CorrectionUpdate,
    ) -> CorrectionRecord:
        previous = result.account_code_suggestion.suggested_account_code if result.account_code_suggestion else None
        result.account_code_suggestion = AccountCodeSuggestion(
            suggested_account_code=str(update.value) if update.value else "UNMAPPED",
            suggested_account_name="User selected account",
            confidence="user",
            reason="User selected account code during review.",
            status="user_selected",
        )
        if result.extraction is not None:
            result.xero_payload = self.payload_builder.build(
                result.extraction,
                result.account_code_suggestion,
                result.status,
            )
        return CorrectionRecord(
            field=update.field,
            original_value=previous,
            corrected_value=update.value,
        )

    def _get_path(self, data: dict[str, Any], path: str) -> Any:
        current: Any = data
        for part in path.split("."):
            if isinstance(current, list):
                current = current[int(part)]
            else:
                current = current.get(part)
        return deepcopy(current)

    def _set_path(self, data: dict[str, Any], path: str, value: Any) -> None:
        parts = path.split(".")
        current: Any = data
        for part in parts[:-1]:
            if isinstance(current, list):
                current = current[int(part)]
            else:
                current = current[part]
        last = parts[-1]
        if isinstance(current, list):
            current[int(last)] = value
        else:
            current[last] = value
