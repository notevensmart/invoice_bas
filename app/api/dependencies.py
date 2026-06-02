from __future__ import annotations

import os
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


def get_demo_reset_enabled() -> bool:
    reset_enabled = os.getenv("INVOICE_DEMO_RESET_ENABLED", "").lower()
    app_env = os.getenv("APP_ENV", "").lower()
    return reset_enabled in {"1", "true", "yes"} or app_env in {
        "development",
        "dev",
        "local",
        "test",
    }
