# Implementation Progress

This file tracks the POC rebuild against the project docs:

- `POC_ENGINE_DESIGN.md`
- `IMPLEMENTATION_CONTRACT.md`
- `TESTING_STRATEGY.md`
- `CODE_QUALITY_AND_STRUCTURE.md`

## Phase 1 - Inspection And Planning

### Docs Re-Read

- Read `POC_ENGINE_DESIGN.md`.
- Read `IMPLEMENTATION_CONTRACT.md`.
- Read `TESTING_STRATEGY.md`.
- Read `CODE_QUALITY_AND_STRUCTURE.md`.

### What Was Implemented

- Inspected the current repository structure.
- Identified the old app as chat/BAS-first with LangGraph in the core invoice path.
- Identified reusable pieces:
  - Existing ABN checksum logic.
  - Existing PDF text extraction first, OCR fallback pattern.
- Created the target folder scaffolding:
  - `app/api`
  - `app/engine`
  - `app/agent`
  - `app/persistence`
  - `app/tests/fixtures`
  - `config`
  - `data`

### Requirements Satisfied

- Implementation sequence item 1: inspect the current codebase.
- Started implementation sequence item 2: restructure into the documented folder structure.
- Confirmed the rebuild must be engine-first, not chat-first.
- Confirmed LangGraph must not be used as the core engine.

### Files Changed

- Added `IMPLEMENTATION_PROGRESS.md`.
- Added empty target directories.

### Tests Run

