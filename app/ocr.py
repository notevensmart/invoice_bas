from io import BytesIO
from PyPDF2 import PdfReader
from pdf2image import convert_from_bytes, convert_from_path
import pytesseract

class OCRService:
    def __init__(self, engine: str = "tesseract"):
        self.engine = engine

    def extract_text(self, file_input) -> str:
        """
        Accepts either a file path (str) or a bytes-like object.
        Extracts text from PDF first, then falls back to OCR if needed.
        """
        text = ""

        # Handle bytes input
        if isinstance(file_input, (bytes, bytearray)):
            file_bytes = BytesIO(file_input)
            try:
                reader = PdfReader(file_bytes)
                text = "".join([page.extract_text() or "" for page in reader.pages])
                if text.strip():
                    return text
            except Exception:
                pass  # not a pure text PDF, try OCR instead

            # Fallback to OCR on each page image
            try:
                images = convert_from_bytes(file_input)
                text = ""
                for img in images:
                    text += pytesseract.image_to_string(img)
                return text.strip()
            except Exception as e:
                print("❌ OCRService error:", e)
                return ""
        else:
            # Assume it's a file path
            try:
                reader = PdfReader(file_input)
                text = "".join([page.extract_text() or "" for page in reader.pages])
                if text.strip():
                    return text
            except Exception:
                pass

            # Fallback to OCR from path
            images = convert_from_path(file_input)
            text = ""
            for img in images:
                text += pytesseract.image_to_string(img)
            return text.strip()

