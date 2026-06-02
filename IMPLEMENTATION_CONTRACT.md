# Invoice Automation POC Implementation Contract

## Purpose

This document turns the POC design into a buildable implementation contract.

The implementation should prove that the invoice engine can process Australian supplier invoice PDFs, extract structured data, validate bookkeeping requirements, support user corrections, and generate Xero-ready draft purchase bill payloads.

The POC should prioritise correctness, traceability, and testability over production-grade scale.

## Recommended Stack

### Backend

Use **FastAPI**.

Reasons:

- The current project already uses FastAPI.
- It handles PDF uploads cleanly with `UploadFile`.
- It gives a simple API boundary between the engine and UI.
- It can later be moved toward a production API without changing the engine contract.

### Schema And Validation

Use **Pydantic v2** models.

Reasons:

- Invoice extraction needs strict structured schemas.
- Parser output must be validated before downstream use.
- Pydantic models can produce JSON schema for test fixtures and frontend contracts.
- It prevents the current loose-dict behaviour from spreading.

### Engine

Use plain Python service modules.

Do not use LangGraph as the core workflow engine for the POC.

Recommended workflow:

```text
intake
  -> ocr
  -> parser
  -> validator
  -> confidence
  -> account_mapping
  -> xero_payload
  -> responder
```

Reasons:

- The workflow is mostly deterministic.
- Each step should be unit-testable.
- The agent should not control accounting logic.
- Typed service modules are easier to debug than an agent graph.

### Persistence

Use **SQLite** for the POC.

Reasons:

- Enough to store uploaded document metadata, extraction results, corrections, validation issues, and batch results.
- Supports duplicate detection across a demo session.
- Keeps the POC lightweight.
- Can later become Postgres without changing the domain model too much.

Use SQLAlchemy or SQLModel if persistence grows beyond simple CRUD.

### OCR

Use PDF text extraction first, then OCR fallback.

Recommended:

- Text PDFs: PyPDF2 or PyMuPDF.
- Scanned PDFs: Tesseract fallback.

Important:

- Empty text is a failure condition.
- OCR method and warnings should be recorded.
- OCR should return metadata, not just a string.

### Parser

Use LLM extraction with strict Pydantic validation.

Rules:

- The LLM extracts structured JSON.
- Pydantic validates the JSON.
- Malformed output is retried a limited number of times.
- If still invalid, mark the invoice `failed` or `needs_review` depending on what was recovered.
- Never silently return `{}`.

### Agent / Response Layer

Use a template-first response layer.

Optional LLM wording is allowed only after the engine has produced facts.

Rules:

- The agent cannot change status.
- The agent cannot change values.
- The agent cannot invent missing fields.
- The agent explains extraction, validation issues, corrections, and next actions.

### Frontend

Use **Streamlit** for the POC UI.

Reasons:

- The current project already uses Streamlit.
- It is fast enough for a proof of concept.
- It can support upload, batch queue, editable fields, validation panels, and payload preview.
- A production frontend can be rebuilt later after the engine is proven.

### Testing

Use **pytest** with golden fixtures.

Testing should cover:

- OCR.
- Parser schema validation.
- Validation rules.
- Confidence status.
- Account-code mapping.
- Review corrections.
- Xero payload generation.
- Agent grounding.
- Batch pipeline.

## Proposed Folder Structure

Detailed code quality expectations are defined in `CODE_QUALITY_AND_STRUCTURE.md`.

```text
app/
  api/
    routes.py
    dependencies.py
  engine/
    intake.py
    ocr.py
    parser.py
    schemas.py
    validator.py
    confidence.py
    account_mapping.py
    xero_payload.py
    batch.py
  agent/
    responder.py
  persistence/
    database.py
    models.py
    repositories.py
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
ui/
  streamlit_app.py
config/
  account_mapping_rules.json
```

## Core Pydantic Schemas

### InvoiceStatus

```python
from enum import Enum

class InvoiceStatus(str, Enum):
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
```

### LineItem

```python
from decimal import Decimal
from pydantic import BaseModel

class LineItem(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    gst_amount: Decimal | None = None
    tax_treatment: str | None = None
    source: str = "parser"
```

### InvoiceExtraction

```python
from decimal import Decimal
from pydantic import BaseModel

class InvoiceExtraction(BaseModel):
    document_id: str
    supplier_name: str | None = None
    supplier_abn: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    buyer_name: str | None = None
    buyer_abn: str | None = None
    subtotal: Decimal | None = None
    gst: Decimal | None = None
    total: Decimal | None = None
    currency: str = "AUD"
    line_items: list[LineItem] = []
    line_items_source: str = "parser"
    field_sources: dict[str, str] = {}
```

