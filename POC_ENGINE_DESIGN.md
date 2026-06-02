# Invoice Automation POC Engine Design

## Purpose

This project is a proof of concept for an Australian small-business invoice automation tool.

The POC should prove that the system can take messy supplier invoices, extract trustworthy accounting data, validate the result, and produce an output that could later be pushed into Xero as draft bills.

The product is not intended to replace Xero. It should sit before Xero as an automation and review layer that reduces manual bookkeeping work.

## POC Goal

The core proof should be:

> Drop a batch of supplier invoices into the system. The engine extracts accounting-ready data, flags uncertain or invalid invoices for review, lets the user correct missing or malformed fields through editable inputs, re-validates the corrected data, and prepares clean Xero-ready draft bill payloads.

Success is not measured by whether the chatbot sounds friendly. Success is measured by whether the extraction engine produces correct, explainable, reviewable results.

## POC Non-Goals

The POC does not need:

- Full production authentication.
- Multi-tenant user management.
- Live Xero posting.
- Live ABR/GST registration lookup.
- Long-term document retention.
- Full BAS lodgement support.
- A polished SaaS dashboard.
- Fully automated zero-review bookkeeping.
- Email, Gmail, Dropbox, or Xero document ingestion.
- Image-file upload support outside PDF documents.

These matter later, but they are not required to prove the engine.

## Resolved POC Decisions

These decisions define the first working proof of concept.

- The POC proves supplier invoice extraction, validation, confidence status, and Xero-ready draft bill payload generation.
- The system processes supplier bills / purchase invoices only. These map to Xero `ACCPAY` draft bills.
- Upload is manual only.
- Supported file type is PDF only. PDFs may be text PDFs or scanned PDFs that require OCR.
- Both single invoice upload and batch upload are supported.
- Batch processing optimises for per-invoice correctness first, then aggregate summary.
- Each invoice receives one of three statuses: `ready`, `needs_review`, or `failed`.
- `ready` requires a two-gate standard: ATO-valid enough for the relevant invoice size and Xero-draftable.
- Invoices of AUD 82.50 or less can use relaxed tax-invoice completeness checks, but must still have enough bookkeeping evidence and Xero payload data.
- Invoices of AUD 1,000 or more require buyer identity or buyer ABN for `ready`.
- Supplier ABN must be present and pass checksum validation for `ready`.
- Live ABR lookup is deferred. The schema should leave room for future `abn_lookup_status` and `gst_registration_status`.
- GST arithmetic must pass deterministically for `ready`.
- Real line items should be extracted when possible.
- If line items cannot be reliably extracted, a conservative fallback single line item is allowed.
- Fallback single-line invoices can still be `ready` if required fields and financial validation pass.
- Account-code suggestions come from a small local rule file using supplier and keyword patterns.
- Account-code suggestions include confidence and reason.
- Account-code uncertainty does not block the invoice's main readiness status.
- Missing, malformed, or uncertain fields are corrected through editable fields, not free-form chat.
- User corrections update the invoice object, trigger re-validation, and are tracked separately from extracted values.
- The parser uses LLM extraction with strict schema validation.
- The agent response is template-first, with optional light LLM wording that cannot change facts, statuses, or validation issues.
- Batch results show the action queue first: `ready`, `needs_review`, and `failed`.
- The final demo should show a batch of supplier PDFs where most are ready and a few are correctly flagged for review.

## Implementation Stack Summary

The detailed implementation contract is defined in `IMPLEMENTATION_CONTRACT.md`.

Recommended POC stack:

- Backend: FastAPI.
- Schemas and validation: Pydantic v2.
- Engine: plain Python service modules, not LangGraph.
- Persistence: SQLite for the POC.
- OCR: PDF text extraction first, Tesseract fallback for scanned PDFs.
- Parser: LLM extraction with strict Pydantic schema validation.
- Agent: template-first response layer with optional light LLM wording.
- Frontend: Streamlit for the POC.
- Testing: pytest with golden fixtures.

Implementation principle:

> The engine should be typed, deterministic, and testable. The agent should explain results, not control accounting logic.

## Core User Workflow

1. A small business owner uploads one or more supplier invoices.
2. The system extracts text from each invoice.
3. The parser converts the text into structured invoice data.
4. The validator checks Australian invoice and GST basics.
5. The system assigns a confidence status.
6. The agent explains the result in plain English.
7. Any low-confidence invoice is marked as requiring human review.
8. The user fixes missing or malformed fields through editable review fields.
9. The system re-validates the corrected invoice.
10. The system returns a Xero-ready draft bill payload once the invoice is ready.

