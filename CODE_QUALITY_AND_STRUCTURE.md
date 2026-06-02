# Code Quality And Directory Structure Guide

## Purpose

This guide defines what the rebuilt POC codebase should feel like.

The current codebase is small, but the logic is shallow and mixed together. The rebuilt POC should still be lightweight, but it should have real engineering depth: typed models, clear module boundaries, deterministic validation, explicit failure handling, and measurable behaviour.

The goal is:

> Thin API, thin UI, thick engine.

The API should receive requests and return results. The UI should display and edit results. The engine should own the invoice processing logic.

## Target Directory Structure

```text
app/
  api/
    routes.py
    dependencies.py

  engine/
    schemas.py
    intake.py
    ocr.py
    parser.py
    validator.py
    confidence.py
    account_mapping.py
    xero_payload.py
    processor.py
    batch.py
    corrections.py

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
    test_parser.py
    test_validator.py
    test_confidence.py
    test_account_mapping.py
    test_xero_payload.py
    test_corrections.py
    test_batch_pipeline.py
    test_agent_grounding.py

config/
  account_mapping_rules.json

ui/
  streamlit_app.py
```

## Module Responsibilities

### app/api/routes.py

FastAPI endpoints only.

Responsibilities:

- Accept PDF uploads.
- Call engine services.
- Return typed results.

Should not:

- Perform invoice validation.
- Call the LLM directly.
- Build Xero payloads.
- Format agent responses manually.

### app/api/dependencies.py

Shared dependency wiring.

Responsibilities:

- Create engine services.
- Create repository/database handles.
- Centralise configuration.

### app/engine/schemas.py

Pydantic models and enums.

Responsibilities:

- Define invoice extraction schema.
- Define validation issue schema.
- Define correction records.
- Define account-code suggestion schema.
- Define Xero draft payload schema.
- Define batch result schema.

All engine modules should exchange these typed models instead of loose dicts.

### app/engine/intake.py

Document intake.

Responsibilities:

- Generate document IDs.
- Capture filename and content type.
- Reject unsupported file types.
- Create initial document metadata.

### app/engine/ocr.py

PDF text extraction and OCR fallback.

Responsibilities:

- Extract text from text PDFs.
- Fall back to OCR for scanned PDFs.
- Return extraction metadata.
- Mark empty text as a failure.

Should not:

- Parse invoice fields.
- Validate GST.
- Call the agent.

### app/engine/parser.py

Structured extraction.

Responsibilities:

- Send extracted text to the LLM.
- Request strict JSON output.
- Validate output against Pydantic schema.
- Retry malformed JSON with strict limits.
- Return parser errors explicitly.

Should not:

- Decide final invoice status.
- Build Xero payloads.
- Hide failures by returning `{}`.

### app/engine/validator.py

Deterministic validation.

Responsibilities:

- Validate required fields.
- Normalize and checksum ABNs.
- Validate dates.
- Validate subtotal, GST, and total arithmetic.
- Check amount-specific ATO requirements.
- Check line item totals.
- Check duplicate supplier ABN plus invoice number.
- Emit issue codes and severity levels.

Should not:

- Ask the LLM whether something is valid.
- Produce friendly agent copy.
- Decide account codes.

### app/engine/confidence.py

Status decision.

Responsibilities:

- Convert validation issues into `ready`, `needs_review`, or `failed`.
- Keep the status rules explicit and testable.

The most important rule:

> Never mark materially uncertain or invalid invoices as `ready`.

### app/engine/account_mapping.py

Account-code suggestions.

Responsibilities:

- Load local mapping rules.
- Match supplier names and line item keywords.
- Return suggested account code, confidence, and reason.
- Return `UNMAPPED` or equivalent when no reliable rule matches.

Should not:

- Block the invoice's main readiness status.
- Pretend low-confidence guesses are certain.

### app/engine/xero_payload.py

Xero-ready draft bill payload generation.

Responsibilities:

- Build `ACCPAY` draft bill payloads.
- Use extracted or corrected invoice fields.
- Use real line items when available.
- Use fallback single line item when allowed.
- Include account-code suggestion metadata.

Should not:

- Call the live Xero API in the POC.
- Mutate invoice extraction data.

### app/engine/processor.py

Single-invoice orchestration.

Responsibilities:

- Run intake, OCR, parser, validation, confidence, account mapping, payload building, and response generation.
- Persist the result.
- Return a complete `InvoiceResult`.

This is the only place where the full single-invoice workflow should be assembled.

### app/engine/batch.py

Batch orchestration.

Responsibilities:

- Process each invoice independently.
- Aggregate counts for `ready`, `needs_review`, and `failed`.
- Preserve per-invoice results.

Should not:

- Hide per-invoice validation issues behind a batch summary.

### app/engine/corrections.py

Structured review corrections.

Responsibilities:

- Apply user corrections to editable fields.
- Record original and corrected values.
- Update `field_sources`.
- Re-run validation and confidence.
- Regenerate Xero payloads after correction.

