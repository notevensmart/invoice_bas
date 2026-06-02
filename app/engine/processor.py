from __future__ import annotations

from app.agent.responder import InvoiceResponder
from app.engine.account_mapping import AccountCodeMapper
from app.engine.intake import UnsupportedDocumentError, create_document, new_document_id
from app.engine.ocr import PDFTextExtractor
from app.engine.parser import InvoiceParser
from app.engine.schemas import (
    DocumentMetadata,
    ExtractionStatus,
    InvoiceExtraction,
    InvoiceResult,
    InvoiceStatus,
    OCRResult,
    ParserStatus,
)
from app.engine.validator import InvoiceValidator
from app.engine.xero_payload import XeroPayloadBuilder
from app.persistence.repositories import InvoiceRepository


class InvoiceProcessor:
    def __init__(
        self,
        repository: InvoiceRepository | None = None,
        ocr: PDFTextExtractor | None = None,
        parser: InvoiceParser | None = None,
        validator: InvoiceValidator | None = None,
        mapper: AccountCodeMapper | None = None,
        payload_builder: XeroPayloadBuilder | None = None,
        responder: InvoiceResponder | None = None,
    ):
        self.repository = repository or InvoiceRepository()
        self.ocr = ocr or PDFTextExtractor()
        self.parser = parser or InvoiceParser()
        self.validator = validator or InvoiceValidator()
        self.mapper = mapper or AccountCodeMapper()
        self.payload_builder = payload_builder or XeroPayloadBuilder()
        self.responder = responder or InvoiceResponder()

    def process_pdf(
        self,
        filename: str,
        content_type: str | None,
        file_bytes: bytes,
        batch_id: str | None = None,
    ) -> InvoiceResult:
        try:
            document = create_document(filename, content_type, batch_id)
        except UnsupportedDocumentError as exc:
            return self._failure_result(
                document_id=new_document_id(),
                filename=filename,
                code="UNSUPPORTED_FILE_TYPE",
                message=str(exc),
            )

        ocr_result = self.ocr.extract(file_bytes, document.document_id)
        self.repository.save_document(document, ocr_result)
        if ocr_result.status == ExtractionStatus.FAILED or not ocr_result.text.strip():
            result = self._failure_result(
                document_id=document.document_id,
                filename=document.filename,
                code="OCR_EMPTY_TEXT",
                message="No text could be extracted from the PDF.",
                ocr=ocr_result,
            )
            self.repository.save_invoice_result(result)
            return result

        return self._process_text(document, ocr_result)

    def process_text(
        self,
        filename: str,
        text: str,
        batch_id: str | None = None,
    ) -> InvoiceResult:
        document = create_document(filename, "application/pdf", batch_id)
        ocr_result = OCRResult(
            document_id=document.document_id,
            text=text,
            method="fixture_text",
            status=ExtractionStatus.SUCCESS,
        )
        self.repository.save_document(document, ocr_result)
        return self._process_text(document, ocr_result)

    def rebuild_result(
        self,
        existing: InvoiceResult,
        extraction: InvoiceExtraction,
    ) -> InvoiceResult:
        validation = self.validator.validate(
            extraction,
            duplicate_checker=self.repository.invoice_key_exists,
        )
        account = existing.account_code_suggestion or self.mapper.suggest(extraction)
        if (
            account is None
            or account.status != "user_selected"
            or account.suggested_account_code in {None, "UNMAPPED"}
        ):
            account = self.mapper.suggest(extraction)
        payload = self.payload_builder.build(extraction, account, validation.status)
        result = InvoiceResult(
            document_id=existing.document_id,
            filename=existing.filename,
            status=validation.status,
            extraction=extraction,
            validation=validation,
            account_code_suggestion=account,
            xero_payload=payload,
            corrections=existing.corrections,
            ocr=existing.ocr,
        )
        result.response = self.responder.render(result)
        self.repository.save_invoice_result(result)
        return result

    def _process_text(self, document: DocumentMetadata, ocr_result: OCRResult) -> InvoiceResult:
        parser_result = self.parser.parse(ocr_result.text, document.document_id)
        if parser_result.status == ParserStatus.FAILED or parser_result.extraction is None:
            code = "PARSER_INVALID_JSON"
            if parser_result.errors and not any("Invalid JSON" in error for error in parser_result.errors):
                code = "PARSER_SCHEMA_INVALID"
            result = self._failure_result(
                document_id=document.document_id,
                filename=document.filename,
                code=code,
                message="Parser could not return a valid invoice schema.",
                ocr=ocr_result,
            )
            self.repository.save_invoice_result(result)
            return result

        validation = self.validator.validate(
            parser_result.extraction,
            duplicate_checker=self.repository.invoice_key_exists,
        )
        account = self.mapper.suggest(parser_result.extraction)
        payload = self.payload_builder.build(
            parser_result.extraction,
            account,
            validation.status,
        )
        result = InvoiceResult(
            document_id=document.document_id,
            filename=document.filename,
            status=validation.status,
            extraction=parser_result.extraction,
            validation=validation,
            account_code_suggestion=account,
            xero_payload=payload,
            ocr=ocr_result,
        )
        result.response = self.responder.render(result)
        self.repository.save_invoice_result(result)
        return result

    def _failure_result(
        self,
        document_id: str,
        filename: str,
        code: str,
        message: str,
        ocr: OCRResult | None = None,
    ) -> InvoiceResult:
        validation = self.validator.failure_result(code, message)
        result = InvoiceResult(
            document_id=document_id,
            filename=filename,
            status=InvoiceStatus.FAILED,
            validation=validation,
            ocr=ocr,
        )
        result.response = self.responder.render(result)
        return result