### ValidationIssue

```python
from pydantic import BaseModel

class ValidationIssue(BaseModel):
    code: str
    severity: str
    field: str | None = None
    message: str
    suggested_action: str | None = None
```

### ValidationResult

```python
from pydantic import BaseModel

class ValidationResult(BaseModel):
    status: InvoiceStatus
    issues: list[ValidationIssue] = []
```

### CorrectionRecord

```python
from pydantic import BaseModel

class CorrectionRecord(BaseModel):
    field: str
    original_value: object | None = None
    corrected_value: object | None = None
    source: str = "user_correction"
```

### AccountCodeSuggestion

```python
from pydantic import BaseModel

class AccountCodeSuggestion(BaseModel):
    suggested_account_code: str | None = None
    suggested_account_name: str | None = None
    confidence: str
    reason: str
    status: str
```

### XeroDraftBillPayload

```python
from pydantic import BaseModel

class XeroDraftBillPayload(BaseModel):
    Type: str = "ACCPAY"
    Status: str = "DRAFT"
    Contact: dict
    InvoiceNumber: str
    Date: str
    DueDate: str | None = None
    LineAmountTypes: str
    LineItems: list[dict]
```

### InvoiceResult

```python
from pydantic import BaseModel

class InvoiceResult(BaseModel):
    document_id: str
    filename: str
    status: InvoiceStatus
    extraction: InvoiceExtraction | None = None
    validation: ValidationResult
    account_code_suggestion: AccountCodeSuggestion | None = None
    xero_payload: XeroDraftBillPayload | None = None
    corrections: list[CorrectionRecord] = []
    response: str | None = None
```

### BatchResult

```python
from pydantic import BaseModel

class BatchResult(BaseModel):
    batch_id: str
    uploaded: int
    ready: int
    needs_review: int
    failed: int
    detected_gst_total: Decimal
    results: list[InvoiceResult]
```

## API Contract

### Process Single Invoice

```http
POST /invoices/process
```

Input:

- Multipart form upload with one PDF file.

Output:

- `InvoiceResult`.

### Process Batch

```http
POST /batches/process
```

Input:

- Multipart form upload with multiple PDF files.

Output:

- `BatchResult`.

### Apply Correction

```http
PATCH /invoices/{document_id}/corrections
```

Input:

```json
{
  "field": "supplier_abn",
  "value": "12 345 678 901"
}
```

Behaviour:

- Load invoice result.
- Apply correction to structured invoice object.
- Record original and corrected values.
- Update `field_sources`.
- Re-run validation and confidence scoring.
- Regenerate Xero payload if invoice becomes `ready`.

Output:

- Updated `InvoiceResult`.

### Get Invoice

```http
GET /invoices/{document_id}
```

Output:

- Current `InvoiceResult`.

### Get Batch

```http
GET /batches/{batch_id}
```

Output:

- Current `BatchResult`.

## SQLite Persistence Model

### documents

Stores uploaded file metadata.

Fields:

- `document_id`
- `batch_id`
- `filename`
- `content_type`
- `created_at`
- `ocr_status`
- `ocr_method`

### invoice_results

Stores the latest structured invoice result.

Fields:

- `document_id`
- `status`
- `extraction_json`
- `validation_json`
- `account_mapping_json`
- `xero_payload_json`
- `response_text`
- `updated_at`

### corrections

Stores user corrections.

Fields:

- `correction_id`
- `document_id`
- `field`
- `original_value`
- `corrected_value`
- `source`
- `created_at`

### batches

Stores batch summary.

Fields:

- `batch_id`
- `uploaded`
- `ready`
- `needs_review`
- `failed`
- `detected_gst_total`
- `created_at`
- `updated_at`

For the POC, source PDFs can be kept temporarily on disk or only in request memory. If keeping files on disk, store them under a local ignored folder such as `data/uploads/`.

## Engine Workflow

### Single Invoice

```text
1. Create document ID.
2. Extract text from PDF.
3. If text extraction fails, run OCR.
4. If OCR returns empty text, return failed result.
5. Parse text into InvoiceExtraction.
6. Validate schema.
7. Run deterministic validation.
8. Apply confidence status.
9. Suggest account code from local mapping rules.
10. Build Xero draft bill payload if invoice is ready or draftable.
11. Generate template-first response.
12. Persist result.
13. Return InvoiceResult.
```

### Batch

```text
1. Create batch ID.
2. Process each PDF independently.
3. Persist each invoice result.
4. Count ready, needs_review, and failed invoices.
5. Return action queue summary first.
```

