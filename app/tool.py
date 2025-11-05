# app/tool.py
from langchain.tools import tool
from app.ocr import OCRService
from app.parser import InvoiceParser
from app.validator import InvoiceValidator
from app.bas_calculator import BASCalculator

ocr = OCRService()
parser = InvoiceParser()
validator = InvoiceValidator()
calculator = BASCalculator()

@tool
def extract_text(file_path: str) -> str:
    """Extract text from a PDF or image invoice."""
    return ocr.extract_text(file_path)

@tool
def parse_invoice(text: str) -> dict:
    """Parse text into structured invoice data."""
    return parser.parse_invoice(text)

@tool
def validate_invoice(data: dict) -> dict:
    """Clean and validate parsed invoice fields."""
    return validator.validate_fields(data)

@tool
def calculate_bas(invoices: list[dict]) -> dict:
    """Compute GST collected, paid, and net BAS position."""
    return calculator.estimate_bas(invoices)
