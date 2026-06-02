from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


MONEY_QUANT = Decimal("0.01")


def coerce_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value.quantize(MONEY_QUANT)
    if isinstance(value, (int, float)):
        return Decimal(str(value)).quantize(MONEY_QUANT)
    if isinstance(value, str):
        cleaned = (
            value.replace("$", "")
            .replace(",", "")
            .replace("AUD", "")
            .replace("aud", "")
            .strip()
        )
        if cleaned == "":
            return None
        try:
            return Decimal(cleaned).quantize(MONEY_QUANT)
        except InvalidOperation:
            return None
    try:
        return Decimal(str(value)).quantize(MONEY_QUANT)
    except (InvalidOperation, ValueError):
        return None


def decimal_json(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(MONEY_QUANT), "f")


class EngineModel(BaseModel):
    model_config = ConfigDict(
        validate_assignment=True,
        arbitrary_types_allowed=False,
    )


class InvoiceStatus(str, Enum):
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class ExtractionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class ParserStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DocumentMetadata(EngineModel):
    document_id: str
    filename: str
    content_type: str
    batch_id: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class OCRResult(EngineModel):
    document_id: str
    text: str = ""
    method: str = "none"
    status: ExtractionStatus = ExtractionStatus.FAILED
    warnings: list[str] = Field(default_factory=list)


class LineItem(EngineModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    gst_amount: Decimal | None = None
    tax_treatment: str | None = None
    source: str = "parser"

    @field_validator("quantity", "unit_price", "amount", "gst_amount", mode="before")
    @classmethod
    def parse_decimal(cls, value: Any) -> Decimal | None:
        return coerce_decimal(value)


class InvoiceExtraction(EngineModel):
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
    line_items: list[LineItem] = Field(default_factory=list)
    line_items_source: str = "parser"
    field_sources: dict[str, str] = Field(default_factory=dict)
    original_extracted_values: dict[str, Any] = Field(default_factory=dict)
    abn_lookup_status: str | None = None
    gst_registration_status: str | None = None

    @field_validator("subtotal", "gst", "total", mode="before")
    @classmethod
    def parse_money(cls, value: Any) -> Decimal | None:
        return coerce_decimal(value)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: Any) -> str:
        if not value:
            return "AUD"
        return str(value).strip().upper()


class ParserResult(EngineModel):
    status: ParserStatus
    extraction: InvoiceExtraction | None = None
    raw_output: str | None = None
    attempts: int = 0
    errors: list[str] = Field(default_factory=list)


class ValidationIssue(EngineModel):
    code: str
    severity: ValidationSeverity | str
    field: str | None = None
    message: str
    suggested_action: str | None = None


class ValidationResult(EngineModel):
    status: InvoiceStatus
    issues: list[ValidationIssue] = Field(default_factory=list)


class CorrectionRecord(EngineModel):
    field: str
    original_value: Any | None = None
    corrected_value: Any | None = None
    source: str = "user_correction"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class CorrectionUpdate(EngineModel):
    field: str
    value: Any | None = None


class CorrectionRequest(EngineModel):
    field: str | None = None
    value: Any | None = None
    updates: list[CorrectionUpdate] | None = None

    def normalized_updates(self) -> list[CorrectionUpdate]:
        if self.updates is not None:
            return self.updates
        if self.field is None:
            return []
        return [CorrectionUpdate(field=self.field, value=self.value)]


class AccountCodeSuggestion(EngineModel):
    suggested_account_code: str | None = None
    suggested_account_name: str | None = None
    confidence: str
    reason: str
    status: str


class XeroDraftBillPayload(EngineModel):
    Type: str = "ACCPAY"
    Status: str = "DRAFT"
    Contact: dict[str, Any]
    InvoiceNumber: str
    Date: str
    DueDate: str | None = None
    LineAmountTypes: str = "Exclusive"
    LineItems: list[dict[str, Any]]


class InvoiceResult(EngineModel):
    document_id: str
    filename: str
    status: InvoiceStatus
    extraction: InvoiceExtraction | None = None
    validation: ValidationResult
    account_code_suggestion: AccountCodeSuggestion | None = None
    xero_payload: XeroDraftBillPayload | None = None
    corrections: list[CorrectionRecord] = Field(default_factory=list)
    response: str | None = None
    ocr: OCRResult | None = None


class BatchResult(EngineModel):
    batch_id: str
    uploaded: int
    ready: int
    needs_review: int
    failed: int
    detected_gst_total: Decimal = Decimal("0.00")
    results: list[InvoiceResult] = Field(default_factory=list)

    @field_validator("detected_gst_total", mode="before")
    @classmethod
    def parse_detected_gst_total(cls, value: Any) -> Decimal:
        return coerce_decimal(value) or Decimal("0.00")
