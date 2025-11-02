import re
from decimal import Decimal
import json
class InvoiceValidator:
    def clean_currency(self, value):
        """Strip currency symbols and convert to Decimal."""
        if isinstance(value, str):
            value = re.sub(r"[^\d.\-]", "", value)
        try:
            return Decimal(value)
        except:
            return Decimal("0.00")

    def validate_abn(self, abn: str) -> bool:
        """Simple ABN checksum validation."""
        clean = re.sub(r"\s+", "", abn)
        if not re.match(r"^\d{11}$", clean):
            return False
        weights = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
        digits = [int(d) for d in clean]
        digits[0] -= 1
        return sum(w * d for w, d in zip(weights, digits)) % 89 == 0

    def validate_fields(self, data: dict) -> dict:
        """Parse raw_response JSON, normalize fields, clean currencies."""
        # Step 1. Parse raw_response if it exists
        raw = data.get("raw_response")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                data.update(parsed)  # merge extracted fields into dict
            except json.JSONDecodeError:
                pass

        # Step 2. Clean currency values
        total = self.clean_currency(data.get("total", 0))
        gst = self.clean_currency(data.get("GST", 0))

        # Step 3. Replace cleaned values back into data
        data["total"] = total
        data["GST"] = gst

        # Step 4. Run ABN and logic checks
        if gst > total:
            data["warning"] = "GST exceeds total"
        abn = data.get("ABN") or data.get("abn")
        if abn and not self.validate_abn(abn):
            data["warning"] = "Invalid ABN"

        return data
