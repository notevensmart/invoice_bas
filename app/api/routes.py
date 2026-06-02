from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.dependencies import (
    get_batch_processor,
    get_correction_service,
    get_demo_reset_enabled,
    get_processor,
    get_repository,
)
from app.engine.batch import BatchProcessor
from app.engine.corrections import CorrectionService
from app.engine.parser import InvoiceParser
from app.engine.processor import InvoiceProcessor
from app.engine.schemas import BatchResult, CorrectionRequest, InvoiceResult
from app.persistence.repositories import InvoiceRepository


router = APIRouter()


@router.get("/system/status")
async def system_status() -> dict[str, object]:
    parser = InvoiceParser()
    return {
        "status": "ok",
        "llm_enabled": parser.use_llm,
        "parser_mode": "llm" if parser.use_llm else "deterministic",
    }


@router.post("/invoices/process", response_model=InvoiceResult)
async def process_invoice(
    file: UploadFile = File(...),
    processor: InvoiceProcessor = Depends(get_processor),
) -> InvoiceResult:
    content = await file.read()
    return processor.process_pdf(file.filename or "invoice.pdf", file.content_type, content)


@router.post("/batches/process", response_model=BatchResult)
async def process_batch(
    files: list[UploadFile] = File(...),
    batch_processor: BatchProcessor = Depends(get_batch_processor),
) -> BatchResult:
    file_specs = []
    for file in files:
        file_specs.append(
            (
                file.filename or "invoice.pdf",
                file.content_type,
                await file.read(),
            )
        )
    return batch_processor.process_pdfs(file_specs)


@router.patch("/invoices/{document_id}/corrections", response_model=InvoiceResult)
async def apply_correction(
    document_id: str,
    request: CorrectionRequest,
    correction_service: CorrectionService = Depends(get_correction_service),
) -> InvoiceResult:
    try:
        return correction_service.apply(document_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/invoices/{document_id}", response_model=InvoiceResult)
async def get_invoice(
    document_id: str,
    repository: InvoiceRepository = Depends(get_repository),
) -> InvoiceResult:
    result = repository.load_invoice_result(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Invoice {document_id} was not found.")
    return result


@router.get("/batches/{batch_id}", response_model=BatchResult)
async def get_batch(
    batch_id: str,
    repository: InvoiceRepository = Depends(get_repository),
) -> BatchResult:
    batch = repository.load_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} was not found.")
    return batch


@router.post("/demo/reset")
async def reset_demo_data(
    enabled: bool = Depends(get_demo_reset_enabled),
    repository: InvoiceRepository = Depends(get_repository),
) -> dict[str, str]:
    if not enabled:
        raise HTTPException(
            status_code=403,
            detail="Demo data reset is only available in development mode.",
        )
    repository.reset_demo_data()
    return {"status": "reset"}
