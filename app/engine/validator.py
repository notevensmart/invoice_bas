from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Callable

from app.engine.confidence import with_decided_status
from app.engine.schemas import (
    InvoiceExtraction,
    InvoiceStatus,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)


ROUNDING_TOLERANCE = Decimal("0.02")
GST_TOLERANCE = Decimal("0.05")
SMALL_INVOICE_THRESHOLD = Decimal("82.50")
BUYER_IDENTITY_THRESHOLD = Decimal("1000.00")


def normalize_abn(abn: str | None) -> str:
    if not abn:
        return ""
    return re.sub(r"\D", "", abn)


def validate_abn_checksum(abn: str | None) -> bool:
    clean = normalize_abn(abn)
    if not re.fullmatch(r"\d{11}", clean):
        return False
    weights = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
    digits = [int(digit) for digit in clean]
    digits[0] -= 1
    return sum(weight * digit for weight, digit in zip(weights, digits)) % 89 == 0


def parse_invoice_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d.%m.%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def issue(
    code: str,
    severity: ValidationSeverity,
    message: str,
    field: str | None = None,
    suggested_action: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        field=field,
        message=message,
        suggested_action=suggested_action,
    )


class InvoiceValidator:
    def validate(
        self,
        extraction: InvoiceExtraction,
        duplicate_checker: Callable[[str, str, str], bool] | None = None,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []

        if not extraction.supplier_name:
            issues.append(
                issue(
                    "MISSING_SUPPLIER_NAME",
                    ValidationSeverity.CRITICAL,
                    "Supplier name was not found.",
                    "supplier_name",
                    "Enter the supplier name shown on the invoice.",
                )
            )

        clean_abn = normalize_abn(extraction.supplier_abn)
        is_small_invoice = (
            extraction.total is not None and extraction.total <= SMALL_INVOICE_THRESHOLD
        )
        if not clean_abn:
            if not is_small_invoice:
                issues.append(
                    issue(
                        "MISSING_SUPPLIER_ABN",
                        ValidationSeverity.ERROR,
                        "Supplier ABN was not found.",
                        "supplier_abn",
                        "Enter the supplier ABN shown on the invoice.",
                    )
                )
        elif not validate_abn_checksum(clean_abn):
            issues.append(
                issue(
                    "INVALID_ABN",
                    ValidationSeverity.ERROR,
                    "Supplier ABN failed checksum validation.",
                    "supplier_abn",
                    "Check the ABN shown on the invoice and update the field.",
                )
            )

        if not extraction.invoice_number:
            issues.append(
                issue(
                    "MISSING_INVOICE_NUMBER",
                    ValidationSeverity.ERROR,
                    "Invoice number was not found.",
                    "invoice_number",
                    "Enter the invoice number shown on the invoice.",
                )
            )

        if not extraction.invoice_date:
            issues.append(
                issue(
                    "MISSING_INVOICE_DATE",
                    ValidationSeverity.ERROR,
                    "Invoice date was not found.",
                    "invoice_date",
                    "Enter the invoice date shown on the invoice.",
                )
            )
        elif parse_invoice_date(extraction.invoice_date) is None:
            issues.append(
                issue(
                    "INVALID_INVOICE_DATE",
                    ValidationSeverity.ERROR,
                    "Invoice date could not be parsed.",
                    "invoice_date",
                    "Use a date such as 2026-05-12 or 12/05/2026.",
                )
            )

        if extraction.total is None:
            issues.append(
                issue(
                    "MISSING_TOTAL",
                    ValidationSeverity.CRITICAL,
                    "Invoice total was not found.",
                    "total",
                    "Enter the GST-inclusive invoice total.",
                )
            )

        if extraction.currency != "AUD":
            issues.append(
                issue(
                    "UNSUPPORTED_CURRENCY",
                    ValidationSeverity.ERROR,
                    f"Currency {extraction.currency} is not supported for this POC.",
                    "currency",
                    "Only AUD supplier invoices are supported in this POC.",
                )
            )

        if extraction.gst is None:
            issues.append(
                issue(
                    "MISSING_GST",
                    ValidationSeverity.ERROR,
                    "GST amount was not found.",
                    "gst",
                    "Enter the GST amount or confirm the invoice is GST-free.",
                )
            )

        self._validate_amounts(extraction, issues)
        self._validate_thresholds(extraction, issues)
        self._validate_line_items(extraction, issues)
        self._validate_duplicate(extraction, duplicate_checker, issues)

        result = with_decided_status(issues)
        return ValidationResult(status=result.status, issues=result.issues)

    def failure_result(self, code: str, message: str, field: str | None = None) -> ValidationResult:
        return ValidationResult(
            status=InvoiceStatus.FAILED,
            issues=[
                issue(
                    code,
                    ValidationSeverity.CRITICAL,
                    message,
                    field,
                    "Re-upload a readable PDF or correct the source document.",
                )
            ],
        )

    def _validate_amounts(
        self,
        extraction: InvoiceExtraction,
        issues: list[ValidationIssue],
    ) -> None:
        if extraction.total is None or extraction.gst is None:
            return

        subtotal = extraction.subtotal
        if subtotal is not None:
            expected_total = subtotal + extraction.gst
            if abs(expected_total - extraction.total) > ROUNDING_TOLERANCE:
                issues.append(
                    issue(
                        "GST_TOTAL_MISMATCH",
                        ValidationSeverity.CRITICAL,
                        "Subtotal plus GST does not match the invoice total.",
                        "total",
                        "Check subtotal, GST, and total against the invoice.",
                    )
                )

        if extraction.gst > Decimal("0.00") and not self._has_mixed_tax_treatment(extraction):
            expected_gst = (extraction.total / Decimal("11")).quantize(Decimal("0.01"))
            if abs(expected_gst - extraction.gst) > GST_TOLERANCE:
                issues.append(
                    issue(
                        "GST_TOTAL_MISMATCH",
                        ValidationSeverity.CRITICAL,
                        "GST is not approximately one eleventh of the GST-inclusive total.",
                        "gst",
                        "Check whether the invoice mixes taxable and GST-free items.",
                    )
                )

    def _has_mixed_tax_treatment(self, extraction: InvoiceExtraction) -> bool:
        treatments = {
            (item.tax_treatment or "").strip().upper().replace("-", "_")
            for item in extraction.line_items
            if item.tax_treatment
        }
        return "GST" in treatments and "GST_FREE" in treatments

    def _validate_thresholds(
        self,
        extraction: InvoiceExtraction,
        issues: list[ValidationIssue],
    ) -> None:
        if extraction.total is None:
            return
        if extraction.total >= BUYER_IDENTITY_THRESHOLD and not (
            extraction.buyer_name or normalize_abn(extraction.buyer_abn)
        ):
            issues.append(
                issue(
                    "MISSING_BUYER_FOR_OVER_1000",
                    ValidationSeverity.WARNING,
                    "Invoice is AUD 1,000 or more but buyer identity was not found.",
                    "buyer_name",
                    "Enter buyer name or buyer ABN for high-value tax invoices.",
                )
            )

        if extraction.total <= SMALL_INVOICE_THRESHOLD:
            return

    def _validate_line_items(
        self,
        extraction: InvoiceExtraction,
        issues: list[ValidationIssue],
    ) -> None:
        if not extraction.line_items:
            return

        amounts = [item.amount for item in extraction.line_items if item.amount is not None]
        if len(amounts) != len(extraction.line_items):
            issues.append(
                issue(
                    "LINE_ITEMS_TOTAL_MISMATCH",
                    ValidationSeverity.CRITICAL,
                    "One or more line items are missing amounts.",
                    "line_items",
                    "Review line item amounts or use a fallback line item.",
                )
            )
            return

        target = extraction.subtotal
        if target is None and extraction.total is not None and extraction.gst is not None:
            target = extraction.total - extraction.gst
        if target is None:
            return

        line_total = sum(amounts, Decimal("0.00"))
        if abs(line_total - target) > ROUNDING_TOLERANCE:
            issues.append(
                issue(
                    "LINE_ITEMS_TOTAL_MISMATCH",
                    ValidationSeverity.CRITICAL,
                    "Line item amounts do not match the invoice subtotal.",
                    "line_items",
                    "Check the extracted line item amounts.",
                )
            )

    def _validate_duplicate(
        self,
        extraction: InvoiceExtraction,
        duplicate_checker: Callable[[str, str, str], bool] | None,
        issues: list[ValidationIssue],
    ) -> None:
        if duplicate_checker is None:
            return
        clean_abn = normalize_abn(extraction.supplier_abn)
        invoice_number = extraction.invoice_number or ""
        if clean_abn and invoice_number and duplicate_checker(
            clean_abn, invoice_number, extraction.document_id
        ):
            issues.append(
                issue(
                    "DUPLICATE_INVOICE",
                    ValidationSeverity.WARNING,
                    "Supplier ABN and invoice number match an invoice already processed.",
                    "invoice_number",
                    "Confirm this is not a duplicate before approving.",
                )
            )
