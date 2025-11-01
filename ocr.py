import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader

class OCRService:
    def __init__(self, engine: str = "tesseract"):
        self.engine = engine

    def extract_text(self, file_path: str) -> str:
        try:
            reader = PdfReader(file_path)
            text = "".join([page.extract_text() or "" for page in reader.pages])
            if text.strip():
                return text
        except Exception:
            pass

        images = convert_from_path(file_path)
        text = ""
        for img in images:
            text += pytesseract.image_to_string(img)
        return text.strip()
