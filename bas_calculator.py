from decimal import Decimal

class BASCalculator:
    def __init__(self, gst_rate: float = 0.1):
        self.gst_rate = Decimal(str(gst_rate))

    def estimate_bas(self, invoices: list[dict]) -> dict:
        gst_paid = Decimal("0.00")
        gst_collected = Decimal("0.00")
        for inv in invoices:
            gst_collected += Decimal(str(inv.get("gst", 0)))
        net_liability = gst_collected - gst_paid
        return {
            "gst_collected": float(gst_collected),
            "gst_paid": float(gst_paid),
            "net_bas_liability": float(net_liability)
        }
