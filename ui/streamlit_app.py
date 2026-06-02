from __future__ import annotations

import json
import os
from decimal import Decimal
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
import streamlit as st


API_BASE_URL = os.getenv("INVOICE_API_URL", "http://localhost:8000").rstrip("/")

STATUS_ORDER = ("ready", "needs_review", "failed")
STATUS_META = {
    "ready": {"label": "Ready", "class": "ready"},
    "needs_review": {"label": "Needs Review", "class": "review"},
    "failed": {"label": "Failed", "class": "failed"},
}
DISPLAY_FIELDS = [
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
]
FIELD_LABELS = {
    "supplier_name": "Supplier",
    "supplier_abn": "Supplier ABN",
    "invoice_number": "Invoice No.",
    "invoice_date": "Invoice Date",
    "due_date": "Due Date",
    "buyer_name": "Buyer",
    "buyer_abn": "Buyer ABN",
    "subtotal": "Subtotal",
    "gst": "GST",
    "total": "Total",
    "currency": "Currency",
}
MONEY_FIELDS = {"subtotal", "gst", "total", "unit_price", "amount", "gst_amount"}
SOURCE_LABELS = {
    "llm": "AI extraction",
    "regex_rescue": "Rule-based check",
    "derived_arithmetic": "Calculated from totals",
    "fallback_single_line": "Created summary line",
    "user_correction": "Edited by user",
    "parser": "Parser",
}
ISSUE_LABELS = {
    "MISSING_SUPPLIER_NAME": "Supplier name is missing",
    "MISSING_SUPPLIER_ABN": "Supplier ABN is missing",
    "INVALID_ABN": "Supplier ABN needs checking",
    "MISSING_INVOICE_NUMBER": "Invoice number is missing",
    "MISSING_INVOICE_DATE": "Invoice date is missing",
    "INVALID_INVOICE_DATE": "Invoice date needs checking",
    "MISSING_TOTAL": "Invoice total is missing",
    "MISSING_GST": "GST amount needs checking",
    "GST_TOTAL_MISMATCH": "GST and total do not add up",
    "LINE_ITEMS_TOTAL_MISMATCH": "Line items do not match the total",
    "MISSING_BUYER_FOR_OVER_1000": "Buyer details are needed",
    "DUPLICATE_INVOICE": "Possible duplicate invoice",
    "UNSUPPORTED_CURRENCY": "Currency is not supported",
    "OCR_EMPTY_TEXT": "PDF text could not be read",
    "PARSER_INVALID_JSON": "Extraction could not be read",
    "PARSER_SCHEMA_INVALID": "Extraction needs review",
}
PARSER_MODE_LABELS = {
    "llm": "AI extraction active",
    "deterministic": "Rule-based mode",
    "unknown": "Unknown",
}
DEMO_BATCH_FILES = [
    "clean_under_1000.pdf",
    "clean_over_1000.pdf",
    "invalid_abn.pdf",
    "gst_not_shown.pdf",
    "over_1000_missing_buyer.pdf",
]