- No tests run yet.
- The available shell PATH does not expose `python`; Codex bundled Python is available at `C:\Users\parth\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.

### Remaining Work

- Implement typed Pydantic schemas.
- Implement OCR/parser/validator/confidence/account mapping/payload/corrections/batch engine modules.
- Replace API routes with the documented endpoints.
- Rebuild Streamlit into a review UI.
- Add fixtures and pytest coverage.
- Run tests and perform local smoke verification.

## Phase 2 - Engine, API, Persistence, And UI Rebuild

### Docs Re-Read

- Re-read `POC_ENGINE_DESIGN.md`.
- Re-read `IMPLEMENTATION_CONTRACT.md`.
- Re-read `CODE_QUALITY_AND_STRUCTURE.md`.

### What Was Implemented

- Added typed Pydantic engine schemas for documents, OCR results, parser results, invoice extraction, line items, validation issues/results, correction records, account-code suggestions, Xero draft payloads, invoice results, and batch results.
- Implemented document intake with PDF-only enforcement and stable document/batch IDs.
- Implemented OCR service returning explicit `OCRResult` metadata, with PDF text extraction first and Tesseract fallback.
- Implemented strict parser service:
  - Optional LLM parsing when `GROQ_API_KEY` is present.
  - Bounded retry/repair prompt path.
  - Strict Pydantic schema validation.
  - Deterministic local parser for fixture and offline demo text.
  - Explicit parser failure results instead of `{}`.
- Implemented deterministic validation:
  - ABN normalization/checksum.
  - Required fields.
  - Date parsing.
  - GST/subtotal/total arithmetic.
  - GST one-eleventh check.
  - AUD-only currency.
  - Buyer identity for invoices AUD 1,000 or more.
  - Line item total checks.
  - Duplicate supplier ABN plus invoice number detection.
- Implemented confidence/status decision logic with conservative failure codes.
- Implemented account-code mapping from `config/account_mapping_rules.json` with confidence/reason/status.
- Implemented Xero `ACCPAY` draft bill payload generation with line-item account-code suggestion metadata.
- Implemented template-first responder that explains engine results only.
- Implemented SQLite repository plus in-memory repository for deterministic tests.
- Implemented single-invoice processor orchestration.
- Implemented batch processor as many independent single-invoice runs.
- Implemented structured correction service:
  - Editable invoice fields.
  - Correction records.
  - Field source updates.
  - Re-validation.
  - Confidence/status recalculation.
  - Account mapping/payload regeneration.
  - Account-code correction support.
- Replaced FastAPI app with documented endpoints:
  - `POST /invoices/process`
  - `POST /batches/process`
  - `PATCH /invoices/{document_id}/corrections`
  - `GET /invoices/{document_id}`
  - `GET /batches/{batch_id}`
  - `GET /health`
- Rebuilt Streamlit as a non-chat review UI:
  - Single/batch PDF upload.
  - Action queue grouped by status.
  - Invoice detail panel.
  - Editable review fields.
  - Validation issue display.
  - Account-code suggestion display.
  - Xero payload preview.
  - Template-first explanation panel.

### Requirements Satisfied

- Implementation sequence items 2 through 12 are implemented at POC level.
- API thin, UI thin, engine thick.
- Core engine objects are typed Pydantic models.
- Money fields use `Decimal`.
- Validation uses deterministic issue codes.
- Agent/responder explains engine results only.
- Corrections update structured invoice data and track original/corrected values.
- Batch processing preserves per-invoice results and action queue counts.
- Xero payload generation is local only and draft-only.

### Files Changed

- Added `app/api/__init__.py`.
- Added `app/api/dependencies.py`.
- Added `app/api/routes.py`.
- Replaced `app/main.py`.
- Added `app/agent/__init__.py`.
- Added `app/agent/responder.py`.
- Added `app/engine/__init__.py`.
- Added `app/engine/account_mapping.py`.
- Added `app/engine/batch.py`.
- Added `app/engine/confidence.py`.
- Added `app/engine/corrections.py`.
- Added `app/engine/intake.py`.
- Added `app/engine/ocr.py`.
- Added `app/engine/parser.py`.
- Added `app/engine/processor.py`.
- Added `app/engine/schemas.py`.
- Added `app/engine/validator.py`.
- Added `app/engine/xero_payload.py`.
- Added `app/persistence/__init__.py`.
- Added `app/persistence/database.py`.
- Added `app/persistence/models.py`.
- Added `app/persistence/repositories.py`.
- Added `config/account_mapping_rules.json`.
- Replaced `ui/streamlit_app.py`.
- Updated `IMPLEMENTATION_PROGRESS.md`.

### Tests Run

- No automated tests run yet.
- Static read-through found and fixed cumulative correction update handling.

### Remaining Work

- Add synthetic Australian invoice fixtures and expected outputs.
- Add pytest coverage for parser, validator, confidence, account mapping, Xero payload, corrections, batch pipeline, and agent grounding.
- Run tests and fix failures.
- Attempt local API/UI smoke verification.

## Phase 3 - Fixtures And Deterministic Tests

### Docs Re-Read

- Re-read `TESTING_STRATEGY.md`.
- Re-read `IMPLEMENTATION_CONTRACT.md`.

### What Was Implemented

- Added synthetic Australian supplier invoice OCR text fixtures covering:
  - Clean tax invoice under AUD 1,000.
  - Clean tax invoice over AUD 1,000.
  - Small receipt under AUD 82.50.
  - Clear line items.
  - Messy invoice requiring fallback single-line item.
  - Local account-code mapping matches.
  - Unmapped account-code review.
  - Missing ABN.
  - Invalid ABN.
  - GST not separately shown.
  - Missing buyer identity over AUD 1,000.
  - Subtotal/GST/total mismatch.
  - Line-item mismatch.
  - Unsupported currency.
  - Missing invoice number.
  - Duplicate supplier ABN plus invoice number.
  - Poor OCR/unusable text.
- Added expected-output manifest at `app/tests/fixtures/expected/invoice_cases.json`.
- Added pytest coverage for:
  - Parser schema extraction and parser failures.
  - Validator issue codes and statuses.
  - Confidence/status decision logic.
  - Account-code mapping.
  - Xero draft payload generation.
  - Correction workflow and field-source tracking.
  - Batch pipeline counts and duplicate detection.
  - Agent/responder grounding.
  - OCR empty-text failure metadata.
- Added an all-fixture status test that checks expected statuses and ensures non-ready fixtures are never marked `ready`.

### Requirements Satisfied

- Implementation sequence item 13: synthetic Australian supplier invoice fixtures and expected outputs.
- Implementation sequence item 14: pytest coverage for parser, validator, confidence, account mapping, Xero payload, corrections, batch pipeline, and agent grounding.
- Testing standard coverage for:
  - Deterministic fixtures.
  - Zero critical false-ready approvals.
  - Editable corrections updating structured fields.
  - Re-validation and payload regeneration after correction.
  - Agent not overriding validation status.

### Files Changed

- Added `app/tests/__init__.py`.
- Added `app/tests/conftest.py`.
- Added `app/tests/test_parser.py`.
- Added `app/tests/test_validator.py`.
- Added `app/tests/test_confidence.py`.
- Added `app/tests/test_account_mapping.py`.
- Added `app/tests/test_xero_payload.py`.
- Added `app/tests/test_corrections.py`.
- Added `app/tests/test_batch_pipeline.py`.
- Added `app/tests/test_agent_grounding.py`.
- Added `app/tests/test_ocr.py`.
- Added OCR text fixtures under `app/tests/fixtures/ocr_text`.
- Added expected manifest under `app/tests/fixtures/expected`.
- Updated `app/engine/parser.py` to fail unusable OCR text explicitly.
- Updated `IMPLEMENTATION_PROGRESS.md`.

### Tests Run

- No automated test command has been run yet.

### Remaining Work

- Run pytest.
- Fix failures.
- Attempt local API/UI smoke verification.
- Re-read all source-of-truth docs before final response and verify gaps.

## Phase 4 - Test Run, Cleanup, And Local Smoke Verification

### Docs Re-Read

- Re-read `TESTING_STRATEGY.md`.

### What Was Implemented

- Installed missing local test/runtime dependencies into the Codex bundled Python runtime:
  - `pytest`
  - FastAPI/UI dependencies needed for local smoke checks.
  - `httpx2` for FastAPI `TestClient`.
- Removed legacy chat/BAS/LangGraph-oriented modules from the active package:
  - `app/agent.py`
  - `app/bas_calculator.py`
  - `app/batch_processor.py`
  - `app/core_tools.py`
  - `app/ocr.py`
  - `app/parser.py`
  - `app/tool.py`
  - `app/validator.py`
- Cleaned `requirements.txt` so it matches the rebuilt POC and does not include LangGraph.
- Added a pure-Python PDF fixture generator.
- Generated synthetic PDF fixtures under `app/tests/fixtures/invoices`.
- Added OCR coverage for a readable generated PDF fixture.
- Removed deprecated Pydantic `json_encoders` config and deprecated UTC timestamp usage.
- Started the local FastAPI server on `http://127.0.0.1:8010`.
- Started the local Streamlit review UI on `http://127.0.0.1:8501` with non-interactive flags:
  - `--browser.gatherUsageStats false`
  - `--server.headless true`
