# Invoice Automation POC Testing Strategy

## Purpose

The POC must prove that the invoice engine is accurate, trustworthy, and useful enough to reduce bookkeeping work.

The goal is not just to show that an agent can answer questions. The goal is to measure whether the system can correctly extract supplier invoice data, validate Australian bookkeeping requirements, produce Xero-ready draft bill payloads, and clearly flag cases that need human review.

## Testing Principle

The most important risk is a false approval.

A false approval happens when the system marks an invoice as `ready` even though the extraction, validation, or Xero payload is materially wrong.

For the POC:

> A false `needs_review` is acceptable. A false `ready` is dangerous.

The system should be conservative. It should prefer sending uncertain invoices to review rather than confidently approving bad data.

## Test Dataset

Create a representative fixture set of Australian supplier invoices.

Recommended starting size:

- Minimum: 20 invoices.
- Better POC target: 50 invoices.

Each fixture should include:

- Source PDF.
- OCR text output, once generated.
- Expected structured invoice JSON.
- Expected validation status: `ready`, `needs_review`, or `failed`.
- Expected validation issues.
- Expected correction behaviour for review cases.
- Expected account-code suggestion, if applicable.
- Expected Xero draft bill payload shape.

## Fixture Coverage

The fixture set should include:

- Clean tax invoice under AUD 1,000.
- Clean tax invoice over AUD 1,000.
- Small invoice or receipt of AUD 82.50 or less.
- Invoice with missing ABN.
- Invoice with invalid ABN.
- Invoice with GST included but not separately shown.
- Invoice with clear line items.
- Invoice with messy line items requiring fallback single-line handling.
- Scanned PDF invoice.
- Poor OCR invoice.
- Duplicate supplier ABN plus invoice number.
- Invoice missing buyer identity over AUD 1,000.
- Invoice with subtotal/GST/total mismatch.
- Invoice with non-AUD or unclear currency.
- Invoice with supplier name present but supplier ABN missing.
- Invoice that becomes `ready` after a user correction.
- Invoice that remains `needs_review` after an incomplete correction.

## Test Layers

### 1. OCR Tests

Input:

- PDF fixture.

Expected output:

- Non-empty extracted text for readable invoices.
- Clear failure state for unreadable invoices.
- Extraction metadata showing whether text extraction or OCR was used.

Important checks:

- Empty OCR output must not silently continue through the pipeline.
- Scanned PDFs should be distinguishable from text PDFs in metadata.

### 2. Parser Tests

Input:

- Known OCR text.

Expected output:

- Strict structured invoice schema.
- Parser errors when output is malformed.
- No silent fallback to `{}`.

Fields to evaluate:

- `supplier_name`
- `supplier_abn`
- `invoice_number`
- `invoice_date`
- `due_date`
- `buyer_name`
- `buyer_abn`
- `subtotal`
- `gst`
- `total`
- `currency`
- `line_items`

### 3. Validation Tests

Input:

- Structured invoice JSON.

Expected output:

- Deterministic validation status.
- Exact validation issue codes.
- Severity levels.

Validation cases:

- ABN checksum passes.
- ABN checksum fails.
- Missing ABN.
- GST arithmetic passes.
- GST arithmetic fails.
- Invoice over AUD 1,000 without buyer identity.
- Invoice of AUD 82.50 or less with relaxed tax-invoice completeness.
- Duplicate supplier ABN plus invoice number.

### 4. Confidence Status Tests

Input:

- Validation output.

Expected output:

- `ready`
- `needs_review`
- `failed`

Rules:

- `ready` only when ATO-relevant checks pass and a Xero draft bill payload can be generated.
- `needs_review` when extraction mostly worked but warnings or uncertainty remain.
- `failed` when OCR fails, parser fails, supplier identity is missing, or totals are materially inconsistent.

### 5. Account-Code Mapping Tests

Input:

- Supplier name.
- Line item descriptions.
- Local mapping rules.

Expected output:

- Suggested account code.
- Suggested account name.
- Confidence.
- Human-readable reason.
- Mapping status.

Important checks:

- Low-confidence account-code mapping must not block the invoice's main `ready` status.
- Missing mapping should produce `UNMAPPED` or equivalent placeholder plus `needs_mapping_review`.
- The system should never hide that an account code was guessed.

### 6. Xero Payload Tests

Input:

- Validated invoice.
- Account-code suggestion.

Expected output:

- Xero-ready draft purchase bill payload.

Required checks:

- `Type` is `ACCPAY`.
- `Status` is `DRAFT`.
- `Contact.Name` is present.
- `InvoiceNumber` is present.
- `Date` is present.
- At least one line item is present.
- Tax type is present or intentionally deferred.
- Account-code suggestion is included with confidence and reason.

### 7. Review And Correction Tests

Input:

- Invoice marked `needs_review`.
- User correction payload.

Expected output:

- Corrected invoice object.
- Correction record with original and corrected values.
- Field source changed to `user_correction`.
- Validation is re-run.
- Confidence status is recalculated.
- Xero payload is regenerated if the invoice becomes `ready`.

