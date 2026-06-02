from __future__ import annotations

from app.engine.corrections import CorrectionService
from app.engine.schemas import CorrectionRequest


def test_valid_correction_updates_structured_data_and_revalidates(processor, text_loader):
    before = processor.process_text("invalid_abn.pdf", text_loader("invalid_abn"))
    assert before.status.value == "needs_review"
    assert before.xero_payload is None

    service = CorrectionService(processor)
    after = service.apply(
        before.document_id,
        CorrectionRequest(field="supplier_abn", value="51 824 753 556"),
    )

    assert after.status.value == "ready"
    assert after.extraction.supplier_abn == "51 824 753 556"
    assert after.extraction.field_sources["supplier_abn"] == "user_correction"
    assert after.extraction.original_extracted_values["supplier_abn"] == "12 345 678 901"
    assert after.corrections[-1].original_value == "12 345 678 901"
    assert after.corrections[-1].corrected_value == "51 824 753 556"
    assert after.xero_payload is not None
    assert "INVALID_ABN" not in {issue.code for issue in after.validation.issues}


def test_incomplete_correction_keeps_invoice_in_review(processor, text_loader):
    before = processor.process_text("missing_abn.pdf", text_loader("missing_abn"))
    service = CorrectionService(processor)

    after = service.apply(
        before.document_id,
        CorrectionRequest(field="supplier_abn", value="12 345 678 901"),
    )

    assert after.status.value == "needs_review"
    assert "INVALID_ABN" in {issue.code for issue in after.validation.issues}
    assert after.xero_payload is None


def test_account_code_correction_regenerates_payload(processor, text_loader):
    before = processor.process_text("unmapped_ready.pdf", text_loader("unmapped_ready"))
    service = CorrectionService(processor)

    after = service.apply(
        before.document_id,
        CorrectionRequest(
            field="account_code_suggestion.suggested_account_code",
            value="429",
        ),
    )

    assert after.status.value == "ready"
    assert after.account_code_suggestion.status == "user_selected"
    assert after.xero_payload.LineItems[0]["AccountCode"] == "429"