- Verified:
  - API health endpoint returns `ok`.
  - Streamlit UI returns HTTP 200.
  - Real HTTP upload to `POST /invoices/process` with a generated PDF returns `ready` and Xero `ACCPAY`.
  - In-process FastAPI smoke verifies single upload, batch upload, and correction workflow.

### Requirements Satisfied

- Implementation sequence item 15: ran tests and fixed failures.
- Implementation sequence item 16: ran the app locally and verified the end-to-end POC path.
- Confirmed generated PDFs can pass through the OCR/PDF text path.
- Confirmed correction flow moves an invalid-ABN invoice from `needs_review` to `ready` when corrected.
- Confirmed Xero payload is regenerated after correction.
- Confirmed no legacy LangGraph core engine remains in the active app structure.

### Files Changed

- Deleted legacy app modules listed above.
- Updated `app/__init__.py`.
- Updated `app/engine/schemas.py`.
- Updated `app/persistence/repositories.py`.
- Updated `app/tests/test_ocr.py`.
- Added `app/tests/fixtures/make_pdf_fixtures.py`.
- Generated PDF fixtures under `app/tests/fixtures/invoices`.
- Updated `requirements.txt`.
- Updated `IMPLEMENTATION_PROGRESS.md`.

### Tests Run

- `python -m pytest app\tests -q`
  - Result: `45 passed, 1 warning`.
  - Warning: `PyPDF2` package deprecation warning recommending `pypdf`.