Important checks:

- Corrections must update structured invoice fields, not chat history.
- Original extracted values should remain traceable.
- A valid correction can move an invoice from `needs_review` to `ready`.
- An incomplete or invalid correction should keep the invoice in `needs_review` or `failed`.
- Agent wording must not override validation status after correction.

Example correction case:

```json
{
  "before": {
    "status": "needs_review",
    "supplier_abn": "123 456 789 00",
    "issues": ["INVALID_ABN"]
  },
  "correction": {
    "field": "supplier_abn",
    "value": "12 345 678 901"
  },
  "after": {
    "status": "ready",
    "field_sources": {
      "supplier_abn": "user_correction"
    }
  }
}
```

### 8. Agent Grounding Tests

Input:

- Fixed engine result.

Expected output:

- Clear explanation of status.
- Extracted fields match engine output.
- Validation issues are mentioned.
- Missing fields are not invented.
- `needs_review` invoices are not described as ready.
- Totals, GST, ABN, and invoice number are not changed by wording.
- User corrections are explained from the correction record, not invented.

The agent should be tested as an explanation layer, not as the source of truth.

## Metrics

Track metrics at both field level and workflow level.

### Field Extraction Accuracy

Measure whether each extracted field matches the expected fixture result.

Key fields:

- Supplier name.
- Supplier ABN.
- Invoice number.
- Invoice date.
- Buyer identity.
- Subtotal.
- GST.
- Total.
- Currency.
- Line items.

### Financial Arithmetic Accuracy

Measure whether the system correctly validates:

- Subtotal plus GST equals total.
- GST is approximately one eleventh of GST-inclusive total where applicable.
- Line items add up to subtotal or total.

### Readiness Decision Accuracy

Measure whether the final status matches the expected status:

- `ready`
- `needs_review`
- `failed`

### False-Ready Rate

Measure invoices marked `ready` that should have been `needs_review` or `failed`.

This is the most important trust metric.

Target:

- 0 critical false-ready approvals in the POC fixture set.

### Review Rate

Measure the percentage of invoices marked `needs_review`.

This shows how much human involvement is still required.

Target:

- Less than 30% review rate on clean representative invoices.

### Payload Validity Rate

Measure the percentage of `ready` invoices that produce a valid Xero draft bill payload.

Target:

- 100% for invoices marked `ready`.

### Correction Success Rate

Measure how often review invoices become `ready` after valid user corrections.

This helps prove that the review workflow actually reduces manual bookkeeping effort instead of becoming a dead end.

Track:

- Number of invoices needing correction.
- Number corrected successfully.
- Number still needing review after correction.
- Average number of corrected fields per invoice.

### Agent Grounding Rate

Measure whether the agent response matches the engine facts.

Checks:

- Correct status.
- Correct totals.
- Correct GST.
- Correct validation issues.
- No invented missing fields.

Target:

- 100% factual consistency with engine output on tested fixtures.

## Recommended POC Targets

For a credible POC demo:

- Test at least 20 representative invoices.
- Prefer 50 invoices if available.
- Achieve 90% or higher required-field extraction accuracy on clean invoices.
- Achieve 95% or higher GST/total arithmetic validation accuracy.
- Achieve 100% Xero payload validity for invoices marked `ready`.
- Achieve 0 critical false-ready approvals.
- Keep clean-invoice review rate under 30%.

## Demo Reporting Format

The final demo should be able to report metrics like:

```text
Tested on 50 representative Australian supplier invoices.

- 86% marked ready.
- 14% correctly flagged for review.
- 0 critical false-ready approvals.
- 94% required-field extraction accuracy.
- 98% GST/total arithmetic validation accuracy.
- 100% valid Xero draft payload generation for ready invoices.
```

This framing is stronger than saying the agent gave good answers.

## Test Execution Modes

### Fast Deterministic Tests

Use saved OCR text and mocked or frozen parser outputs.

Purpose:

- Run quickly.
- Catch schema, validation, confidence, mapping, payload, and response regressions.

### Evaluation Tests

Run the real parser against OCR text or source PDFs.

Purpose:

- Measure actual extraction accuracy.
- Track model and prompt quality.
- Generate POC performance metrics.

Evaluation tests may be slower and may require API access.

## Recommended Test Folder Shape

```text
app/
  tests/
    fixtures/
      invoices/
      ocr_text/
      expected/
    test_ocr.py
    test_parser.py
    test_validator.py
    test_confidence.py
    test_account_mapping.py
    test_xero_payload.py
    test_review_correction.py
    test_agent_grounding.py
    test_batch_pipeline.py
```

## Acceptance Bar

The POC is credible when the team can honestly say:

> We tested this on representative Australian supplier invoices. It correctly extracted core invoice fields, validated tax and bookkeeping rules, flagged risky cases for review, generated Xero-ready draft bill payloads, and produced zero critical false approvals.
