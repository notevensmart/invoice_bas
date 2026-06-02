from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.engine.schemas import (
    BatchResult,
    CorrectionRecord,
    DocumentMetadata,
    InvoiceResult,
    OCRResult,
)
from app.engine.validator import normalize_abn
from app.persistence.database import DEFAULT_DB_PATH, connect, initialize_database


def _json_value(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


class InvoiceRepository:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        with connect(self.db_path) as connection:
            initialize_database(connection)

    def save_document(
        self,
        document: DocumentMetadata,
        ocr: OCRResult | None = None,
    ) -> None:
        with connect(self.db_path) as connection:
            initialize_database(connection)
            connection.execute(
                """
                INSERT OR REPLACE INTO documents (
                    document_id, batch_id, filename, content_type, created_at,
                    ocr_status, ocr_method
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.document_id,
                    document.batch_id,
                    document.filename,
                    document.content_type,
                    document.created_at,
                    ocr.status.value if ocr else None,
                    ocr.method if ocr else None,
                ),
            )
            connection.commit()

    def save_invoice_result(self, result: InvoiceResult) -> None:
        now = datetime.now(UTC).isoformat()
        with connect(self.db_path) as connection:
            initialize_database(connection)
            connection.execute(
                """
                INSERT OR REPLACE INTO invoice_results (
                    document_id, filename, status, extraction_json, validation_json,
                    account_mapping_json, xero_payload_json, corrections_json,
                    response_text, ocr_json, result_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.document_id,
                    result.filename,
                    result.status.value,
                    result.extraction.model_dump_json() if result.extraction else None,
                    result.validation.model_dump_json(),
                    result.account_code_suggestion.model_dump_json()
                    if result.account_code_suggestion
                    else None,
                    result.xero_payload.model_dump_json() if result.xero_payload else None,
                    json.dumps(
                        [record.model_dump(mode="json") for record in result.corrections],
                        default=str,
                    ),
                    result.response,
                    result.ocr.model_dump_json() if result.ocr else None,
                    result.model_dump_json(),
                    now,
                ),
            )
            connection.commit()

    def load_invoice_result(self, document_id: str) -> InvoiceResult | None:
        with connect(self.db_path) as connection:
            initialize_database(connection)
            row = connection.execute(
                "SELECT result_json FROM invoice_results WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return InvoiceResult.model_validate_json(row["result_json"])

    def save_correction(self, document_id: str, correction: CorrectionRecord) -> None:
        with connect(self.db_path) as connection:
            initialize_database(connection)
            connection.execute(
                """
                INSERT INTO corrections (
                    correction_id, document_id, field, original_value,
                    corrected_value, source, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"corr_{uuid.uuid4().hex[:12]}",
                    document_id,
                    correction.field,
                    _json_value(correction.original_value),
                    _json_value(correction.corrected_value),
                    correction.source,
                    correction.created_at,
                ),
            )
            connection.commit()

    def save_batch(self, batch: BatchResult) -> None:
        now = datetime.now(UTC).isoformat()
        with connect(self.db_path) as connection:
            initialize_database(connection)
            connection.execute(
                """
                INSERT OR REPLACE INTO batches (
                    batch_id, uploaded, ready, needs_review, failed,
                    detected_gst_total, batch_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(
                    (SELECT created_at FROM batches WHERE batch_id = ?), ?
                ), ?)
                """,
                (
                    batch.batch_id,
                    batch.uploaded,
                    batch.ready,
                    batch.needs_review,
                    batch.failed,
                    str(batch.detected_gst_total),
                    batch.model_dump_json(),
                    batch.batch_id,
                    now,
                    now,
                ),
            )
            connection.commit()

    def load_batch(self, batch_id: str) -> BatchResult | None:
        with connect(self.db_path) as connection:
            initialize_database(connection)
            row = connection.execute(
                "SELECT batch_json FROM batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
        if row is None:
            return None
        return BatchResult.model_validate_json(row["batch_json"])

    def invoice_key_exists(
        self,
        supplier_abn: str,
        invoice_number: str,
        exclude_document_id: str | None = None,
    ) -> bool:
        clean_abn = normalize_abn(supplier_abn)
        if not clean_abn or not invoice_number:
            return False
        with connect(self.db_path) as connection:
            initialize_database(connection)
            rows = connection.execute("SELECT result_json FROM invoice_results").fetchall()
        for row in rows:
            result = InvoiceResult.model_validate_json(row["result_json"])
            if exclude_document_id and result.document_id == exclude_document_id:
                continue
            extraction = result.extraction
            if extraction is None:
                continue
            if (
                normalize_abn(extraction.supplier_abn) == clean_abn
                and (extraction.invoice_number or "").lower() == invoice_number.lower()
            ):
                return True
        return False

    def reset_demo_data(self) -> None:
        with connect(self.db_path) as connection:
            initialize_database(connection)
            connection.execute("DELETE FROM corrections")
            connection.execute("DELETE FROM invoice_results")
            connection.execute("DELETE FROM documents")
            connection.execute("DELETE FROM batches")
            connection.commit()


class InMemoryInvoiceRepository:
    def __init__(self):
        self.documents: dict[str, DocumentMetadata] = {}
        self.results: dict[str, InvoiceResult] = {}
        self.batches: dict[str, BatchResult] = {}
        self.corrections: list[tuple[str, CorrectionRecord]] = []

    def save_document(self, document: DocumentMetadata, ocr: OCRResult | None = None) -> None:
        self.documents[document.document_id] = document

    def save_invoice_result(self, result: InvoiceResult) -> None:
        self.results[result.document_id] = result

    def load_invoice_result(self, document_id: str) -> InvoiceResult | None:
        return self.results.get(document_id)

    def save_correction(self, document_id: str, correction: CorrectionRecord) -> None:
        self.corrections.append((document_id, correction))

    def save_batch(self, batch: BatchResult) -> None:
        self.batches[batch.batch_id] = batch

    def load_batch(self, batch_id: str) -> BatchResult | None:
        return self.batches.get(batch_id)

    def invoice_key_exists(
        self,
        supplier_abn: str,
        invoice_number: str,
        exclude_document_id: str | None = None,
    ) -> bool:
        clean_abn = normalize_abn(supplier_abn)
        for document_id, result in self.results.items():
            if exclude_document_id and document_id == exclude_document_id:
                continue
            extraction = result.extraction
            if extraction is None:
                continue
            if (
                normalize_abn(extraction.supplier_abn) == clean_abn
                and (extraction.invoice_number or "").lower() == invoice_number.lower()
            ):
                return True
        return False

    def reset_demo_data(self) -> None:
        self.documents.clear()
        self.results.clear()
        self.batches.clear()
        self.corrections.clear()
