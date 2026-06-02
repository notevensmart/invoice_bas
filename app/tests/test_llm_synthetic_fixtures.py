from __future__ import annotations

import json
from pathlib import Path


SYNTHETIC_CASES_PATH = (
    Path(__file__).parent / "fixtures" / "expected" / "llm_noisy_invoice_cases.json"
)


def test_noisy_llm_synthetic_cases_cover_required_invoice_variants():
    cases = json.loads(SYNTHETIC_CASES_PATH.read_text(encoding="utf-8"))
    names = {case["name"] for case in cases}

    required = {
        "unusual_total_labels_gst_inclusive",
        "supplier_buyer_abns_close",
        "messy_spacing_table_items",
        "fixed_width_line_items",
        "missing_due_date",
        "missing_buyer_abn_under_1000",
        "over_1000_missing_buyer",
        "small_receipt_under_82_50",
        "gst_inclusive_wording_no_gst_line",
        "mixed_taxable_gst_free",
        "ocr_character_noise",
        "duplicate_reference_a",
        "duplicate_reference_b",
        "weird_valid_date_formats",
        "extra_bank_payment_text",
        "multiple_non_total_amounts",
    }

    assert required.issubset(names)


def test_noisy_llm_synthetic_cases_have_ground_truth_and_expected_statuses():
    cases = json.loads(SYNTHETIC_CASES_PATH.read_text(encoding="utf-8"))

    for case in cases:
        expected = case["expected"]
        assert case["expected_status"] in {"ready", "needs_review", "failed"}
        assert case["text"].strip()
        for field in (
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
        ):
            assert field in expected
