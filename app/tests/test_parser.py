from __future__ import annotations

from app.engine.schemas import ParserStatus


def test_parser_extracts_strict_invoice_schema(parser, text_loader):
    result = parser.parse(text_loader("clean_under_1000"), "doc_test")

    assert result.status == ParserStatus.SUCCESS
    assert result.extraction is not None
    assert result.extraction.supplier_name == "Metro Coffee Roasters Pty Ltd"
    assert result.extraction.supplier_abn == "51 824 753 556"
    assert result.extraction.invoice_number == "MCR-1001"
    assert result.extraction.invoice_date == "2026-05-12"
    assert result.extraction.subtotal is not None
    assert str(result.extraction.subtotal) == "300.00"
    assert str(result.extraction.gst) == "30.00"
    assert str(result.extraction.total) == "330.00"
    assert result.extraction.currency == "AUD"
    assert len(result.extraction.line_items) == 1


def test_parser_uses_fallback_single_line_when_items_are_messy(parser, text_loader):
    result = parser.parse(text_loader("messy_fallback"), "doc_test")

    assert result.status == ParserStatus.SUCCESS
    assert result.extraction is not None
    assert result.extraction.line_items_source == "fallback_single_line"
    assert result.extraction.line_items[0].source == "fallback_single_line"


def test_parser_rejects_malformed_json_without_empty_dict_fallback(parser):
    result = parser.parse_json("not json at all", "doc_test")

    assert result.status == ParserStatus.FAILED
    assert result.extraction is None
    assert result.errors


def test_parser_fails_unusable_ocr_text(parser, text_loader):
    result = parser.parse(text_loader("poor_ocr"), "doc_test")

    assert result.status == ParserStatus.FAILED
    assert result.extraction is None
