from __future__ import annotations

from app.engine.confidence import decide_status
from app.engine.schemas import InvoiceStatus, ValidationIssue, ValidationSeverity


def test_confidence_ready_when_no_issues():
    assert decide_status([]) == InvoiceStatus.READY


def test_confidence_review_for_non_critical_issue():
    issues = [
        ValidationIssue(
            code="MISSING_SUPPLIER_ABN",
            severity=ValidationSeverity.ERROR,
            field="supplier_abn",
            message="Missing ABN.",
        )
    ]
    assert decide_status(issues) == InvoiceStatus.NEEDS_REVIEW


def test_confidence_failed_for_material_arithmetic_issue():
    issues = [
        ValidationIssue(
            code="GST_TOTAL_MISMATCH",
            severity=ValidationSeverity.CRITICAL,
            field="total",
            message="Totals do not reconcile.",
        )
    ]
    assert decide_status(issues) == InvoiceStatus.FAILED
