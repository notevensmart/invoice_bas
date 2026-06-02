from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.batch import BatchProcessor
from app.engine.parser import InvoiceParser, JSON_SCHEMA_HINT
from app.engine.processor import InvoiceProcessor
from app.engine.schemas import InvoiceExtraction, InvoiceResult, LineItem
from app.persistence.repositories import InMemoryInvoiceRepository


CASES_PATH = ROOT / "app" / "tests" / "fixtures" / "expected" / "llm_noisy_invoice_cases.json"
RESULTS_PATH = ROOT / "LLM_EVALUATION_RESULTS.json"
REPORT_PATH = ROOT / "LLM_EVALUATION_REPORT.md"
FIELDS = [
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


class LegacyPromptParser(InvoiceParser):
    def _build_prompt(self, text: str, previous_output: str | None) -> str:
        repair = ""
        if previous_output:
            repair = (
                "The previous output was malformed or failed schema validation. "
                "Repair it and return only valid JSON.\n"
                f"Previous output:\n{previous_output}\n\n"
            )
        return (
            "Extract an Australian supplier invoice into this strict JSON schema. "
            "Return only JSON, no markdown, no commentary. Use null for missing values. "
            "Use decimal strings for money.\n"
            f"Schema:\n{json.dumps(JSON_SCHEMA_HINT, indent=2)}\n\n"
            f"{repair}Invoice text:\n{text}"
        )

    def _complete_extraction(
        self,
        extraction: InvoiceExtraction,
        default_source: str = "parser",
        source_text: str | None = None,
    ) -> InvoiceExtraction:
        if extraction.subtotal is None and extraction.total is not None and extraction.gst is not None:
            extraction.subtotal = extraction.total - extraction.gst
        if not extraction.line_items and extraction.total is not None:
            amount = extraction.subtotal
            if amount is None and extraction.gst is not None:
                amount = extraction.total - extraction.gst
            if amount is not None:
                extraction.line_items = [
                    LineItem(
                        description=f"Invoice {extraction.invoice_number or extraction.document_id}",
                        quantity=Decimal("1.00"),
                        unit_price=amount,
                        amount=amount,
                        gst_amount=extraction.gst or Decimal("0.00"),
                        tax_treatment="GST" if (extraction.gst or Decimal("0.00")) > 0 else "GST_FREE",
                        source="fallback_single_line",
                    )
                ]
                extraction.line_items_source = "fallback_single_line"

        for field_name, value in extraction.model_dump().items():
            if field_name in {"field_sources", "original_extracted_values"}:
                continue
            if value not in (None, [], {}):
                extraction.field_sources.setdefault(field_name, "parser")
                extraction.original_extracted_values.setdefault(field_name, value)
        return extraction


def _normalize(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value.quantize(Decimal("0.01")), "f")
    text = str(value).strip()
    if text == "":
        return None
    money_candidate = text.replace("$", "").replace(",", "").replace("AUD", "").strip()
    try:
        return format(Decimal(money_candidate).quantize(Decimal("0.01")), "f")
    except Exception:
        return " ".join(text.lower().split())


def _line_items_match(actual: InvoiceResult, expected_items: list[dict[str, Any]]) -> bool:
    if actual.extraction is None:
        return False
    actual_items = actual.extraction.line_items
    if len(actual_items) != len(expected_items):
        return False
    for actual_item, expected_item in zip(actual_items, expected_items):
        for field in ("description", "quantity", "unit_price", "amount", "gst_amount", "tax_treatment"):
            if _normalize(getattr(actual_item, field)) != _normalize(expected_item.get(field)):
                return False
    return True


def _result_sources(result: InvoiceResult) -> dict[str, int]:
    if result.extraction is None:
        return {}
    counts = Counter(result.extraction.field_sources.values())
    counts.update(item.source for item in result.extraction.line_items if item.source)
    if result.extraction.line_items_source:
        counts[result.extraction.line_items_source] += 1
    return dict(sorted(counts.items()))


def evaluate(label: str, legacy: bool) -> dict[str, Any]:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    parser = LegacyPromptParser() if legacy else InvoiceParser()
    run: dict[str, Any] = {
        "label": label,
        "timestamp": datetime.now(UTC).isoformat(),
        "llm_enabled": parser.use_llm,
        "model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant") if parser.use_llm else None,
        "prompt_version": "legacy" if legacy else getattr(__import__("app.engine.parser", fromlist=["PROMPT_VERSION"]), "PROMPT_VERSION", "unknown"),
        "cases": len(cases),
        "field_accuracy": {},
        "status_accuracy": None,
        "line_items_accuracy": None,
        "false_ready": 0,
        "review_rate": None,
        "parser_failures": 0,
        "llm_calls": 0,
        "legacy_prompt": legacy,
        "case_results": [],
    }

    if not parser.use_llm:
        run["skipped_reason"] = "GROQ_API_KEY was not available or was placeholder-like."
        return run

    original_call_llm = parser._call_llm

    def counted_call_llm(prompt: str) -> str:
        run["llm_calls"] += 1
        return original_call_llm(prompt)

    parser._call_llm = counted_call_llm  # type: ignore[method-assign]

    processor = InvoiceProcessor(
        repository=InMemoryInvoiceRepository(),
        parser=parser,
    )
    batch = BatchProcessor(processor).process_texts(
        [(f"{case['name']}.pdf", case["text"]) for case in cases]
    )

    field_totals = defaultdict(int)
    field_correct = defaultdict(int)
    line_item_correct = 0
    status_correct = 0
    review_count = 0

    for case, result in zip(cases, batch.results):
        expected = case["expected"]
        expected_status = case["expected_status"]
        actual_status = result.status.value
        status_correct += int(actual_status == expected_status)
        review_count += int(actual_status == "needs_review")
        run["parser_failures"] += int(result.extraction is None)
        run["false_ready"] += int(actual_status == "ready" and expected_status != "ready")

        field_matches: dict[str, bool] = {}
        for field in FIELDS:
            field_totals[field] += 1
            actual_value = getattr(result.extraction, field) if result.extraction is not None else None
            matched = _normalize(actual_value) == _normalize(expected.get(field))
            field_correct[field] += int(matched)
            field_matches[field] = matched

        expected_items = expected.get("line_items") or []
        items_match = _line_items_match(result, expected_items)
        line_item_correct += int(items_match)
        issues = [issue.code for issue in result.validation.issues]
        run["case_results"].append(
            {
                "name": case["name"],
                "expected_status": expected_status,
                "actual_status": actual_status,
                "field_matches": field_matches,
                "line_items_match": items_match,
                "issues": issues,
                "sources": _result_sources(result),
            }
        )

    run["field_accuracy"] = {
        field: {
            "correct": field_correct[field],
            "total": field_totals[field],
            "accuracy": round(field_correct[field] / field_totals[field], 4),
        }
        for field in FIELDS
    }
    run["status_accuracy"] = round(status_correct / len(cases), 4)
    run["line_items_accuracy"] = round(line_item_correct / len(cases), 4)
    run["review_rate"] = round(review_count / len(cases), 4)
    return run


