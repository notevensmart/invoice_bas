from decimal import Decimal

class BASCalculator:
    def __init__(self, gst_rate: float = 0.1):
        self.gst_rate = Decimal(str(gst_rate))

    from decimal import Decimal

    def estimate_bas(self, invoices: list[dict]) -> dict:
        """
        Estimate BAS figures (GST collected vs paid) based on parsed invoice data.

        Heuristics:
        - Uses known keywords in supplier names to classify purchases (GST paid)
        - If 'bill_to' or buyer fields indicate the business itself, marks as GST paid
        - Otherwise assumes it's a sales invoice (GST collected)
        """

        gst_paid = Decimal("0.00")
        gst_collected = Decimal("0.00")

        # Common supplier-side keywords for café, retail, hospitality
        VENDOR_KEYWORDS = [
            "supply", "wholesale", "milk", "roast", "vendor", "packaging", "equipment",
            "service", "cleaning", "produce", "bakery", "distribution", "logistics",
            "food", "dairy", "beans", "beverage"
        ]

        for inv in invoices:
            # --- Extract GST value safely ---
            gst_value = inv.get("gst") or inv.get("GST") or 0
            try:
                gst_str = str(gst_value).replace("$", "").strip()
                gst_value = Decimal(gst_str)
            except Exception:
                gst_value = Decimal("0.00")

            # --- Extract supplier/buyer info ---
            supplier_name = str(inv.get("supplier") or inv.get("supplier_name") or "").lower()
            bill_to = str(inv.get("bill_to") or inv.get("buyer") or "").lower()

            # --- Classification rules ---
            # 1️⃣ If bill_to clearly refers to the business itself → GST paid
            if any(k in bill_to for k in ["luna café", "luna cafe", "my business", "our company"]):
                gst_paid += gst_value

            # 2️⃣ If supplier name matches vendor patterns → GST paid
            elif any(k in supplier_name for k in VENDOR_KEYWORDS):
                gst_paid += gst_value

            # 3️⃣ Otherwise treat as sales invoice → GST collected
            else:
                gst_collected += gst_value

        # --- Compute net liability ---
        net_liability = gst_collected - gst_paid

        return {
            "gst_collected": float(gst_collected),
            "gst_paid": float(gst_paid),
            "net_liability": float(net_liability)
        }

