from app.ocr import OCRService
from app.parser import InvoiceParser
from app.validator import InvoiceValidator
from app.bas_calculator import BASCalculator

# app/core_tools.py


# Instantiate once
_ocr = OCRService()
_parser = InvoiceParser()
_validator = InvoiceValidator()
_bas = BASCalculator()

# Expose bound methods as functions
def extract_text(file_path: str) -> str:
    """Extract text from a local PDF or image file."""
    return _ocr.extract_text(file_path)

def parse_invoice(input: str) -> dict:
    """Parse invoice fields from raw text."""
    return _parser.parse_invoice(input)

def validate_invoice(data: dict) -> dict:
    """Validate extracted invoice fields and ABN."""
    return _validator.validate_fields(data)

def calculate_bas(invoices: list[dict]) -> dict:
    """Compute GST/BAS summary from validated invoices."""
    return _bas.estimate_bas(invoices)

# Registry of tools
TOOLS = {
    "extract_text": extract_text,
    "parse_invoice": parse_invoice,
    "validate_invoice": validate_invoice,
    "calculate_bas": calculate_bas,
}