## Engine Architecture

```text
Upload
  -> Document Intake
  -> OCR / Text Extraction
  -> Structured Invoice Parser
  -> Validation Engine
  -> Confidence Scoring
  -> Xero Payload Builder
  -> Review / Correction
  -> Agent Explanation
  -> Review / Accept Output
```

The agent should not be the engine. The agent should explain what the engine found, what it is unsure about, and what the user needs to review.

## Engine Components

### 1. Document Intake

Responsible for accepting manual PDF uploads.

For the POC, intake can be request-based and temporary. It should still assign each uploaded file a document ID so all downstream results can be traced back to the source document.

Supported input:

- Text-based PDF invoices.
- Scanned PDF invoices that require OCR.

Unsupported in the POC:

- PNG/JPG/JPEG uploads.
- Email body extraction.
- Gmail, Dropbox, Xero, or supplier-portal ingestion.

Expected output:

```json
{
  "document_id": "doc_123",
  "filename": "supplier-invoice.pdf",
  "content_type": "application/pdf"
}
```

### 2. OCR / Text Extraction

Responsible for extracting raw text from PDFs.

The OCR layer should return both extracted text and extraction metadata. Empty text should be treated as a failed extraction, not silently accepted.

Expected output:

```json
{
  "document_id": "doc_123",
  "text": "Tax Invoice...",
  "method": "pdf_text_or_ocr",
  "status": "success",
  "warnings": []
}
```

### 3. Structured Invoice Parser

Responsible for converting raw text into structured invoice fields.

Minimum fields for the POC:

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

Line item fields:

- `description`
- `quantity`
- `unit_price`
- `amount`
- `gst_amount`
- `tax_treatment`

Expected output:

```json
{
  "supplier_name": "Example Supplies Pty Ltd",
  "supplier_abn": "12345678901",
  "invoice_number": "INV-1007",
  "invoice_date": "2026-05-12",
  "due_date": "2026-06-12",
  "buyer_name": "Luna Cafe Pty Ltd",
  "buyer_abn": null,
  "subtotal": 100.00,
  "gst": 10.00,
  "total": 110.00,
  "currency": "AUD",
  "line_items": [
    {
      "description": "Coffee beans",
      "quantity": 1,
      "unit_price": 100.00,
      "amount": 100.00,
      "gst_amount": 10.00,
      "tax_treatment": "GST"
    }
  ]
}
```

### 4. Validation Engine

Responsible for checking whether the extracted invoice looks reliable enough for bookkeeping.

POC validation checks are based on Australian tax-invoice requirements and what Xero needs to create a useful draft purchase bill.

Base checks:

- Required fields are present.
- ABN has a valid checksum.
- Invoice date is parseable.
- Total equals subtotal plus GST within rounding tolerance.
- GST is approximately one eleventh of the GST-inclusive total when applicable.
- Invoice number is present.
- Buyer identity is present for invoices over AUD 1,000.
- Line items add up to the subtotal or total.
- Currency is AUD or explicitly detected.
- Duplicate supplier ABN plus invoice number is flagged.

Amount-specific checks:

- For invoices of AUD 82.50 or less, formal tax-invoice completeness checks are relaxed, but the system still requires enough evidence to create a draft bill.
- For invoices over AUD 82.50, core tax-invoice fields are required.
- For invoices of AUD 1,000 or more, buyer identity or buyer ABN is required for `ready`.

Validation output should contain specific issues, not just a pass/fail boolean.

```json
{
  "status": "needs_review",
  "issues": [
    {
      "code": "MISSING_BUYER_FOR_OVER_1000",
      "severity": "warning",
      "message": "Invoice is over AUD 1,000 but buyer identity was not found."
    }
  ]
}
```

### 5. Confidence Scoring

Responsible for deciding whether the invoice is safe to prepare for Xero or needs human review.

Recommended POC statuses:

- `ready`
- `needs_review`
- `failed`

Example rules:

- `ready`: ATO-relevant invoice checks pass, Xero draft bill payload can be generated, GST arithmetic passes, and no high-severity validation issues exist.
- `needs_review`: extraction mostly worked but one or more warnings exist.
- `failed`: OCR failed, parser returned invalid JSON, total/GST arithmetic is badly inconsistent, or supplier identity is missing.