def inject_styles() -> None:
    st.markdown(
        """
        <style>
          .block-container {
            padding-top: 1.25rem;
            padding-bottom: 2rem;
            max-width: 1440px;
          }
          div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e4e7ec;
            border-radius: 8px;
            padding: 0.65rem 0.8rem;
          }
          div[data-testid="stMetricLabel"] {
            color: #667085;
          }
          .app-heading {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            gap: 1rem;
            margin-bottom: 0.75rem;
          }
          .app-heading h1 {
            font-size: 1.85rem;
            line-height: 1.15;
            margin: 0;
            letter-spacing: 0;
          }
          .app-subtitle {
            color: #667085;
            font-size: 0.95rem;
            margin-top: 0.2rem;
          }
          .status-badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            line-height: 1;
            padding: 0.38rem 0.62rem;
            border: 1px solid transparent;
            white-space: nowrap;
          }
          .status-ready {
            background: #ecfdf3;
            border-color: #abefc6;
            color: #067647;
          }
          .status-review {
            background: #fffaeb;
            border-color: #fedf89;
            color: #b54708;
          }
          .status-failed {
            background: #fef3f2;
            border-color: #fecdca;
            color: #b42318;
          }
          .empty-state {
            border: 1px dashed #d0d5dd;
            border-radius: 8px;
            color: #667085;
            padding: 1rem;
            text-align: center;
            background: #fcfcfd;
          }
          .detail-header {
            border-bottom: 1px solid #e4e7ec;
            padding-bottom: 0.7rem;
            margin-bottom: 0.9rem;
          }
          .detail-title-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
          }
          .detail-title {
            font-size: 1.25rem;
            font-weight: 700;
            color: #101828;
            margin: 0;
          }
          .detail-meta {
            color: #667085;
            font-size: 0.86rem;
            margin-top: 0.18rem;
          }
          .issue-row {
            border-left: 4px solid #f79009;
            background: #fffaeb;
            border-radius: 6px;
            padding: 0.75rem 0.85rem;
            margin-bottom: 0.55rem;
          }
          .issue-row strong {
            color: #93370d;
          }
          .issue-action {
            color: #667085;
            margin-top: 0.25rem;
            font-size: 0.86rem;
          }
          .account-strip {
            border: 1px solid #e4e7ec;
            border-radius: 8px;
            padding: 0.75rem 0.85rem;
            background: #fcfcfd;
          }
          .account-strip strong {
            color: #101828;
          }
          .queue-caption {
            color: #667085;
            font-size: 0.82rem;
            margin: -0.35rem 0 0.55rem 0;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def api_post_files(endpoint: str, files_payload: list[tuple[str, tuple[str, bytes, str]]]) -> dict[str, Any]:
    response = requests.post(api_url(endpoint), files=files_payload, timeout=120)
    response.raise_for_status()
    return response.json()


def api_patch(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.patch(api_url(endpoint), json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def api_post_json(endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.post(api_url(endpoint), json=payload or {}, timeout=60)
    response.raise_for_status()
    return response.json()


def api_url(endpoint: str) -> str:
    return f"{API_BASE_URL}/{endpoint.lstrip('/')}"


def api_get_json(endpoint: str, timeout: int = 5) -> dict[str, Any]:
    response = requests.get(api_url(endpoint), timeout=timeout)
    response.raise_for_status()
    return response.json()


def money_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def money_display(value: Any) -> str:
    text = money_text(value)
    if not text:
        return "-"
    try:
        return f"${Decimal(str(text).replace('$', '').replace(',', '')).quantize(Decimal('0.01'))}"
    except Exception:
        return text


def field_display(field: str, value: Any) -> str:
    if value in (None, ""):
        return "-"
    if field in MONEY_FIELDS:
        return money_display(value)
    return str(value)


def title_text(value: Any) -> str:
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    return text.title() if text else "-"


def source_display(source: Any) -> str:
    return SOURCE_LABELS.get(str(source or ""), title_text(source))


def confidence_display(confidence: Any) -> str:
    text = str(confidence or "").strip().lower()
    if not text:
        return "Needs checking"
    return {
        "high": "High confidence",
        "medium": "Medium confidence",
        "low": "Low confidence",
        "user": "User selected",
    }.get(text, title_text(text))


def parser_mode_display(mode: Any) -> str:
    return PARSER_MODE_LABELS.get(str(mode or "unknown"), title_text(mode))


def issue_title(code: Any) -> str:
    return ISSUE_LABELS.get(str(code or ""), title_text(code))


def account_reason_text(reason: Any) -> str:
    text = str(reason or "").strip()
    if not text:
        return "No matching rule explanation was provided."
    lower = text.lower()
    if lower.startswith("matched supplier pattern:"):
        remainder = text.split(":", 1)[1].strip()
        supplier, _, explanation = remainder.partition(".")
        if explanation.strip():
            return (
                f"Matched this supplier to a bookkeeping rule for {supplier.strip()}. "
                f"{explanation.strip()}"
            )
        return f"Matched this supplier to a bookkeeping rule for {supplier.strip()}."
    if lower.startswith("matched keyword pattern:"):
        remainder = text.split(":", 1)[1].strip()
        keyword, _, explanation = remainder.partition(".")
        if explanation.strip():
            return (
                f"Matched invoice wording to a bookkeeping rule for {keyword.strip()}. "
                f"{explanation.strip()}"
            )
        return f"Matched invoice wording to a bookkeeping rule for {keyword.strip()}."
    return text


def status_label(status: str | None) -> str:
    return STATUS_META.get(status or "", {"label": status or "Unknown"})["label"]


def status_badge_html(status: str | None) -> str:
    meta = STATUS_META.get(status or "", {"label": status or "Unknown", "class": "failed"})
    return (
        f'<span class="status-badge status-{escape(meta["class"])}">'
        f'{escape(meta["label"])}</span>'
    )


def invoice_identity(result: dict[str, Any]) -> tuple[str, str, str]:
    extraction = result.get("extraction") or {}
    invoice_number = extraction.get("invoice_number") or result.get("document_id") or "-"
    supplier = extraction.get("supplier_name") or result.get("filename") or "-"
    filename = result.get("filename") or "-"
    return str(invoice_number), str(supplier), str(filename)


def file_specs_from_uploads(files: list[Any]) -> list[dict[str, Any]]:
    specs = []
    for file in files:
        specs.append(
            {
                "filename": file.name,
                "content": file.read(),
                "content_type": "application/pdf",
            }
        )
    return specs


def files_payload_from_specs(
    specs: list[dict[str, Any]],
    field_name: str,
) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (
            field_name,
            (
                spec["filename"],
                spec["content"],
                spec.get("content_type") or "application/pdf",
            ),
        )
        for spec in specs
    ]


def store_pdf_previews(
    results: list[dict[str, Any]],
    specs: list[dict[str, Any]],
) -> None:
    previews = st.session_state.setdefault("pdf_previews", {})
    for result, spec in zip(results, specs):
        previews[result["document_id"]] = {
            "filename": spec["filename"],
            "content": spec["content"],
        }


def status_groups(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "ready": [result for result in results if result.get("status") == "ready"],
        "needs_review": [result for result in results if result.get("status") == "needs_review"],
        "failed": [result for result in results if result.get("status") == "failed"],
    }


def issue_fields(result: dict[str, Any]) -> set[str]:
    return {
        issue.get("field")
        for issue in result.get("validation", {}).get("issues", [])
        if issue.get("field")
    }


def result_label(result: dict[str, Any]) -> str:
    invoice_number, supplier, _ = invoice_identity(result)
    return f"{invoice_number} | {supplier}"


def update_result_in_state(updated: dict[str, Any]) -> None:
    for key in ("last_invoice",):
        if st.session_state.get(key, {}).get("document_id") == updated["document_id"]:
            st.session_state[key] = updated
    batch = st.session_state.get("last_batch")
    if batch:
        batch["results"] = [
            updated if result["document_id"] == updated["document_id"] else result
            for result in batch.get("results", [])
        ]
        batch["ready"] = sum(1 for result in batch["results"] if result["status"] == "ready")
        batch["needs_review"] = sum(1 for result in batch["results"] if result["status"] == "needs_review")
        batch["failed"] = sum(1 for result in batch["results"] if result["status"] == "failed")
        batch["detected_gst_total"] = str(
            sum(
                Decimal(str((result.get("extraction") or {}).get("gst") or "0"))
                for result in batch["results"]
            )
        )
        st.session_state["last_batch"] = batch


def render_validation_panel(result: dict[str, Any]) -> None:
    issues = result.get("validation", {}).get("issues", [])
    if not issues:
        st.success("No validation issues.")
        return

    for issue in issues:
        if issue.get("field"):
            st.checkbox(
                f"{FIELD_LABELS.get(str(issue.get('field')), title_text(issue.get('field')))} needs attention",
                value=False,
                key=f"issue_check_{result['document_id']}_{issue.get('code')}_{issue.get('field')}",
            )
        st.markdown(
            '<div class="issue-row">'
            f'<strong>{escape(issue_title(issue.get("code")))}</strong>'
            f'<div>{escape(str(issue.get("message") or ""))}</div>'
            + (
                f'<div class="issue-action">{escape(str(issue.get("suggested_action")))}</div>'
                if issue.get("suggested_action")
                else ""
            )
            + '</div>',
            unsafe_allow_html=True,
        )


def render_fields_table(result: dict[str, Any]) -> None:
    extraction = result.get("extraction") or {}
    sources = extraction.get("field_sources") or {}
    fields_needing_review = issue_fields(result)
    rows = []
    for field in DISPLAY_FIELDS:
        rows.append(
            {
                "Field": FIELD_LABELS[field],
                "Value": field_display(field, extraction.get(field)),
                "How Found": source_display(sources.get(field)),
                "Needs Review": "Yes" if field in fields_needing_review else "",
            }
        )
    st.dataframe(rows, hide_index=True, use_container_width=True)
    render_source_summary(extraction)

    line_items = extraction.get("line_items") or []
    if line_items:
        item_rows = []
        for index, item in enumerate(line_items, start=1):
            item_rows.append(
                {
                    "Line": index,
                    "Description": item.get("description") or "-",
                    "Qty": field_display("quantity", item.get("quantity")),
                    "Unit": field_display("unit_price", item.get("unit_price")),
                    "Amount": field_display("amount", item.get("amount")),
                    "GST": field_display("gst_amount", item.get("gst_amount")),
                    "Tax": item.get("tax_treatment") or "-",
                    "How Found": source_display(item.get("source")),
                }
            )
        st.markdown("#### Line Items")
        st.dataframe(item_rows, hide_index=True, use_container_width=True)


def render_source_summary(extraction: dict[str, Any]) -> None:
    sources = extraction.get("field_sources") or {}
    line_items = extraction.get("line_items") or []
    counts: dict[str, int] = {}
    for source in sources.values():
        counts[source] = counts.get(source, 0) + 1
    for item in line_items:
        source = item.get("source")
        if source:
            counts[source] = counts.get(source, 0) + 1
    if not counts:
        return
    labels = {
        "llm": "AI extracted",
        "regex_rescue": "Checked by rules",
        "derived_arithmetic": "Calculated",
        "fallback_single_line": "Summary line created",
        "user_correction": "Edited by user",
        "parser": "Parsed",
    }
    summary = " | ".join(
        f"{labels.get(source, source)}: {count}"
        for source, count in sorted(counts.items())
    )
    st.caption(f"Extraction sources: {summary}")


def render_correction_audit(result: dict[str, Any]) -> None:
    corrections = result.get("corrections") or []
    if not corrections:
        st.caption("No corrections applied yet.")
        return
    rows = [
        {
            "Field": FIELD_LABELS.get(str(correction.get("field")), title_text(correction.get("field"))),
            "Original": correction.get("original_value"),
            "Corrected": correction.get("corrected_value"),
            "Updated By": source_display(correction.get("source")),
        }
        for correction in corrections
    ]
    st.markdown("#### Correction History")
    st.dataframe(rows, hide_index=True, use_container_width=True)


@st.cache_data(show_spinner=False)
def pdf_preview_images(content: bytes, max_pages: int = 2) -> tuple[list[bytes], str | None]:
    try:
        import fitz

        images = []
        with fitz.open(stream=content, filetype="pdf") as document:
            page_count = min(max_pages, document.page_count)
            for page_index in range(page_count):
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
                images.append(pixmap.tobytes("png"))
        if images:
            return images, None
    except Exception:
        pass

    try:
        from pdf2image import convert_from_bytes

        pages = convert_from_bytes(
            content,
            dpi=150,
            first_page=1,
            last_page=max_pages,
        )
        images = []
        for page in pages:
            output = BytesIO()
            page.save(output, format="PNG")
            images.append(output.getvalue())
        if images:
            return images, None
    except Exception as exc:
        return [], f"PDF image preview could not be rendered: {exc}"

    return [], "PDF image preview could not be rendered."


def render_original_pdf(result: dict[str, Any]) -> None:
    preview = st.session_state.get("pdf_previews", {}).get(result["document_id"])
    if not preview:
        st.info("Original PDF preview is available for files uploaded in this browser session.")
        return

    filename = preview["filename"]
    content = preview["content"]
    st.download_button(
        "Download Original PDF",
        data=content,
        file_name=filename,
        mime="application/pdf",
        use_container_width=True,
    )
    images, warning = pdf_preview_images(content)
    if not images:
        st.info("The original PDF can still be downloaded, but the page preview is unavailable.")
        if warning:
            st.caption(warning)
        return

    if len(images) == 1:
        st.caption("Static preview of the uploaded invoice.")
    else:
        st.caption(f"Static preview of the first {len(images)} pages.")
    for index, image in enumerate(images, start=1):
        st.image(
            image,
            caption=f"{filename} - page {index}",
            use_container_width=True,
        )


def render_account_suggestion(result: dict[str, Any]) -> None:
    account = result.get("account_code_suggestion") or {}
    if not account:
        st.caption("No account suggestion is available yet.")
        return
    account_code = str(account.get("suggested_account_code") or "Not mapped")
    account_name = str(account.get("suggested_account_name") or "Needs mapping")
    st.markdown(
        '<div class="account-strip">'
        f'<strong>Suggested Xero account:</strong> {escape(account_name)} '
        f'<span class="detail-meta">({escape(account_code)})</span>'
        f'<br><strong>Confidence:</strong> {escape(confidence_display(account.get("confidence")))}'
        f'<br><span class="detail-meta">{escape(account_reason_text(account.get("reason")))}</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def selected_invoice(batch: dict[str, Any]) -> dict[str, Any] | None:
    results = batch.get("results", [])
    selected_id = st.session_state.get("selected_document_id")
    for result in results:
        if result["document_id"] == selected_id:
            return result
    for status in ("needs_review", "failed", "ready"):
        for result in results:
            if result.get("status") == status:
                st.session_state["selected_document_id"] = result["document_id"]
                return result
    return None


def render_invoice_queue(batch: dict[str, Any]) -> None:
    groups = status_groups(batch.get("results", []))
    for status in ("needs_review", "failed", "ready"):
        st.markdown(f"#### {STATUS_META[status]['label']} ({len(groups[status])})")
        if not groups[status]:
            st.caption("None")
            continue
        for result in groups[status]:
            invoice_number, supplier, _ = invoice_identity(result)
            extraction = result.get("extraction") or {}
            issues = result.get("validation", {}).get("issues", [])
            is_selected = result["document_id"] == st.session_state.get("selected_document_id")
            if st.button(
                f"{invoice_number} | {supplier}",
                key=f"review_select_{result['document_id']}",
                use_container_width=True,
                type="primary" if is_selected else "secondary",
            ):
                st.session_state["selected_document_id"] = result["document_id"]
                st.rerun()
            issue_text = f"{len(issues)} issue{'s' if len(issues) != 1 else ''}"
            st.markdown(
                '<div class="queue-caption">'
                f'{escape(money_display(extraction.get("total")))}'
                f' | {escape(status_label(result.get("status")))}'
                f' | {escape(issue_text)}'
                '</div>',
                unsafe_allow_html=True,
            )


def render_review_workspace(result: dict[str, Any]) -> None:
    extraction = result.get("extraction") or {}
    invoice_number, supplier, filename = invoice_identity(result)
    st.markdown(
        '<div class="detail-header">'
        '<div class="detail-title-row">'
        '<div>'
        f'<p class="detail-title">{escape(invoice_number)} | {escape(supplier)}</p>'
        f'<div class="detail-meta">{escape(filename)}</div>'
        '</div>'
        f'{status_badge_html(result.get("status"))}'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Total", money_display(extraction.get("total")))
    metric_cols[1].metric("GST", money_display(extraction.get("gst")))
    metric_cols[2].metric("Invoice Date", field_display("invoice_date", extraction.get("invoice_date")))
    metric_cols[3].metric("Due Date", field_display("due_date", extraction.get("due_date")))

    evidence_col, edit_col = st.columns([0.53, 0.47], gap="large")
    with evidence_col:
        st.markdown("### Original Invoice")
        render_original_pdf(result)
    with edit_col:
        st.markdown("### Review Fields")
        render_correction_form(result)

    with st.expander("Validation Issues", expanded=bool(result.get("validation", {}).get("issues", []))):
        render_validation_panel(result)
    with st.expander("Extracted Fields And Line Items"):
        render_fields_table(result)
    with st.expander("Account Suggestion", expanded=True):
        render_account_suggestion(result)
    with st.expander("Explanation"):
        st.markdown(result.get("response") or "")


def render_review_page(batch: dict[str, Any]) -> None:
    render_action_status(batch)
    render_batch_metrics(batch)
    queue_col, workspace_col = st.columns([0.28, 0.72], gap="large")
    with queue_col:
        st.markdown("### Work Queue")
        render_invoice_queue(batch)
    with workspace_col:
        result = selected_invoice(batch)
        if result:
            render_review_workspace(result)
        else:
            st.markdown('<div class="empty-state">No invoice selected.</div>', unsafe_allow_html=True)


def ready_results(batch: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        result
        for result in batch.get("results", [])
        if result.get("status") == "ready" and result.get("xero_payload")
    ]


def render_export_page(batch: dict[str, Any]) -> None:
    ready = ready_results(batch)
    render_batch_metrics(batch)
    if not ready:
        st.markdown(
            '<div class="empty-state">No invoices are ready for draft bill export yet.</div>',
            unsafe_allow_html=True,
        )
        return

    payloads = [result["xero_payload"] for result in ready]
    st.success(f"{len(ready)} invoice{'s' if len(ready) != 1 else ''} ready for draft bill export.")
    st.download_button(
        "Download All Draft Bill JSON",
        data=json.dumps(payloads, indent=2),
        file_name="xero_draft_bill_payloads.json",
        mime="application/json",
        use_container_width=True,
    )

    for result in ready:
        invoice_number, supplier, _ = invoice_identity(result)
        extraction = result.get("extraction") or {}
        with st.expander(f"{invoice_number} | {supplier} | {money_display(extraction.get('total'))}"):
            payload_text = json.dumps(result["xero_payload"], indent=2)
            st.download_button(
                "Download This Draft Bill",
                data=payload_text,
                file_name=f"xero_payload_{invoice_number}.json",
                mime="application/json",
                key=f"download_ready_{result['document_id']}",
                use_container_width=True,
            )
            st.code(payload_text, language="json")


def render_batch_metrics(batch: dict[str, Any]) -> None:
    cols = st.columns(5)
    cols[0].metric("Uploaded", batch.get("uploaded", 0))
    cols[1].metric("Ready", batch.get("ready", 0))
    cols[2].metric("Needs Review", batch.get("needs_review", 0))
    cols[3].metric("Failed", batch.get("failed", 0))
    cols[4].metric("Detected GST", money_display(batch.get("detected_gst_total", "0.00")))


def render_action_status(batch: dict[str, Any]) -> None:
    needs_review = int(batch.get("needs_review") or 0)
    failed = int(batch.get("failed") or 0)
    ready = int(batch.get("ready") or 0)
    if needs_review:
        st.warning(f"{needs_review} invoice{'s' if needs_review != 1 else ''} waiting for review.")
    elif failed:
        st.error(f"{failed} invoice{'s' if failed != 1 else ''} failed processing.")
    elif ready:
        st.success(f"{ready} invoice{'s' if ready != 1 else ''} ready.")
    else:
        st.info("No invoices in the queue.")


def prime_queue_selection(batch: dict[str, Any]) -> None:
    groups = status_groups(batch.get("results", []))
    selected_by_status = {}
    for status in STATUS_ORDER:
        if groups[status]:
            selected_by_status[status] = groups[status][0]["document_id"]
    st.session_state["selected_document_ids_by_status"] = selected_by_status
    for status in ("needs_review", "failed", "ready"):
        if selected_by_status.get(status):
            st.session_state["selected_document_id"] = selected_by_status[status]
            break


def api_health_status() -> str:
    try:
        response = requests.get(api_url("/health"), timeout=2)
        return "Connected" if response.ok else "Unavailable"
    except Exception:
        return "Unavailable"


def system_status() -> dict[str, Any]:
    try:
        return api_get_json("/system/status", timeout=3)
    except Exception:
        return {}


def demo_batch_specs() -> list[dict[str, Any]]:
    root = Path(__file__).resolve().parents[1] / "app" / "tests" / "fixtures" / "invoices"
    specs = []
    for filename in DEMO_BATCH_FILES:
        path = root / filename
        if path.exists():
            specs.append(
                {
                    "filename": filename,
                    "content": path.read_bytes(),
                    "content_type": "application/pdf",
                }
            )
    return specs


def render_correction_form(result: dict[str, Any]) -> None:
    extraction = result.get("extraction") or {}
    if not extraction:
        return
    st.markdown("#### Review Edits")
    editable_fields = [
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
    ]
    original_values = {field: money_text(extraction.get(field)) for field in editable_fields}
    updates = []
    with st.form(f"corrections_{result['document_id']}"):
        cols = st.columns(3)
        edited_values: dict[str, str] = {}
        for index, field in enumerate(editable_fields):
            with cols[index % 3]:
                edited_values[field] = st.text_input(
                    FIELD_LABELS.get(field, title_text(field)),
                    value=original_values[field],
                    key=f"edit_{result['document_id']}_{field}",
                )

        line_items = extraction.get("line_items") or []
        if line_items:
            st.markdown("Line Items")
            for index, item in enumerate(line_items):
                key = f"line_items.{index}.description"
                edited_values[key] = st.text_input(
                    f"Line {index + 1} description",
                    value=item.get("description") or "",
                    key=f"edit_{result['document_id']}_{key}",
                )
                original_values[key] = item.get("description") or ""

        account = result.get("account_code_suggestion") or {}
        edited_values["account_code_suggestion.suggested_account_code"] = st.text_input(
            "Xero account code",
            value=account.get("suggested_account_code") or "",
            key=f"edit_{result['document_id']}_account_code",
        )
        original_values["account_code_suggestion.suggested_account_code"] = account.get("suggested_account_code") or ""

        submitted = st.form_submit_button("Apply Corrections")
        if submitted:
            for field, value in edited_values.items():
                if value != original_values.get(field, ""):
                    updates.append({"field": field, "value": value})
            if updates:
                try:
                    updated = api_patch(
                        f"/invoices/{result['document_id']}/corrections",
                        {"updates": updates},
                    )
                    update_result_in_state(updated)
                    st.success("Corrections applied.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Correction failed: {exc}")
            else:
                st.info("No changed fields.")
    render_correction_audit(result)


st.set_page_config(page_title="Invoice Automation POC", layout="wide")
inject_styles()
connection_badge = (
    '<span class="status-badge status-ready">Connected</span>'
    if api_health_status() == "Connected"
    else '<span class="status-badge status-failed">Unavailable</span>'
)
st.markdown(
    (
        '<div class="app-heading">'
        '<div>'
        '<h1>Smart BAS Assistant POC</h1>'
        '<div class="app-subtitle">Upload supplier invoice PDFs, extract GST and invoice details, review uncertain items, and prepare Xero-ready draft bill payloads.</div>'
        '</div>'
        f'{connection_badge}'
        '</div>'
    ),
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### System")
    status_payload = system_status()
    st.text_input("API", value=API_BASE_URL, disabled=True)
    st.text_input("Backend", value=api_health_status(), disabled=True)
    st.text_input(
        "Parser",
        value=parser_mode_display(status_payload.get("parser_mode", "unknown")),
        disabled=True,
    )
    st.markdown("### How It Works")
    st.caption("PDF upload -> OCR/text extraction -> LLM parser -> deterministic validation -> review -> Xero draft payload.")
    st.markdown("### Statuses")
    st.caption("Ready: draftable. Needs Review: human check required. Failed: blocked by OCR, parser, or validation.")
    st.markdown("### Demo")
    if st.button("Load demo batch", use_container_width=True):
        try:
            specs = demo_batch_specs()
            if not specs:
                st.error("Demo PDFs were not found in the repo.")
            else:
                payload = files_payload_from_specs(specs, "files")
                batch = api_post_files("/batches/process", payload)
                st.session_state["last_batch"] = batch
                store_pdf_previews(batch.get("results", []), specs)
                prime_queue_selection(batch)
                st.success("Demo batch processed.")
                st.rerun()
        except Exception as exc:
            st.error(f"Demo batch failed: {exc}")
    if st.button("Reset demo data"):
        try:
            api_post_json("/demo/reset")
            for key in (
                "last_invoice",
                "last_batch",
                "selected_document_id",
                "selected_document_ids_by_status",
                "pdf_previews",
            ):
                st.session_state.pop(key, None)
            st.success("Demo data reset.")
            st.rerun()
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 403:
                st.info("Demo reset is disabled unless the API is running in development mode.")
            else:
                st.error(f"Reset failed: {exc}")
        except Exception as exc:
            st.error(f"Reset failed: {exc}")

upload_tab, review_tab, export_tab = st.tabs(["Upload", "Review", "Export"])

with upload_tab:
    upload_col, summary_col = st.columns([0.42, 0.58], gap="large")
    with upload_col:
        st.markdown("### Upload")
        mode = st.radio("Mode", ["Single PDF", "Batch PDFs"], horizontal=True)
        uploaded_files = st.file_uploader(
            "PDF invoices",
            type=["pdf"],
            accept_multiple_files=mode == "Batch PDFs",
        )
        if st.button("Process", type="primary", use_container_width=True):
            if not uploaded_files:
                st.warning("Upload at least one PDF.")
            else:
                files = uploaded_files if isinstance(uploaded_files, list) else [uploaded_files]
                specs = file_specs_from_uploads(files)
                field_name = "files" if mode == "Batch PDFs" else "file"
                payload = files_payload_from_specs(specs, field_name)
                try:
                    if mode == "Batch PDFs":
                        batch = api_post_files("/batches/process", payload)
                        st.session_state["last_batch"] = batch
                        store_pdf_previews(batch.get("results", []), specs)
                        prime_queue_selection(batch)
                    else:
                        invoice = api_post_files("/invoices/process", payload)
                        st.session_state["last_invoice"] = invoice
                        st.session_state["last_batch"] = {
                            "uploaded": 1,
                            "ready": 1 if invoice["status"] == "ready" else 0,
                            "needs_review": 1 if invoice["status"] == "needs_review" else 0,
                            "failed": 1 if invoice["status"] == "failed" else 0,
                            "detected_gst_total": (invoice.get("extraction") or {}).get("gst") or "0.00",
                            "results": [invoice],
                        }
                        store_pdf_previews([invoice], specs)
                        prime_queue_selection(st.session_state["last_batch"])
                    st.success("Processing complete. Open the Review tab to inspect the work queue.")
                except Exception as exc:
                    st.error(f"Processing failed: {exc}")

    with summary_col:
        st.markdown("### Latest Run")
        latest_batch = st.session_state.get("last_batch")
        if latest_batch:
            render_action_status(latest_batch)
            render_batch_metrics(latest_batch)
        else:
            st.markdown('<div class="empty-state">No invoices processed yet.</div>', unsafe_allow_html=True)

with review_tab:
    batch = st.session_state.get("last_batch")
    if not batch:
        st.info("No invoices processed yet.")
    else:
        render_review_page(batch)

with export_tab:
    batch = st.session_state.get("last_batch")
    if not batch:
        st.info("No invoices processed yet.")
    else:
        render_export_page(batch)
