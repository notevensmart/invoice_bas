from __future__ import annotations

from app.engine.schemas import InvoiceStatus, ValidationIssue, ValidationResult


FAILED_CODES = {
    "OCR_EMPTY_TEXT",
    "OCR_EXTRACTION_FAILED",
    "PARSER_INVALID_JSON",
    "PARSER_SCHEMA_INVALID",
    "MISSING_SUPPLIER_NAME",
    "MISSING_TOTAL",
    "GST_TOTAL_MISMATCH",
    "LINE_ITEMS_TOTAL_MISMATCH",
}


def decide_status(issues: list[ValidationIssue]) -> InvoiceStatus:
    codes = {issue.code for issue in issues}
    if codes & FAILED_CODES:
        return InvoiceStatus.FAILED
    if issues:
        return InvoiceStatus.NEEDS_REVIEW
    return InvoiceStatus.READY


def with_decided_status(issues: list[ValidationIssue]) -> ValidationResult:
    return ValidationResult(status=decide_status(issues), issues=issues)