### Correction

```text
1. Load current invoice result.
2. Apply structured field correction.
3. Record correction.
4. Re-run validation.
5. Recalculate status.
6. Re-run account mapping if relevant.
7. Regenerate Xero payload if possible.
8. Regenerate response.
9. Persist updated result.
10. Return updated InvoiceResult.
```

## LLM Parser Failure Rules

Use strict retry behaviour.

Recommended:

- Attempt 1: extract using strict JSON schema prompt.
- Attempt 2: if malformed JSON, ask model to repair into schema using the previous output.
- Attempt 3: if still malformed, return parser failure.

Status rules:

- If parser fails completely: `failed`.
- If parser returns partial but critical fields are missing: `needs_review`.
- If parser returns partial but validation can pass after fallback line item: `ready` may be allowed.

Critical fields:

- Supplier name.
- Supplier ABN.
- Invoice number.
- Invoice date.
- Total.
- GST or enough data to infer GST treatment.

## Validation Rules

The validator should produce issue codes, not just messages.

Recommended issue codes:

- `MISSING_SUPPLIER_NAME`
- `MISSING_SUPPLIER_ABN`
- `INVALID_ABN`
- `MISSING_INVOICE_NUMBER`
- `MISSING_INVOICE_DATE`
- `INVALID_INVOICE_DATE`
- `MISSING_TOTAL`
- `MISSING_GST`
- `GST_TOTAL_MISMATCH`
- `LINE_ITEMS_TOTAL_MISMATCH`
- `MISSING_BUYER_FOR_OVER_1000`
- `DUPLICATE_INVOICE`
- `UNSUPPORTED_CURRENCY`
- `OCR_EMPTY_TEXT`
- `PARSER_INVALID_JSON`
- `PARSER_SCHEMA_INVALID`

## UI Contract

The UI should not be chat-first.

### Screen 1: Upload

Capabilities:

- Upload one PDF.
- Upload multiple PDFs.
- Start processing.

### Screen 2: Batch Action Queue

Show first:

- Ready count.
- Needs review count.
- Failed count.
- Total detected GST.

Then group invoices by status:

- `ready`
- `needs_review`
- `failed`

### Screen 3: Invoice Detail

Show:

- Source filename.
- Status.
- Extracted fields.
- Validation issues.
- Account-code suggestion.
- Xero draft payload preview.
- Agent explanation panel.

### Screen 4: Editable Review Panel

For `needs_review` invoices, show editable fields.

Rules:

- Highlight fields tied to validation issues.
- User edits structured fields.
- User submits correction.
- Backend re-validates.
- Updated status is shown.

### Screen 5: Payload Preview

Show generated Xero draft bill payload.

For POC:

- Display JSON.
- Do not post to Xero.

## Agent Response Contract

The response should be generated from `InvoiceResult`, not raw invoice text.

Required response content:

- Invoice identity.
- Status.
- Extracted totals.
- Validation result.
- Review issues.
- Correction outcome, if applicable.
- Xero draft bill summary.

Forbidden:

- Inventing fields.
- Changing status.
- Recalculating totals using LLM-only reasoning.
- Hiding validation issues.
- Capturing corrections as chat text.

## Testing Contract

The implementation must support the metrics in `TESTING_STRATEGY.md`.

Minimum test coverage before demo:

- Parser schema tests.
- Validator tests.
- Confidence status tests.
- Correction workflow tests.
- Account mapping tests.
- Xero payload tests.
- Batch pipeline tests.
- Agent grounding tests.

Most important acceptance metric:

- 0 critical false-ready approvals on the fixture set.

## Build Milestones

### Milestone 1: Engine Schemas

- Add Pydantic schemas.
- Replace loose dicts with typed models.
- Add fixture text samples.

### Milestone 2: Parser And Validation

- Implement strict parser output.
- Implement validation issue codes.
- Implement confidence status.

### Milestone 3: Xero Payload And Account Mapping

- Add local account mapping file.
- Add account-code suggestions.
- Generate Xero draft bill payloads.

### Milestone 4: Review Corrections

- Add correction API.
- Track original and corrected values.
- Re-run validation after edits.

### Milestone 5: Batch Workflow UI

- Build Streamlit upload flow.
- Show action queue.
- Show editable invoice detail panel.
- Show payload preview.

### Milestone 6: Testing And Metrics

- Add pytest suite.
- Add golden fixtures.
- Generate metric report for demo.

## Implementation Principle

The engine should be boring and reliable.

The agent should be helpful, but never authoritative.

The UI should make the next action obvious:

> Ready, needs review, or failed.
