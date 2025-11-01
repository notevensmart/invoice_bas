from fastapi import FastAPI, UploadFile
from app.ocr import OCRService
from app.parser import InvoiceParser
from app.validator import InvoiceValidator
from app.bas_calculator import BASCalculator

app = FastAPI(title="Smart Invoice Inbox + BAS Estimator")

ocr_service = OCRService()
parser_service = InvoiceParser(model="gpt-4")
validator_service = InvoiceValidator()
bas_calculator = BASCalculator()

@app.post("/process_invoice/")
async def process_invoice(file: UploadFile):
    text = ocr_service.extract_text(file.file)
    parsed_data = parser_service.parse_invoice(text)
    validated_data = validator_service.validate_fields(parsed_data)
    bas_summary = bas_calculator.estimate_bas([validated_data])
    return {"invoice_data": validated_data, "bas_summary": bas_summary}