Account-code confidence should be separate from invoice readiness. An invoice can be `ready` while its suggested account code is marked as needing mapping review.

### 6. Xero Payload Builder

Responsible for producing a Xero-ready draft bill payload.

For the POC, this does not need to call the Xero API. It only needs to generate a payload shape that can later be sent to Xero.

Expected output:

```json
{
  "Type": "ACCPAY",
  "Contact": {
    "Name": "Example Supplies Pty Ltd"
  },
  "InvoiceNumber": "INV-1007",
  "Date": "2026-05-12",
  "DueDate": "2026-06-12",
  "LineAmountTypes": "Exclusive",
  "LineItems": [
    {
      "Description": "Coffee beans",
      "Quantity": 1,
      "UnitAmount": 100.00,
      "AccountCode": "453",
      "TaxType": "INPUT",
      "LineAmount": 100.00,
      "AccountCodeSuggestion": {
        "confidence": "high",
        "reason": "Description contains 'coffee beans', matched local purchases rule."
      }
    }
  ],
  "Status": "DRAFT"
}
```

Important: account codes should be suggestions in the POC, not hidden decisions. Suggestions should come from a small local mapping file and include confidence plus a human-readable reason.

If no reliable rule matches, use `UNMAPPED` and set `account_code_status` to `needs_mapping_review`.

### 7. Account-Code Mapping

The POC should use a small configurable local mapping file.

The mapping should support supplier and keyword patterns.

Example:

```json
[
  {
    "match": {
      "supplier_contains": ["officeworks"],
      "description_contains": ["stationery", "paper", "printer"]
    },
    "suggested_account_code": "453",
    "suggested_account_name": "Office Expenses",
    "confidence": "high",
    "reason": "Officeworks or office-supply terms usually map to office expenses."
  }
]
```

Mapping output:

```json
{
  "suggested_account_code": "453",
  "suggested_account_name": "Office Expenses",
  "confidence": "high",
  "reason": "Matched supplier pattern: officeworks",
  "status": "suggested"
}
```

Low-confidence or missing mappings should not change the invoice's main `ready` status. They should appear as mapping review work.

### 8. Review And Correction Workflow

The POC should support structured human correction for missing, malformed, or uncertain fields.

The main workflow should not rely on chat for corrections. Chat can explain why a field needs attention, but the correction itself should happen through editable fields.

Examples of editable fields:

- Supplier name.
- Supplier ABN.
- Invoice number.
- Invoice date.
- Due date.
- Buyer name.
- Buyer ABN.
- Subtotal.
- GST.
- Total.
- Currency.
- Line item description.
- Fallback line item description.
- Account-code suggestion.

Review flow:

1. Invoice is marked `needs_review`.
2. UI highlights the exact validation issue.
3. User edits the relevant field.
4. The invoice object records the correction.
5. The system re-runs validation and confidence scoring.
6. If checks pass, the invoice can move to `ready`.
7. The Xero draft bill payload is regenerated from the corrected invoice.

Correction records should preserve both extracted and corrected values.

Example correction record:

```json
{
  "field": "supplier_abn",
  "original_value": "123 456 789 00",
  "corrected_value": "12 345 678 901",
  "source": "user_correction"
}
```

Example review issue:

```json
{
  "code": "INVALID_ABN",
  "severity": "error",
  "field": "supplier_abn",
  "message": "Supplier ABN failed checksum validation.",
  "suggested_action": "Check the ABN shown on the invoice and update the field."
}
```

The corrected invoice should distinguish extracted data from user-approved data:

```json
{
  "supplier_abn": "12 345 678 901",
  "field_sources": {
    "supplier_abn": "user_correction",
    "supplier_name": "parser",
    "total": "parser"
  },
  "corrections": [
    {
      "field": "supplier_abn",
      "original_value": "123 456 789 00",
      "corrected_value": "12 345 678 901",
      "source": "user_correction"
    }
  ]
}
```

This keeps the human-in-the-loop workflow structured, auditable, and easier to test.

### 9. Agent Explanation Layer

The agent should communicate the engine result clearly and honestly.

The agent should say:

- What invoice was processed.
- What fields were extracted.
- Whether it is ready or needs review.
- Which fields are uncertain or missing.
- What draft Xero bill would be prepared.

The agent should not:

- Invent missing fields.
- Claim an invoice is valid when validation warnings exist.
- Hide low confidence behind friendly language.
- Present BAS estimates as the main output.
- Capture corrections as free-form chat messages instead of structured field updates.

Example response:

```text
I processed INV-1007 from Example Supplies Pty Ltd.

This invoice looks ready for review as a Xero draft bill.

Extracted:
- Supplier: Example Supplies Pty Ltd
- ABN: 12 345 678 901
- Date: 12 May 2026
- Total: $110.00
- GST: $10.00

Validation:
- ABN format passed.
- GST arithmetic passed.
- Line items matched the subtotal.

Xero draft bill:
- Type: Purchase bill
- Status: Draft
- Tax type: GST on expenses
- Account code: 453 - Office Expenses
- Account code confidence: High, matched local supplier rule
```

## Batch Processing Behaviour

For batch uploads, each invoice should be processed independently.

Batch output should show the action queue first:

- Number of invoices uploaded.
- Number ready.
- Number needing review.
- Number failed.
- Total GST detected.
- List of invoice-level results.

Example:

```json
{
  "uploaded": 10,
  "ready": 8,
  "needs_review": 2,
  "failed": 0,
  "detected_gst_total": 428.35,
  "results": []
}
```

Recommended demo shape:

> Upload 10 supplier invoice PDFs. The system returns 8 `ready`, 2 `needs_review`, shows the review reasons, and displays Xero draft bill payloads with account-code suggestions.

## POC Success Criteria

The POC should be considered successful if it can:

- Process at least 20 representative Australian supplier invoices.
- Correctly extract supplier, ABN, invoice number, date, GST, and total for most clean invoices.
- Correctly flag incomplete or suspicious invoices.
- Avoid confidently approving bad extractions.
- Produce a plausible Xero draft bill payload.
- Explain results in a way a small business owner can understand.

Suggested target metrics:

- Required field extraction accuracy: 90% or higher on clean invoices.
- GST/total arithmetic validation accuracy: 95% or higher.
- No critical false approvals in the test set.
- Human review required for less than 30% of clean invoices.

## Suggested Test Dataset

Build a small local fixture set:

- Clean tax invoice under AUD 1,000.
- Clean tax invoice over AUD 1,000.
- Small invoice or receipt of AUD 82.50 or less.
- Invoice with missing ABN.
- Invoice with invalid ABN.
- Invoice with GST included but not separately shown.
- Invoice with line items.
- Invoice where line items are messy and require fallback single-line handling.
- Receipt-style invoice.
- Scanned PDF invoice.
- Poor OCR invoice.
- Duplicate supplier invoice number.

Each fixture should have an expected JSON result. This becomes the evaluation harness for the engine.

## Recommended POC Implementation Plan

### Milestone 1: Structured Extraction

- Replace loose JSON parsing with a strict invoice schema.
- Add invoice number, due date, buyer, currency, and line items.
- Return parser errors instead of silently falling back to `{}`.

### Milestone 2: Validation and Confidence

- Expand ABN and GST validation.
- Add issue codes and severity levels.
- Add `ready`, `needs_review`, and `failed` statuses.

### Milestone 3: Xero-Ready Payload

- Add a payload builder for draft purchase bills.
- Add local account-code mapping rules with confidence and reason.
- Keep account-code mapping explicit and reviewable.
- Return the payload without live API posting.

### Milestone 4: Grounded Agent Response

- Make the agent consume engine output only.
- Make it explain validation issues and uncertainty.
- Remove BAS-style summaries from invoice extraction responses.

### Milestone 5: Review And Correction

- Add editable review fields for missing and malformed values.
- Track original extracted values and user-corrected values.
- Re-run validation after corrections.
- Regenerate Xero draft bill payloads from corrected invoice data.

### Milestone 6: Evaluation Harness

- Add fixture invoices or text samples.
- Add expected extraction JSON.
- Add automated tests for parser, validator, and payload builder.

## Recommended Folder Shape

```text
app/
  api/
    routes.py
  engine/
    intake.py
    ocr.py
    parser.py
    schemas.py
    validator.py
    confidence.py
    xero_payload.py
    batch.py
  agent/
    responder.py
  tests/
    fixtures/
    test_parser.py
    test_validator.py
    test_xero_payload.py
```

## Design Principle

The POC should optimise for trustworthy automation, not conversational polish.

The engine should answer:

> Can this invoice become a safe draft bill in Xero?

The agent should answer:

> What happened, what is uncertain, and what should the human do next?