Corrections should update structured invoice data, not chat history.

### app/agent/responder.py

Template-first explanation layer.

Responsibilities:

- Explain invoice result.
- Explain validation issues.
- Explain correction outcomes.
- Summarise Xero draft payload.

Should not:

- Decide status.
- Invent missing fields.
- Change totals.
- Capture corrections as chat messages.

### app/persistence/database.py

SQLite connection and setup.

Responsibilities:

- Initialise database.
- Manage sessions/connections.

### app/persistence/models.py

Database table definitions.

Responsibilities:

- Define document, invoice result, correction, and batch tables.

### app/persistence/repositories.py

Persistence operations.

Responsibilities:

- Save and load invoice results.
- Save corrections.
- Save and load batches.
- Support duplicate detection.

## Core Workflow Shape

The processing flow should look like this:

```python
result = processor.process_invoice(file)
```

Internally:

```python
document = intake.create_document(file)
text_result = ocr.extract(file)
extraction = parser.parse(text_result.text)
validation = validator.validate(extraction)
status = confidence.decide(validation)
account = account_mapper.suggest(extraction)
payload = xero_payload.build(extraction, account, status)
response = responder.render(result)
```

Each step should return a typed object.

## Engineering Standards

### Typed Models Over Loose Dicts

Use Pydantic models for core engine data.

Avoid passing raw dicts between engine modules except when building external payloads.

### Decimal For Money

Use `Decimal` for money values.

Avoid floats for:

- Subtotal.
- GST.
- Total.
- Unit amounts.
- Line item totals.

### Explicit Issue Codes

Validation should return issue codes.

Examples:

- `MISSING_SUPPLIER_ABN`
- `INVALID_ABN`
- `GST_TOTAL_MISMATCH`
- `MISSING_BUYER_FOR_OVER_1000`
- `DUPLICATE_INVOICE`
- `OCR_EMPTY_TEXT`
- `PARSER_SCHEMA_INVALID`

Do not rely only on prose warning strings.

### Explicit Failure Handling

Failures should be visible in the result object.

Bad patterns:

```python
except Exception:
    return {}
```

```python
except Exception:
    return ""
```

Good pattern:

```python
return InvoiceResult(
    status=InvoiceStatus.FAILED,
    validation=ValidationResult(
        status=InvoiceStatus.FAILED,
        issues=[
            ValidationIssue(
                code="OCR_EMPTY_TEXT",
                severity="error",
                message="No text could be extracted from the PDF."
            )
        ]
    )
)
```

### Agent Is Not The Engine

The agent can explain results but cannot create accounting truth.

The agent must not:

- Decide if an invoice is valid.
- Decide if an invoice is ready.
- Invent extracted values.
- Hide validation issues.
- Convert chat corrections into data silently.

### Corrections Are Structured

User corrections should be applied to fields.

Example:

```json
{
  "field": "supplier_abn",
  "original_value": "123 456 789 00",
  "corrected_value": "12 345 678 901",
  "source": "user_correction"
}
```

After correction:

- The invoice object is updated.
- `field_sources` is updated.
- Validation is re-run.
- Status is recalculated.
- Xero payload is regenerated.

### Batch Is Many Singles

Batch processing should not have separate accounting logic.

Batch should:

- Process each invoice with the single-invoice processor.
- Aggregate statuses.
- Preserve each invoice's validation issues and payload.

### Xero Payload Is Separate

Xero payload generation should live in `xero_payload.py`.

Do not mix Xero payload construction into:

- Parser.
- Validator.
- Agent.
- UI.

### Configuration Is Explicit

Account-code rules should live in:

```text
config/account_mapping_rules.json
```

The mapping system should explain why a code was suggested.

## What Good Code Looks Like

Good POC code should be:

- Small but not shallow.
- Typed.
- Modular.
- Deterministic where possible.
- Conservative about readiness.
- Honest about uncertainty.
- Easy to test.

The code should make this easy to answer:

> Why was this invoice marked ready?

And this:

> What exactly needs review?

And this:

> Did the agent say anything that was not in the engine result?

## What To Avoid

Avoid:

- One large agent class controlling the whole workflow.
- LLM output being treated as truth without schema validation.
- Friendly responses hiding validation problems.
- Global mutable memory for invoice state.
- Hard-coded business names.
- Cafe-specific assumptions.
- BAS calculations as the primary invoice workflow.
- Regex-only parsing for all invoice fields.
- Returning empty strings or empty dicts on failure.
- UI code that performs accounting validation.

## Minimum Quality Bar

Before the POC is demoed, the codebase should have:

- Typed schemas for all core objects.
- Deterministic validation issue codes.
- Explicit `ready`, `needs_review`, and `failed` status rules.
- Structured correction workflow.
- Xero draft bill payload builder.
- Batch processing with per-invoice results.
- Tests for parser, validator, confidence, corrections, mapping, payload, and agent grounding.
- Zero critical false-ready approvals on the fixture set.