- API import smoke:
  - `import app.main`
  - Result: passed.
- Streamlit import smoke:
  - `import ui.streamlit_app`
  - Result: passed with expected bare-mode Streamlit warnings.
- FastAPI in-process endpoint smoke:
  - Single upload: `200 ready ACCPAY`.
  - Batch upload: `200`, uploaded `2`, ready `1`, needs_review `1`, failed `0`.
  - Correction: `200 ready user_correction ACCPAY`.
- Running API HTTP smoke:
  - `POST http://127.0.0.1:8010/invoices/process`
  - Result: `200 ready ACCPAY`.
- Streamlit HTTP smoke:
  - `GET http://127.0.0.1:8501`
  - Result: `200`.

### Remaining Work

- Final re-read of all four source-of-truth docs.
- Verify implementation against docs and report gaps.
- Note known limitation: browser visual automation was attempted through the available Node REPL path but failed with a sandbox spawn error, so UI verification is HTTP/import based rather than screenshot-based.

## Phase 5 - Final Contract Verification

### Docs Re-Read

- Re-read `POC_ENGINE_DESIGN.md`.
- Re-read `IMPLEMENTATION_CONTRACT.md`.
- Re-read `TESTING_STRATEGY.md`.
- Re-read `CODE_QUALITY_AND_STRUCTURE.md`.

### What Was Implemented

- Updated `.gitignore` to exclude local runtime SQLite/log/PID artifacts under `data`.
- Re-ran the full deterministic test suite after final cleanup.
- Rechecked repository shape against the documented target structure.
- Confirmed the running local endpoints:
  - FastAPI API: `http://127.0.0.1:8010`
  - Streamlit UI: `http://127.0.0.1:8501`

### Requirements Satisfied

- Full source-of-truth doc re-read completed before final response.
- Folder structure now matches the documented engine/API/UI/persistence/test split.
- API is thin and routes to engine services.
- UI is non-chat and review/work-queue oriented.
- Engine owns OCR, parsing, validation, status, account mapping, payload building, corrections, and batch orchestration.
- LangGraph is not present in the active implementation or requirements.
- Tests prove zero false-ready approvals across the deterministic fixture set.
- Local API and Streamlit servers were started and smoke checked.

### Files Changed

- Updated `.gitignore`.
- Updated `IMPLEMENTATION_PROGRESS.md`.

### Tests Run

- `python -m pytest app\tests -q`
  - Result: `45 passed, 1 warning`.
  - Warning: `PyPDF2` package deprecation warning recommending `pypdf`.

### Remaining Gaps / Limitations

- LLM parser path is implemented with strict schema validation and bounded retry/repair, but the live LLM path was not exercised because no API key was used in deterministic tests.
- Scanned-PDF OCR fallback code exists, but the fixture set uses generated text PDFs plus poor-OCR text rather than a true image-only scanned PDF fixture.
- Browser visual automation was attempted through the available Node REPL tool, but that tool failed with a sandbox spawn error. UI verification is therefore HTTP/import based rather than screenshot based.
- The parser has a deterministic fallback suitable for synthetic fixtures; real-world supplier PDFs will need evaluation tuning against a larger invoice corpus.
- `PyPDF2` emits a deprecation warning; switching to `pypdf` would remove that warning later.

## Phase 6 - Quality Findings Fix Pass

### Docs Re-Read

- Re-read `POC_ENGINE_DESIGN.md`.
- Re-read `IMPLEMENTATION_CONTRACT.md`.
- Re-read `TESTING_STRATEGY.md`.
- Re-read `CODE_QUALITY_AND_STRUCTURE.md`.
- Re-read `IMPLEMENTATION_CONTRACT.md` and `CODE_QUALITY_AND_STRUCTURE.md` again before touching API/persistence/payload/UI boundaries.

### What Was Implemented

- Replaced `httpx2` with `httpx` in `requirements.txt`.
- Kept internal money fields as `Decimal`, but converted Xero line item numeric fields to JSON-safe numbers:
  - `Quantity`
  - `UnitAmount`
  - `LineAmount`
