from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_batch_processor,
    get_correction_service,
    get_processor,
    get_repository,
)
from app.engine.batch import BatchProcessor
from app.engine.corrections import CorrectionService
from app.engine.parser import InvoiceParser
from app.engine.processor import InvoiceProcessor
from app.main import app
from app.persistence.repositories import InMemoryInvoiceRepository
from app.tests.conftest import FIXTURE_ROOT


@contextmanager
def _pdf(name: str):
    path = FIXTURE_ROOT / "invoices" / f"{name}.pdf"
    with path.open("rb") as file_handle:
        yield (f"{name}.pdf", file_handle, "application/pdf")


def _client():
    repository = InMemoryInvoiceRepository()
    processor = InvoiceProcessor(
        repository=repository,
        parser=InvoiceParser(use_llm=False),
    )
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_processor] = lambda: processor
    app.dependency_overrides[get_batch_processor] = lambda: BatchProcessor(processor)
    app.dependency_overrides[get_correction_service] = lambda: CorrectionService(processor)
    return TestClient(app), repository


def test_process_invoice_endpoint_returns_numeric_xero_payload_values():
    client, _ = _client()
    try:
        with _pdf("clean_under_1000") as file_tuple:
            response = client.post("/invoices/process", files={"file": file_tuple})

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        line = payload["xero_payload"]["LineItems"][0]
        assert isinstance(line["Quantity"], (int, float))
        assert isinstance(line["UnitAmount"], (int, float))
        assert isinstance(line["LineAmount"], (int, float))
        assert not isinstance(line["UnitAmount"], str)
    finally:
        app.dependency_overrides.clear()


def test_batch_get_invoice_get_batch_and_correction_endpoints():
    client, _ = _client()
    try:
        with _pdf("clean_over_1000") as ready_file, _pdf("invalid_abn") as review_file:
            response = client.post(
                "/batches/process",
                files=[
                    ("files", ready_file),
                    ("files", review_file),
                ],
            )

        assert response.status_code == 200
        batch = response.json()
        assert batch["uploaded"] == 2
        assert batch["ready"] == 1
        assert batch["needs_review"] == 1
        assert batch["failed"] == 0

        get_batch = client.get(f"/batches/{batch['batch_id']}")
        assert get_batch.status_code == 200
        assert get_batch.json()["batch_id"] == batch["batch_id"]

        review_invoice = next(item for item in batch["results"] if item["status"] == "needs_review")
        get_invoice = client.get(f"/invoices/{review_invoice['document_id']}")
        assert get_invoice.status_code == 200
        assert get_invoice.json()["xero_payload"] is None

        correction = client.patch(
            f"/invoices/{review_invoice['document_id']}/corrections",
            json={"field": "supplier_abn", "value": "51 824 753 556"},
        )
        assert correction.status_code == 200
        corrected = correction.json()
        assert corrected["status"] == "ready"
        assert corrected["extraction"]["field_sources"]["supplier_abn"] == "user_correction"
        assert corrected["xero_payload"]["Type"] == "ACCPAY"
    finally:
        app.dependency_overrides.clear()


def test_demo_reset_endpoint_clears_duplicate_state_without_dev_gate():
    client, _ = _client()
    try:
        with _pdf("duplicate_a") as first_file:
            first = client.post("/invoices/process", files={"file": first_file}).json()
        with _pdf("duplicate_b") as second_file:
            second = client.post("/invoices/process", files={"file": second_file}).json()

        assert first["status"] == "ready"
        assert second["status"] == "needs_review"
        assert "DUPLICATE_INVOICE" in {
            issue["code"] for issue in second["validation"]["issues"]
        }

        reset = client.post("/demo/reset")
        assert reset.status_code == 200
        assert reset.json() == {"status": "reset"}

        with _pdf("duplicate_b") as after_reset_file:
            after_reset = client.post(
                "/invoices/process",
                files={"file": after_reset_file},
            ).json()
        assert after_reset["status"] == "ready"
    finally:
        app.dependency_overrides.clear()
