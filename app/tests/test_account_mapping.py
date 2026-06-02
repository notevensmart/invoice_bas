from __future__ import annotations

from app.engine.account_mapping import AccountCodeMapper


def test_account_mapping_matches_supplier_and_keyword(parser, text_loader):
    extraction = parser.parse(text_loader("officeworks"), "doc_test").extraction
    suggestion = AccountCodeMapper().suggest(extraction)

    assert suggestion.suggested_account_code == "453"
    assert suggestion.confidence == "high"
    assert suggestion.status == "suggested"
    assert "Matched" in suggestion.reason


def test_unmapped_account_code_does_not_block_invoice_readiness(processor, text_loader):
    result = processor.process_text("unmapped_ready.pdf", text_loader("unmapped_ready"))

    assert result.status.value == "ready"
    assert result.account_code_suggestion is not None
    assert result.account_code_suggestion.suggested_account_code == "UNMAPPED"
    assert result.account_code_suggestion.status == "needs_mapping_review"