- Changed Xero payload policy so `xero_payload` is populated only when invoice status is `ready`.
- Updated Streamlit copy to state that no final Xero payload is available until the invoice is ready.
- Added a development-gated demo reset path:
  - `POST /demo/reset`
  - Enabled only when `INVOICE_DEMO_RESET_ENABLED` is truthy or `APP_ENV` is `development`, `dev`, `local`, or `test`.
  - Returns `403` outside development/demo mode.
- Added repository reset methods for SQLite and in-memory repositories.
- Added Streamlit “Reset demo data” button that calls the gated reset endpoint and clears session state.
- Added small-receipt relaxed ABN behavior for invoices at or under AUD 82.50:
  - Missing supplier ABN can pass for small receipts when Xero draft fields and financial checks are present.
  - Invalid supplied ABNs still fail checksum and require review.
  - Normal invoices above AUD 82.50 still require supplier ABN.
- Added `small_receipt_missing_abn` OCR/PDF fixtures and expected output.
- Regenerated synthetic PDF fixtures from OCR text fixtures.
- Added FastAPI `TestClient` coverage for:
  - `POST /invoices/process`
  - `POST /batches/process`
  - `PATCH /invoices/{document_id}/corrections`
  - `GET /invoices/{document_id}`
  - `GET /batches/{batch_id}`
  - Gated `POST /demo/reset`
- Added regression tests for:
  - Xero payload numbers are JSON numbers, not strings.
  - Needs-review invoices expose no final Xero payload.
  - Requirements use `httpx`, not `httpx2`.
  - SQLite reset clears duplicate detection state.
  - Small-receipt ABN relaxation does not apply to normal invoices.

### Requirements Satisfied

- Fixed dependency typo and verified with a requirements test.
- Fixed Xero payload JSON numeric serialization while keeping internal engine money as `Decimal`.
- Implemented the safest needs-review payload policy: final payload only for `ready`.
- Added safe development-gated demo reset path and UI control.
- Added isolated duplicate/reset tests.
- Added small-invoice relaxation fixture/tests without weakening Xero draft fields.
- Added API endpoint tests for the full required endpoint list.
- Preserved thin API, thin UI, thick engine.
- Did not reintroduce chat-first behavior or LangGraph.

### Files Changed

- Updated `requirements.txt`.
- Updated `app/engine/xero_payload.py`.
- Updated `app/engine/validator.py`.
- Updated `app/persistence/repositories.py`.
- Updated `app/api/dependencies.py`.
- Updated `app/api/routes.py`.
- Updated `ui/streamlit_app.py`.
- Added `app/tests/fixtures/ocr_text/small_receipt_missing_abn.txt`.
- Regenerated `app/tests/fixtures/invoices/*.pdf`.
- Updated `app/tests/fixtures/expected/invoice_cases.json`.
- Updated `app/tests/test_xero_payload.py`.
- Updated `app/tests/test_corrections.py`.
- Updated `app/tests/test_batch_pipeline.py`.
- Added `app/tests/test_api_endpoints.py`.
- Added `app/tests/test_persistence_reset.py`.
- Added `app/tests/test_requirements.py`.
- Updated `IMPLEMENTATION_PROGRESS.md`.

### Tests Run

- `python -m pytest app\tests -q`
  - Result: `54 passed, 1 warning`.
  - Warning: `PyPDF2` package deprecation warning recommending `pypdf`.
- Evidence sweep:
  - `rg "httpx2|LangGraph|langgraph|chat" requirements.txt app ui -n`
  - Result: only the requirements regression test references `httpx2`; no active LangGraph/chat-first code found.
- Serialization check:
  - Ready invoice Xero line values serialize as JSON `int`/number types.
  - Review invoice serializes with `xero_payload = None`.

### Remaining Risks

- `PyPDF2` is still used and emits a deprecation warning; moving to `pypdf` would be a tidy follow-up.
- The live LLM parser path remains unexercised in deterministic tests because tests intentionally use the offline parser path.
- True scanned image-only PDFs are still not represented as binary fixtures; OCR fallback code exists but is not tested with a real scanned PDF.
