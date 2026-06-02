from __future__ import annotations

from functools import lru_cache

from app.engine.batch import BatchProcessor
from app.engine.corrections import CorrectionService
from app.engine.processor import InvoiceProcessor
from app.persistence.repositories import InvoiceRepository


@lru_cache
def get_repository() -> InvoiceRepository:
    return InvoiceRepository()


@lru_cache
def get_processor() -> InvoiceProcessor:
    return InvoiceProcessor(repository=get_repository())


@lru_cache
def get_batch_processor() -> BatchProcessor:
    return BatchProcessor(get_processor())


@lru_cache
def get_correction_service() -> CorrectionService:
    return CorrectionService(get_processor())
