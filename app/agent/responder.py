from __future__ import annotations

from decimal import Decimal

from app.engine.schemas import InvoiceResult


def _money(value: Decimal | None) -> str:
    if value is None:
        return "not found"
    return f"${value:.2f}"


def _value(value: object | None) -> str:
    if value is None or value == "":
        return "not found"
    return str(value)


class InvoiceResponder:
    def render(self, result: InvoiceResult) -> str:
        extraction = result.extraction
        if extraction is None:
            issue_lines = "\n".join(
                f"- {issue.code}: {issue.message}" for issue in result.validation.issues
            )
            return (
                f"I processed {result.filename}.\n\n"
                f"Status: {result.status.value}.\n\n"
                f"Validation issues:\n{issue_lines or '- No structured issues were returned.'}"
            )

        identity = extraction.invoice_number or result.document_id
        lines = [
            f"I processed {identity} from {_value(extraction.supplier_name)}.",
            "",
            f"Status: {result.status.value}.",
            "",
            "Extracted:",
            f"- Supplier: {_value(extraction.supplier_name)}",
            f"- ABN: {_value(extraction.supplier_abn)}",
            f"- Invoice date: {_value(extraction.invoice_date)}",
            f"- Total: {_money(extraction.total)}",
            f"- GST: {_money(extraction.gst)}",
            "",
            "Validation:",
        ]

        if result.validation.issues:
            lines.extend(
                f"- {issue.code}: {issue.message}" for issue in result.validation.issues
            )
        else:
            lines.append("- No validation issues were found.")

        if result.corrections:
            lines.append("")
            lines.append("Corrections:")
            lines.extend(
                f"- {record.field}: {_value(record.original_value)} -> {_value(record.corrected_value)}"
                for record in result.corrections
            )

        lines.append("")
        lines.append("Xero draft bill:")
        if result.xero_payload:
            account = result.account_code_suggestion
            account_text = "UNMAPPED"
            if account:
                account_text = (
                    f"{account.suggested_account_code} - {account.suggested_account_name} "
                    f"({account.confidence}; {account.reason})"
                )
            lines.extend(
                [
                    "- Type: Purchase bill",
                    "- Status: Draft",
                    f"- Account code suggestion: {account_text}",
                ]
            )
        else:
            lines.append("- No Xero draft payload was generated because the invoice is not draftable yet.")

        return "\n".join(lines)
