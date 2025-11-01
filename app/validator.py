import re
from decimal import Decimal

class InvoiceValidator:
    def validate_abn(self, abn: str) -> bool:
        clean = re.sub(r"\s+", "", abn)
        if not re.match(r"^\d{11}$", clean):
            return False
        weights = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
        digits = [int(d) for d in clean]
        digits[0] -= 1
        return sum(w * d for w, d in zip(weights, digits)) % 89 == 0

    def validate_fields(self, data: dict) -> dict:
        total = Decimal(data.get("total", 0))
        gst = Decimal(data.get("gst", 0))
        if gst > total:
            data["warning"] = "GST exceeds total"
        if "abn" in data and not self.validate_abn(data["abn"]):
            data["warning"] = "Invalid ABN"
        return data
