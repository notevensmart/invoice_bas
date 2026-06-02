from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.engine.parser import InvoiceParser
from app.engine.processor import InvoiceProcessor
from app.persistence.repositories import InMemoryInvoiceRepository


FIXTURE_ROOT = Path(__file__).parent / "fixtures"
OCR_TEXT_ROOT = FIXTURE_ROOT / "ocr_text"
EXPECTED_PATH = FIXTURE_ROOT / "expected" / "invoice_cases.json"


def load_text(name: str) -> str:
    return (OCR_TEXT_ROOT / f"{name}.txt").read_text(encoding="utf-8")


@pytest.fixture
def expected_cases() -> dict:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def parser() -> InvoiceParser:
    return InvoiceParser(use_llm=False)


@pytest.fixture
def processor() -> InvoiceProcessor:
    return InvoiceProcessor(
        repository=InMemoryInvoiceRepository(),
        parser=InvoiceParser(use_llm=False),
    )


@pytest.fixture
def text_loader():
    return load_text


def issue_codes(result) -> set[str]:
    return {issue.code for issue in result.validation.issues}
