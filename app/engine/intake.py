from __future__ import annotations

import uuid

from app.engine.schemas import DocumentMetadata


class UnsupportedDocumentError(ValueError):
    pass


def new_document_id() -> str:
    return f"doc_{uuid.uuid4().hex[:12]}"


def new_batch_id() -> str:
    return f"batch_{uuid.uuid4().hex[:12]}"


def create_document(
    filename: str,
    content_type: str | None,
    batch_id: str | None = None,
) -> DocumentMetadata:
    content_type = content_type or "application/octet-stream"
    lowered = filename.lower()
    is_pdf = lowered.endswith(".pdf") or content_type in {
        "application/pdf",
        "application/x-pdf",
    }
    if not is_pdf:
        raise UnsupportedDocumentError("Only PDF invoice uploads are supported in this POC.")
    return DocumentMetadata(
        document_id=new_document_id(),
        filename=filename,
        content_type="application/pdf",
        batch_id=batch_id,
    )
