from decimal import Decimal

class BASCalculator:
    def __init__(self, gst_rate: float = 0.1):
        self.gst_rate = Decimal(str(gst_rate))

    def estimate_bas(self, invoices: list[dict]) -> dict:
        gst_paid = Decimal("0.00")
        gst_collected = Decimal("0.00")

        for inv in invoices:
            # Handle variations in field naming
            gst_value = inv.get("GST") or inv.get("gst") or 0
            supplier_name = inv.get("supplier_name", "").lower()

            # Convert to Decimal safely
            try:
                gst_value = Decimal(str(gst_value))
            except:
                gst_value = Decimal("0.00")

            # Heuristic: supplier invoices are purchases (GST paid)
            if any(keyword in supplier_name for keyword in ["supply", "wholesale", "milk", "roast", "vendor"]):
                gst_paid += gst_value
            else:
                gst_collected += gst_value

        net_liability = gst_collected - gst_paid

        return {
            "gst_collected": float(gst_collected),
            "gst_paid": float(gst_paid),
            "net_bas_liability": float(net_liability)
        }

