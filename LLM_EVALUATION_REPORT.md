# LLM Evaluation Report

Generated: 2026-06-02T09:00:55.920738+00:00

Synthetic noisy OCR cases are stored in `app/tests/fixtures/expected/llm_noisy_invoice_cases.json`.

## Before/After Summary

| Metric | Before | After |
| --- | ---: | ---: |
| Status accuracy | 75.0% | 100.0% |
| Line item accuracy | 25.0% | 81.2% |
| False-ready approvals | 0 | 0 |
| Review rate | 12.5% | 12.5% |
| Parser failures | 0 | 0 |

## baseline_legacy_llm

- Timestamp: `2026-06-02T09:00:27.863274+00:00`
- LLM enabled: `True`
- Model: `llama-3.1-8b-instant`
- Prompt version: `legacy`
- Legacy prompt: `True`
- LLM calls attempted: `16`
- Cases: `16`
- Status accuracy: `75.0%`
- Line item accuracy: `25.0%`
- False-ready approvals: `0`
- Review rate: `12.5%`
- Parser failures: `0`

### Field Accuracy

| Field | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| supplier_name | 15 | 16 | 93.8% |
| supplier_abn | 16 | 16 | 100.0% |
| invoice_number | 15 | 16 | 93.8% |
| invoice_date | 15 | 16 | 93.8% |
| due_date | 16 | 16 | 100.0% |
| buyer_name | 16 | 16 | 100.0% |
| buyer_abn | 16 | 16 | 100.0% |
| subtotal | 15 | 16 | 93.8% |
| gst | 15 | 16 | 93.8% |
| total | 16 | 16 | 100.0% |
| currency | 16 | 16 | 100.0% |

### Case Results

| Case | Expected | Actual | Issues | Sources |
| --- | --- | --- | --- | --- |
| unusual_total_labels_gst_inclusive | ready | ready | - | parser:15 |
| supplier_buyer_abns_close | ready | failed | LINE_ITEMS_TOTAL_MISMATCH | parser:15 |
| messy_spacing_table_items | ready | ready | - | parser:15 |
| fixed_width_line_items | ready | ready | - | parser:15 |
| missing_due_date | ready | ready | - | parser:14 |
| missing_buyer_abn_under_1000 | ready | ready | - | parser:14 |
| over_1000_missing_buyer | needs_review | failed | MISSING_BUYER_FOR_OVER_1000, LINE_ITEMS_TOTAL_MISMATCH | parser:14 |
| small_receipt_under_82_50 | ready | failed | LINE_ITEMS_TOTAL_MISMATCH | parser:12 |
| gst_inclusive_wording_no_gst_line | ready | needs_review | MISSING_GST | parser:12 |
| mixed_taxable_gst_free | ready | ready | - | parser:15 |
| ocr_character_noise | ready | ready | - | parser:14 |
| duplicate_reference_a | ready | ready | - | fallback_single_line:2, parser:12 |
| duplicate_reference_b | needs_review | needs_review | DUPLICATE_INVOICE | fallback_single_line:2, parser:12 |
| weird_valid_date_formats | ready | ready | - | fallback_single_line:2, parser:13 |
| extra_bank_payment_text | ready | ready | - | fallback_single_line:2, parser:12 |
| multiple_non_total_amounts | ready | ready | - | fallback_single_line:2, parser:12 |

## after_improvements

- Timestamp: `2026-06-02T09:00:52.194595+00:00`
- LLM enabled: `True`
- Model: `llama-3.1-8b-instant`
- Prompt version: `2026-06-02-noisy-v2`
- Legacy prompt: `False`
- LLM calls attempted: `16`
- Cases: `16`
- Status accuracy: `100.0%`
- Line item accuracy: `81.2%`
- False-ready approvals: `0`
- Review rate: `12.5%`
- Parser failures: `0`

### Field Accuracy

| Field | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| supplier_name | 15 | 16 | 93.8% |
| supplier_abn | 16 | 16 | 100.0% |
| invoice_number | 15 | 16 | 93.8% |
| invoice_date | 15 | 16 | 93.8% |
| due_date | 15 | 16 | 93.8% |
| buyer_name | 15 | 16 | 93.8% |
| buyer_abn | 15 | 16 | 93.8% |
| subtotal | 16 | 16 | 100.0% |
| gst | 16 | 16 | 100.0% |
| total | 16 | 16 | 100.0% |
| currency | 16 | 16 | 100.0% |

### Case Results

| Case | Expected | Actual | Issues | Sources |
| --- | --- | --- | --- | --- |
| unusual_total_labels_gst_inclusive | ready | ready | - | llm:14 |
| supplier_buyer_abns_close | ready | ready | - | llm:14 |
| messy_spacing_table_items | ready | ready | - | regex_rescue:14 |
| fixed_width_line_items | ready | ready | - | regex_rescue:15 |
| missing_due_date | ready | ready | - | fallback_single_line:2, regex_rescue:11 |
| missing_buyer_abn_under_1000 | ready | ready | - | fallback_single_line:2, regex_rescue:11 |
| over_1000_missing_buyer | needs_review | needs_review | MISSING_BUYER_FOR_OVER_1000 | fallback_single_line:2, regex_rescue:10 |
| small_receipt_under_82_50 | ready | ready | - | derived_arithmetic:1, fallback_single_line:2, regex_rescue:8 |
| gst_inclusive_wording_no_gst_line | ready | ready | - | derived_arithmetic:2, fallback_single_line:2, regex_rescue:9 |
| mixed_taxable_gst_free | ready | ready | - | regex_rescue:14 |
| ocr_character_noise | ready | ready | - | derived_arithmetic:1, fallback_single_line:2, regex_rescue:9 |
| duplicate_reference_a | ready | ready | - | fallback_single_line:2, regex_rescue:11 |
| duplicate_reference_b | needs_review | needs_review | DUPLICATE_INVOICE | fallback_single_line:2, regex_rescue:11 |
| weird_valid_date_formats | ready | ready | - | fallback_single_line:2, regex_rescue:12 |
| extra_bank_payment_text | ready | ready | - | fallback_single_line:2, regex_rescue:11 |
| multiple_non_total_amounts | ready | ready | - | fallback_single_line:2, regex_rescue:11 |
