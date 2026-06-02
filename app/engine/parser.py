from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency in fresh environments
    def load_dotenv() -> bool:
        return False

from app.engine.schemas import (
    InvoiceExtraction,
    LineItem,
    ParserResult,
    ParserStatus,
    coerce_decimal,
)


JSON_SCHEMA_HINT = {
    "supplier_name": "string|null",
    "supplier_abn": "string|null",
    "invoice_number": "string|null",
    "invoice_date": "YYYY-MM-DD|string|null",
    "due_date": "YYYY-MM-DD|string|null",
    "buyer_name": "string|null",
    "buyer_abn": "string|null",
    "subtotal": "decimal|null",
    "gst": "decimal|null",
    "total": "decimal|null",
    "currency": "AUD|string",
    "line_items": [
        {
            "description": "string|null",
            "quantity": "decimal|null",
            "unit_price": "decimal|null",
            "amount": "decimal|null",
            "gst_amount": "decimal|null",
            "tax_treatment": "GST|GST_FREE|null",
        }
    ],
}

PROMPT_VERSION = "2026-06-02-noisy-v2"

PLACEHOLDER_KEYS = {
    "",
    "replace_with_your_groq_api_key",
    "your_groq_api_key",
    "placeholder",
    "todo",
}


PLACEHOLDER_KEY_PATTERNS = [
    re.compile(r"your[_\-\s]*groq[_\-\s]*api[_\-\s]*key", re.IGNORECASE),
    re.compile(r"replace.*groq.*key", re.IGNORECASE),
    re.compile(r"^gsk_?x+$", re.IGNORECASE),
    re.compile(r"placeholder|example|dummy|todo", re.IGNORECASE),
]


EXTRACTION_FIELDS = {
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
    "line_items_source",
    "abn_lookup_status",
    "gst_registration_status",
}


DATE_VALUE_PATTERN = (
    r"([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}|"
    r"[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|"
    r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{2,4}|"
    r"[0-9]{1,2}\s+[A-Za-z]{3,9}\s+[0-9]{2,4})"
)


MONEY_VALUE_PATTERN = r"\$?\s*([0-9][0-9,]*\.\d{2})"


def is_real_groq_api_key(api_key: str | None) -> bool:
    cleaned = (api_key or "").strip()
    if cleaned.lower() in PLACEHOLDER_KEYS:
        return False
    return bool(cleaned) and not any(pattern.search(cleaned) for pattern in PLACEHOLDER_KEY_PATTERNS)


def load_project_env() -> None:
    if load_dotenv():
        return
    env_path = ".env"
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_project_env()


