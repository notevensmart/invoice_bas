from __future__ import annotations

import json

from app.engine.parser import InvoiceParser
from app.engine.schemas import ParserStatus


def _valid_invoice_payload(**overrides):
    payload = {
        "supplier_name": "Metro Coffee Roasters Pty Ltd",
        "supplier_abn": "51 824 753 556",
        "invoice_number": "MCR-LLM-1",
        "invoice_date": "2026-05-12",
        "due_date": "2026-06-12",
        "buyer_name": "Luna Cafe Pty Ltd",
        "buyer_abn": None,
        "subtotal": "300.00",
        "gst": "30.00",
        "total": "330.00",
        "currency": "AUD",
        "line_items": [
            {
                "description": "Coffee beans",
                "quantity": "1",
                "unit_price": "300.00",
                "amount": "300.00",
                "gst_amount": "30.00",
                "tax_treatment": "GST",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_llm_valid_json_validates_into_invoice_extraction(monkeypatch):
    parser = InvoiceParser(use_llm=True)
    monkeypatch.setattr(
        parser,
        "_call_llm",
        lambda prompt: json.dumps(_valid_invoice_payload()),
    )

    result = parser.parse("Tax Invoice\nCoffee beans\nTotal $330.00", "doc_llm")

    assert result.status == ParserStatus.SUCCESS
    assert result.extraction is not None
    assert result.extraction.supplier_name == "Metro Coffee Roasters Pty Ltd"
    assert result.extraction.invoice_number == "MCR-LLM-1"


def test_llm_malformed_json_triggers_retry_and_repair(monkeypatch):
    parser = InvoiceParser(use_llm=True, max_attempts=2)
    calls: list[str] = []
    outputs = iter(["not json", json.dumps(_valid_invoice_payload())])

    def fake_llm(prompt: str) -> str:
        calls.append(prompt)
        return next(outputs)

    monkeypatch.setattr(parser, "_call_llm", fake_llm)

    result = parser.parse("Tax Invoice\nTotal $330.00", "doc_retry")

    assert result.status == ParserStatus.SUCCESS
    assert result.attempts == 2
    assert len(calls) == 2
    assert "previous output" in calls[1].lower()


def test_llm_invalid_schema_output_fails_explicitly(monkeypatch):
    parser = InvoiceParser(use_llm=True, max_attempts=1)
    invalid_schema = _valid_invoice_payload(line_items=["not an object"])
    monkeypatch.setattr(parser, "_call_llm", lambda prompt: json.dumps(invalid_schema))

    result = parser._parse_with_llm("Tax Invoice\nTotal $330.00", "doc_invalid_schema")

    assert result.status == ParserStatus.FAILED
    assert result.extraction is None
    assert result.errors


def test_llm_call_failure_falls_back_to_deterministic_parser(monkeypatch, text_loader):
    parser = InvoiceParser(use_llm=True)

    def fail_call(prompt: str) -> str:
        raise RuntimeError("simulated LLM outage")

    monkeypatch.setattr(parser, "_call_llm", fail_call)

    result = parser.parse(text_loader("clean_under_1000"), "doc_fallback")

    assert result.status == ParserStatus.SUCCESS
    assert result.extraction is not None
    assert result.extraction.invoice_number == "MCR-1001"


def test_field_sources_indicate_llm_origin_when_possible(monkeypatch):
    parser = InvoiceParser(use_llm=True)
    monkeypatch.setattr(
        parser,
        "_call_llm",
        lambda prompt: json.dumps(
            _valid_invoice_payload(
                subtotal=None,
                line_items=[],
            )
        ),
    )

    result = parser.parse("Tax Invoice\nTotal $330.00\nGST $30.00", "doc_sources")

    assert result.status == ParserStatus.SUCCESS
    assert result.extraction is not None
    assert result.extraction.field_sources["supplier_name"] == "llm"
    assert result.extraction.field_sources["subtotal"] == "derived_arithmetic"
    assert result.extraction.line_items_source == "fallback_single_line"
    assert result.extraction.line_items[0].source == "fallback_single_line"