def load_runs() -> list[dict[str, Any]]:
    if not RESULTS_PATH.exists():
        return []
    return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))


def save_runs(runs: list[dict[str, Any]]) -> None:
    RESULTS_PATH.write_text(json.dumps(runs, indent=2), encoding="utf-8")


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def write_report(runs: list[dict[str, Any]]) -> None:
    lines: list[str] = [
        "# LLM Evaluation Report",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "Synthetic noisy OCR cases are stored in `app/tests/fixtures/expected/llm_noisy_invoice_cases.json`.",
        "",
    ]
    if len(runs) >= 2:
        before = runs[-2]
        after = runs[-1]
        lines.extend(
            [
                "## Before/After Summary",
                "",
                "| Metric | Before | After |",
                "| --- | ---: | ---: |",
                f"| Status accuracy | {_pct(before.get('status_accuracy'))} | {_pct(after.get('status_accuracy'))} |",
                f"| Line item accuracy | {_pct(before.get('line_items_accuracy'))} | {_pct(after.get('line_items_accuracy'))} |",
                f"| False-ready approvals | {before.get('false_ready', 'n/a')} | {after.get('false_ready', 'n/a')} |",
                f"| Review rate | {_pct(before.get('review_rate'))} | {_pct(after.get('review_rate'))} |",
                f"| Parser failures | {before.get('parser_failures', 'n/a')} | {after.get('parser_failures', 'n/a')} |",
                "",
            ]
        )

    for run in runs:
        lines.extend(
            [
                f"## {run['label']}",
                "",
                f"- Timestamp: `{run['timestamp']}`",
                f"- LLM enabled: `{run['llm_enabled']}`",
                f"- Model: `{run.get('model')}`",
                f"- Prompt version: `{run.get('prompt_version')}`",
                f"- Legacy prompt: `{run.get('legacy_prompt')}`",
                f"- LLM calls attempted: `{run.get('llm_calls')}`",
                f"- Cases: `{run['cases']}`",
            ]
        )
        if run.get("skipped_reason"):
            lines.extend(["", f"Skipped: {run['skipped_reason']}", ""])
            continue
        lines.extend(
            [
                f"- Status accuracy: `{_pct(run.get('status_accuracy'))}`",
                f"- Line item accuracy: `{_pct(run.get('line_items_accuracy'))}`",
                f"- False-ready approvals: `{run['false_ready']}`",
                f"- Review rate: `{_pct(run.get('review_rate'))}`",
                f"- Parser failures: `{run['parser_failures']}`",
                "",
                "### Field Accuracy",
                "",
                "| Field | Correct | Total | Accuracy |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for field, metric in run["field_accuracy"].items():
            lines.append(
                f"| {field} | {metric['correct']} | {metric['total']} | {_pct(metric['accuracy'])} |"
            )
        lines.extend(["", "### Case Results", "", "| Case | Expected | Actual | Issues | Sources |", "| --- | --- | --- | --- | --- |"])
        for item in run["case_results"]:
            issues = ", ".join(item["issues"]) or "-"
            sources = ", ".join(f"{key}:{value}" for key, value in item["sources"].items()) or "-"
            lines.append(
                f"| {item['name']} | {item['expected_status']} | {item['actual_status']} | {issues} | {sources} |"
            )
        lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    arg_parser = argparse.ArgumentParser(description="Evaluate the real LLM parser on noisy synthetic invoices.")
    arg_parser.add_argument("--label", required=True, help="Run label, e.g. baseline or after_improvements.")
    arg_parser.add_argument("--reset", action="store_true", help="Discard previous saved evaluation runs.")
    arg_parser.add_argument("--legacy", action="store_true", help="Use the legacy prompt/completion behavior for a before baseline.")
    args = arg_parser.parse_args()

    runs = [] if args.reset else load_runs()
    run = evaluate(args.label, args.legacy)
    runs.append(run)
    save_runs(runs)
    write_report(runs)
    print(json.dumps({key: run.get(key) for key in ("label", "llm_enabled", "status_accuracy", "line_items_accuracy", "false_ready", "review_rate", "parser_failures", "skipped_reason")}, indent=2))
    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