class InvoiceParser:
    def __init__(self, use_llm: bool | None = None, max_attempts: int = 3):
        groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
        has_real_key = is_real_groq_api_key(groq_key)
        self.use_llm = has_real_key if use_llm is None else use_llm
        self.max_attempts = max_attempts
        self._llm = None

    def parse(self, text: str, document_id: str) -> ParserResult:
        if not text.strip():
            return ParserResult(
                status=ParserStatus.FAILED,
                attempts=0,
                errors=["Parser received empty text."],
            )

        if self.use_llm:
            llm_result = self._parse_with_llm(text, document_id)
            if llm_result.status != ParserStatus.FAILED:
                return llm_result

        return self._parse_deterministically(text, document_id)

    def parse_json(
        self,
        raw_json: str,
        document_id: str,
        default_source: str = "parser",
        source_text: str | None = None,
    ) -> ParserResult:
        try:
            payload = json.loads(self._extract_json_object(raw_json) or raw_json)
        except json.JSONDecodeError as exc:
            return ParserResult(
                status=ParserStatus.FAILED,
                raw_output=raw_json,
                attempts=1,
                errors=[f"Invalid JSON: {exc}"],
            )
        return self._validate_payload(
            payload,
            document_id,
            raw_json,
            attempts=1,
            default_source=default_source,
            source_text=source_text,
        )

    def _parse_with_llm(self, text: str, document_id: str) -> ParserResult:
        errors: list[str] = []
        raw_output = ""

        for attempt in range(1, self.max_attempts + 1):
            prompt = self._build_prompt(text, raw_output if attempt > 1 else None)
            try:
                raw_output = self._call_llm(prompt)
            except Exception as exc:  # pragma: no cover - optional LLM path
                errors.append(f"LLM call failed on attempt {attempt}: {exc}")
                break

            result = self.parse_json(
                raw_output,
                document_id,
                default_source="llm",
                source_text=text,
            )
            result.attempts = attempt
            if result.status != ParserStatus.FAILED:
                return result
            errors.extend(result.errors)

        return ParserResult(
            status=ParserStatus.FAILED,
            raw_output=raw_output,
            attempts=min(self.max_attempts, max(1, len(errors))),
            errors=errors or ["LLM parser failed."],
        )

    def _call_llm(self, prompt: str) -> str:
        api_key = os.getenv("GROQ_API_KEY")
        if not is_real_groq_api_key(api_key):
            raise RuntimeError("GROQ_API_KEY is not configured.")

        payload = self._call_groq_with_curl(api_key, prompt)
        return str(payload["choices"][0]["message"]["content"])

    def _call_groq_with_curl(self, api_key: str, prompt: str) -> dict[str, Any]:
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            raise RuntimeError("curl is required for Groq calls in this local runtime.")

        request_payload = {
            "model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You extract invoice data into strict JSON only. "
                        "You do not decide approval, readiness, validation, or account codes."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        with tempfile.TemporaryDirectory(prefix="invoice_groq_") as temp_dir:
            temp_path = Path(temp_dir)
            body_path = temp_path / "body.json"
            config_path = temp_path / "curl.conf"
            body_path.write_text(json.dumps(request_payload), encoding="utf-8")
            config_path.write_text(
                "\n".join(
                    [
                        'url = "https://api.groq.com/openai/v1/chat/completions"',
                        'request = "POST"',
                        f'header = "Authorization: Bearer {api_key}"',
                        'header = "Content-Type: application/json"',
                        f'data = "@{body_path.as_posix()}"',
                        "silent",
                        "show-error",
                    ]
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [curl, "--ssl-no-revoke", "--config", str(config_path)],
                capture_output=True,
                text=True,
                timeout=75,
                check=False,
            )

        if completed.returncode != 0:
            message = completed.stderr.strip() or "Groq request failed."
            raise RuntimeError(message)
        try:
            response_payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Groq returned non-JSON response.") from exc
        if "error" in response_payload:
            error = response_payload["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise RuntimeError(f"Groq API error: {message}")
        return response_payload

    def _build_prompt(self, text: str, previous_output: str | None) -> str:
        repair = ""
        if previous_output:
            repair = (
                "The previous output was malformed or failed schema validation. "
                "Repair it and return only valid JSON.\n"
                f"Previous output:\n{previous_output}\n\n"
            )
        return (
            f"Prompt version: {PROMPT_VERSION}\n"
            "Extract an Australian supplier invoice into this strict JSON schema. "
            "Return only one JSON object, no markdown, no commentary. Use null for missing values. "
            "Use decimal strings for money and AUD unless another currency is explicitly printed.\n\n"
            "Extraction rules:\n"
            "- Separate supplier/vendor/from details from buyer/bill-to/customer details. If two ABNs appear close together, choose the ABN nearest supplier/vendor/from as supplier_abn and the ABN nearest buyer/bill-to/customer as buyer_abn.\n"
            "- Extract the invoice number from invoice/ref/id labels, not payment references, bank references, quote numbers, order numbers, or card authorisation numbers.\n"
            "- Normalize dates to YYYY-MM-DD when possible. If a date is present but ambiguous, return the printed date string rather than inventing a date.\n"
            "- For total, choose the final invoice total, amount due, balance due, grand total, final payable, or total payable. Ignore bank limits, statement balances, deposits, late fees, card minimums, quotes, credits, and payment reference amounts.\n"
            "- Extract explicit GST when shown. If the invoice clearly says all prices are GST inclusive and does not mention mixed taxable/GST-free items, calculate GST as total/11 and subtotal as total-GST. If mixed taxable/GST-free wording appears, do not infer GST from total/11; use explicit GST or null.\n"
            "- Extract line items from pipes, tables, or fixed-width rows when amounts are visible. Use amount as the GST-exclusive line amount where the invoice separates subtotal and GST.\n"
            "- Use tax_treatment GST for taxable rows and GST_FREE for GST-free rows. Do not mark a mixed invoice as all GST.\n"
            "- Do not decide whether the invoice is ready; validation is deterministic after extraction.\n\n"
            f"Schema:\n{json.dumps(JSON_SCHEMA_HINT, indent=2)}\n\n"
            f"{repair}Invoice text:\n{text}"
        )

    def _validate_payload(
        self,
        payload: dict[str, Any],
        document_id: str,
        raw_output: str | None,
        attempts: int,
        default_source: str,
        source_text: str | None,
    ) -> ParserResult:
        payload = dict(payload)
        payload["document_id"] = document_id
        payload.setdefault("currency", "AUD")
        payload.pop("field_sources", None)
        payload.pop("original_extracted_values", None)
        try:
            extraction = InvoiceExtraction.model_validate(payload)
        except ValidationError as exc:
            return ParserResult(
                status=ParserStatus.FAILED,
                raw_output=raw_output,
                attempts=attempts,
                errors=[str(exc)],
            )
        extraction = self._complete_extraction(
            extraction,
            default_source=default_source,
            source_text=source_text,
        )
        return ParserResult(
            status=self._parser_status_for(extraction),
            extraction=extraction,
            raw_output=raw_output,
            attempts=attempts,
        )

    def _parse_deterministically(self, text: str, document_id: str) -> ParserResult:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        payload: dict[str, Any] = {
            "document_id": document_id,
            "supplier_name": self._extract_supplier_name(lines, text),
            "supplier_abn": self._extract_abn(text, supplier=True),
            "invoice_number": self._extract_invoice_number(text),
            "invoice_date": self._normalize_date(self._extract_date(text, due=False)),
            "due_date": self._normalize_date(self._extract_date(text, due=True)),
            "buyer_name": self._extract_buyer_name(text),
            "buyer_abn": self._extract_abn(text, supplier=False),
            "subtotal": self._extract_money(text, self._subtotal_patterns()),
            "gst": self._extract_money(text, self._gst_patterns()),
            "total": self._extract_money(text, self._total_patterns()),
            "currency": self._match(text, r"(?im)^Currency\s*[:#]?\s*([A-Z]{3})") or "AUD",
            "line_items": self._parse_line_items(text),
        }

        try:
            extraction = InvoiceExtraction.model_validate(payload)
        except ValidationError as exc:
            return ParserResult(
                status=ParserStatus.FAILED,
                raw_output=json.dumps(payload, default=str),
                attempts=1,
                errors=[str(exc)],
            )

        extraction = self._complete_extraction(
            extraction,
            default_source="regex_rescue",
            source_text=text,
        )
        has_invoice_anchor = any(
            [
                extraction.supplier_abn,
                extraction.invoice_number,
                extraction.total is not None,
            ]
        )
        if not has_invoice_anchor:
            return ParserResult(
                status=ParserStatus.FAILED,
                raw_output=json.dumps(payload, default=str),
                attempts=1,
                errors=["No recognizable invoice fields were extracted."],
            )
        return ParserResult(
            status=self._parser_status_for(extraction),
            extraction=extraction,
            raw_output=json.dumps(payload, default=str),
            attempts=1,
        )

    def _complete_extraction(
        self,
        extraction: InvoiceExtraction,
        default_source: str,
        source_text: str | None = None,
    ) -> InvoiceExtraction:
        if source_text:
            self._apply_regex_rescue(extraction, source_text)

        if extraction.total is None and extraction.subtotal is not None and extraction.gst is not None:
            extraction.total = extraction.subtotal + extraction.gst
            extraction.field_sources.setdefault("total", "derived_arithmetic")

        if extraction.gst is None and extraction.total is not None and self._can_infer_gst(source_text):
            extraction.gst = (extraction.total / Decimal("11")).quantize(Decimal("0.01"))
            extraction.field_sources.setdefault("gst", "derived_arithmetic")

        if extraction.subtotal is None and extraction.total is not None and extraction.gst is not None:
            extraction.subtotal = extraction.total - extraction.gst
            extraction.field_sources.setdefault("subtotal", "derived_arithmetic")

        for item in extraction.line_items:
            if item.source == "parser":
                item.source = default_source

        if extraction.line_items and extraction.line_items_source == "parser":
            extraction.line_items_source = default_source

        if not extraction.line_items and extraction.total is not None:
            amount = extraction.subtotal
            if amount is None and extraction.gst is not None:
                amount = extraction.total - extraction.gst
            if amount is not None:
                fallback_description = self._infer_single_line_description(source_text, extraction)
                extraction.line_items = [
                    LineItem(
                        description=fallback_description
                        or f"Invoice {extraction.invoice_number or extraction.document_id}",
                        quantity=Decimal("1.00"),
                        unit_price=amount,
                        amount=amount,
                        gst_amount=extraction.gst or Decimal("0.00"),
                        tax_treatment="GST" if (extraction.gst or Decimal("0.00")) > 0 else "GST_FREE",
                        source="fallback_single_line",
                    )
                ]
                extraction.line_items_source = "fallback_single_line"

        for field_name in EXTRACTION_FIELDS:
            value = getattr(extraction, field_name)
            if value not in (None, [], {}):
                extraction.field_sources.setdefault(field_name, default_source)
                extraction.original_extracted_values.setdefault(field_name, value)
        return extraction

    def _apply_regex_rescue(self, extraction: InvoiceExtraction, text: str) -> None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        self._set_if_missing(
            extraction,
            "supplier_name",
            self._extract_supplier_name(lines, text),
            "regex_rescue",
        )
        self._set_if_missing(extraction, "supplier_abn", self._extract_abn(text, supplier=True), "regex_rescue")
        self._set_if_missing(extraction, "invoice_number", self._extract_invoice_number(text), "regex_rescue")
        self._set_if_missing(
            extraction,
            "invoice_date",
            self._normalize_date(self._extract_date(text, due=False)),
            "regex_rescue",
        )
        self._set_if_missing(
            extraction,
            "due_date",
            self._normalize_date(self._extract_date(text, due=True)),
            "regex_rescue",
        )
        self._set_if_missing(extraction, "buyer_name", self._extract_buyer_name(text), "regex_rescue")
        self._set_if_missing(extraction, "buyer_abn", self._extract_abn(text, supplier=False), "regex_rescue")
        self._set_if_missing(extraction, "subtotal", self._extract_money(text, self._subtotal_patterns()), "regex_rescue")
        self._set_if_missing(extraction, "gst", self._extract_money(text, self._gst_patterns()), "regex_rescue")
        self._set_if_missing(extraction, "total", self._extract_money(text, self._total_patterns()), "regex_rescue")

        if not extraction.line_items:
            rescued_items = self._parse_line_items(text)
            if rescued_items:
                extraction.line_items = [LineItem.model_validate(item) for item in rescued_items]
                extraction.line_items_source = "regex_rescue"
                extraction.field_sources.setdefault("line_items", "regex_rescue")
                extraction.field_sources.setdefault("line_items_source", "regex_rescue")

    def _set_if_missing(self, extraction: InvoiceExtraction, field_name: str, value: Any, source: str) -> None:
        if value in (None, "", [], {}):
            return
        if getattr(extraction, field_name) in (None, "", [], {}):
            setattr(extraction, field_name, value)
            extraction.field_sources.setdefault(field_name, source)

    def _parser_status_for(self, extraction: InvoiceExtraction) -> ParserStatus:
        critical_values = [
            extraction.supplier_name,
            extraction.supplier_abn,
            extraction.invoice_number,
            extraction.invoice_date,
            extraction.total,
        ]
        if all(value not in (None, "") for value in critical_values):
            return ParserStatus.SUCCESS
        return ParserStatus.PARTIAL

    def _extract_json_object(self, raw: str) -> str | None:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return match.group(0) if match else None

    def _extract_supplier_name(self, lines: list[str], text: str) -> str | None:
        explicit = self._match(text, r"(?im)^(?:Supplier|Supplier Name|From)\s*[:#]?\s*(.+)$")
        if explicit:
            return explicit
        for line in lines[:5]:
            if re.search(r"tax invoice|invoice|receipt|abn|date", line, re.IGNORECASE):
                continue
            return line
        return None

    def _extract_invoice_number(self, text: str) -> str | None:
        patterns = [
            r"(?im)^(?:Tax\s+Invoice\s+)?(?:Invoice|Inv)\s*(?:No\.?|Number|#|ID|Ref|Reference)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-_/]*[0-9][A-Z0-9\-_/]*)",
            r"(?im)^Tax\s+Invoice\s+([A-Z0-9][A-Z0-9\-_/]*[0-9][A-Z0-9\-_/]*)",
            r"(?im)^Sale\s+([A-Z0-9][A-Z0-9\-_/]*[0-9][A-Z0-9\-_/]*)",
        ]
        ignored_prefixes = ("payment", "bank", "quote", "order", "card", "auth", "statement")
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                line = match.group(0).strip().lower()
                if any(line.startswith(prefix) for prefix in ignored_prefixes):
                    continue
                value = match.group(1).strip().replace("O", "0") if re.search(r"\d", match.group(1)) else match.group(1).strip()
                return value or None
        return None

    def _extract_buyer_name(self, text: str) -> str | None:
        value = self._match(
            text,
            r"(?im)^(?:Buyer|Bill\s*To|Billed\s*To|Customer)\b\s*[:#]?\s*(.+?)(?:\s+ABN\s+[0-9 ]{11,})?$",
        ) or self._match(
            text,
            r"(?im)^To\s*[:#]\s*(.+?)(?:\s+ABN\s+[0-9 ]{11,})?$",
        )
        if value:
            value = re.sub(r"\s+ABN\s+[0-9 ]{11,}.*$", "", value, flags=re.IGNORECASE).strip()
        return value or None

    def _extract_abn(self, text: str, supplier: bool) -> str | None:
        if supplier:
            context_patterns = [
                r"(?im)^(?:Supplier|Vendor|From)?\s*(?:ABN|A8N|Australian Business Number)\s*[:#]?\s*([0-9 ]{11,})",
                r"(?im)^(?:Supplier|Vendor|From).{0,80}?\b(?:ABN|A8N)\s*[:#]?\s*([0-9 ]{11,})",
            ]
            blocked_context = re.compile(r"\b(buyer|bill\s*to|billed\s*to|customer|recipient|to)\b", re.IGNORECASE)
        else:
            context_patterns = [
                r"(?im)^(?:Buyer|Bill\s*To|Billed\s*To|Customer|Recipient|To).{0,80}?\b(?:ABN|A8N)\s*[:#]?\s*([0-9 ]{11,})",
                r"(?im)^(?:Buyer|Bill\s*To|Billed\s*To|Customer|Recipient)\s+ABN\s*[:#]?\s*([0-9 ]{11,})",
            ]
            blocked_context = re.compile(r"\b(supplier|vendor|from)\b", re.IGNORECASE)

        for pattern in context_patterns:
            found = self._match(text, pattern)
            if found:
                return found

        all_matches = list(re.finditer(r"(?<!\d)([0-9](?:[0-9 ]{9,15})[0-9])(?!\d)", text))
        if not all_matches:
            return None
        if not supplier and len(all_matches) < 2:
            return None

        for match in all_matches:
            context = text[max(0, match.start() - 80) : min(len(text), match.end() + 80)]
            if supplier and not blocked_context.search(context):
                return match.group(1).strip()
            if not supplier and re.search(r"\b(buyer|bill\s*to|billed\s*to|customer|recipient|to)\b", context, re.IGNORECASE):
                return match.group(1).strip()
        return all_matches[0].group(1).strip() if supplier else None

    def _extract_date(self, text: str, due: bool) -> str | None:
        labels = (
            r"(?:Due|Due\s+Date|Payment\s+requested\s+by|Pay\s+by)"
            if due
            else r"(?:Invoice\s+Date|Date\s+issued|Issued\s+on|Date)"
        )
        return self._match(text, rf"(?im)^{labels}\s*[:#]?\s*{DATE_VALUE_PATTERN}")

    def _normalize_date(self, value: str | None) -> str | None:
        if not value:
            return None
        value = value.strip()
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d/%m/%Y",
            "%d/%m/%y",
            "%d-%m-%Y",
            "%d-%m-%y",
            "%d %b %Y",
            "%d %b %y",
            "%d %B %Y",
            "%d %B %y",
            "%d.%m.%Y",
            "%d.%m.%y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                continue
        return value

    def _subtotal_patterns(self) -> list[str]:
        return [
            rf"(?im)^(?:Sub\s*total|Subtotal|Amount\s+ex\s+GST|Total\s+ex\s+GST|Net\s+Amount|Taxable\s+supplies|Taxable\s+sales)\s*[:#]?\s*(?:AUD\s*)?{MONEY_VALUE_PATTERN}",
        ]

    def _gst_patterns(self) -> list[str]:
        return [
            rf"(?im)^(?:GST|G5T|GST\s+Amount|Total\s+GST|GST\s+collected|GST\s+payable|GST\s+on\s+taxable\s+supply|GST\s+included\s+in\s+total)\s*[:#]?\s*(?:AUD\s*)?{MONEY_VALUE_PATTERN}",
        ]

    def _total_patterns(self) -> list[str]:
        return [
            rf"(?im)^(?:Invoice\s+Total|Total\s+inc\s+GST|Total\s+includes\s+GST|Total\s+due\s+now|Total\s+due|Total\s+payable|Amount\s+Due|Balance\s+Due|Grand\s+Total|Final\s+payable|Total|T0tal\s+due)\s*(?:\([^)]*\))?\s*[:#]?\s*(?:AUD\s*)?{MONEY_VALUE_PATTERN}",
            rf"(?im)(?:All\s+prices\s+are\s+GST\s+inclusive\.\s*)?Total\s+amount\s+payable\s*(?:AUD\s*)?{MONEY_VALUE_PATTERN}",
        ]

    def _extract_money(self, text: str, patterns: list[str]) -> Decimal | None:
        for pattern in patterns:
            value = self._money_match(text, pattern)
            if value is not None:
                return value
        return None

    def _can_infer_gst(self, text: str | None) -> bool:
        if not text:
            return False
        has_inclusive_hint = re.search(r"\bGST\s+inclusive\b|\bincludes\s+GST\b|\bGST\s+included\b", text, re.IGNORECASE)
        has_mixed_hint = re.search(r"GST[-\s]*free|mixed\s+taxable|taxable\s+and\s+GST[-\s]*free", text, re.IGNORECASE)
        return bool(has_inclusive_hint and not has_mixed_hint)

    def _infer_single_line_description(
        self,
        text: str | None,
        extraction: InvoiceExtraction,
    ) -> str | None:
        if not text:
            return None
        excluded = re.compile(
            r"tax invoice|receipt|invoice\s*(?:no|number|#|id|ref)|\babn\b|a8n|date|due|"
            r"buyer|bill\s*to|billed\s*to|customer|supplier|subtotal|sub total|amount\s+ex|"
            r"gst|g5t|total|balance|currency|payment|bank|bsb|eftpos|card|auth|quote|"
            r"deposit|delivery estimate|previous|credit|terms|no due date|all prices|no other tax",
            re.IGNORECASE,
        )
        candidates: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if re.search(r"^(?:Sub\s*total|Subtotal|GST|G5T|Total|T0tal|Amount Due|Balance Due|Grand Total|Final payable|Net Amount)", line, re.IGNORECASE):
                break
            if excluded.search(line):
                continue
            if extraction.supplier_name and line.lower() == extraction.supplier_name.lower():
                continue
            if extraction.buyer_name and line.lower() == extraction.buyer_name.lower():
                continue
            clean = re.sub(r"\$?\s*[0-9][0-9,]*\.\d{2}", "", line).strip(" -|")
            if 3 <= len(clean) <= 90 and re.search(r"[A-Za-z]", clean):
                candidates.append(clean)
        return candidates[-1] if candidates else None

    def _match(self, text: str, pattern: str) -> str | None:
        found = re.search(pattern, text)
        if not found:
            return None
        value = found.group(1).strip()
        return value or None

    def _money_match(self, text: str, pattern: str) -> Decimal | None:
        return coerce_decimal(self._match(text, pattern))

    def _parse_line_items(self, text: str) -> list[dict[str, Any]]:
        match = re.search(
            r"(?ims)^(?:Line Items?|ITEM)\s*:?\s*(.+?)(?:^Sub\s*total|^Subtotal|^GST|^G5T|^Total|^T0tal|^Amount Due|^Currency|^Notes|^Net Amount|\Z)",
            text,
        )
        if not match:
            return []

        items: list[dict[str, Any]] = []
        for raw_line in match.group(1).splitlines():
            line = raw_line.strip()
            if not line or re.search(r"description|qty|quantity|unit", line, re.IGNORECASE):
                continue
            if "|" in line:
                parts = [part.strip() for part in line.split("|")]
                if len(parts) < 4:
                    continue
                description, quantity, unit_price, amount = parts[:4]
                gst_amount = parts[4] if len(parts) > 4 else None
                tax_treatment = parts[5] if len(parts) > 5 else None
            else:
                row = re.match(
                    r"^(?P<description>.+?)\s{2,}(?P<quantity>[0-9]+(?:\.\d+)?)\s+\$?(?P<unit_price>[0-9,]+\.\d{2})\s+\$?(?P<gst_amount>[0-9,]+\.\d{2})\s+\$?(?P<amount>[0-9,]+\.\d{2})$",
                    line,
                )
                if not row:
                    continue
                description = row.group("description").strip()
                quantity = row.group("quantity")
                unit_price = row.group("unit_price")
                amount = row.group("amount")
                gst_amount = row.group("gst_amount")
                tax_treatment = None
            items.append(
                {
                    "description": description,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "amount": amount,
                    "gst_amount": gst_amount,
                    "tax_treatment": self._normalize_tax_treatment(tax_treatment, gst_amount),
                    "source": "regex_rescue",
                }
            )
        return items

    def _normalize_tax_treatment(self, tax_treatment: str | None, gst_amount: str | None) -> str:
        if tax_treatment and re.search(r"free|0", tax_treatment, re.IGNORECASE):
            return "GST_FREE"
        if tax_treatment and re.search(r"gst", tax_treatment, re.IGNORECASE):
            return "GST"
        return "GST" if coerce_decimal(gst_amount) else "GST_FREE"
