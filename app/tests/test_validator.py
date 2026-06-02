from __future__ import annotations

from app.engine.schemas import InvoiceStatus
from app.engine.validator import InvoiceValidator, validate_abn_checksum


def test_abn_checksum_accepts_known_valid_abn():
    assert validate_abn_checksum("51 824 753 556")


def test_abn_checksum_rejects_invalid_abn():
    assert not validate_abn_checksum("12 345 678 901")


def test_validator_returns_ready_for_clean_invoice(parser, text_loader):
    extraction = parser.parse(text_loader("clean_under_1000"), "doc_test").extraction
    result = InvoiceValidator().validate(extraction)

    assert result.status == InvoiceStatus.READY
    assert result.issues == []


def test_validator_flags_invalid_abn(parser, text_loader):
    extraction = parser.parse(text_loader("invalid_abn"), "doc_test").extraction
    result = InvoiceValidator().validate(extraction)

    assert result.status == InvoiceStatus.NEEDS_REVIEW
    assert {issue.code for issue in result.issues} == {"INVALID_ABN"}


def test_validator_flags_buyer_identity_for_high_value_invoice(parser, text_loader):
    extraction = parser.parse(text_loader("over_1000_missing_buyer"), "doc_test").extraction
    result = InvoiceValidator().validate(extraction)

    assert result.status == InvoiceStatus.NEEDS_REVIEW
    assert {issue.code for issue in result.issues} == {"MISSING_BUYER_FOR_OVER_1000"}


def test_validator_fails_material_total_mismatch(parser, text_loader):
    extraction = parser.parse(text_loader("subtotal_mismatch"), "doc_test").extraction
    result = InvoiceValidator().validate(extraction)

    assert result.status == InvoiceStatus.FAILED
    assert "GST_TOTAL_MISMATCH" in {issue.code for issue in result.issues}
