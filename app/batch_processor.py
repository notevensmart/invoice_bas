# app/batch_processor.py
import asyncio
from fastapi import UploadFile
from fastapi.responses import JSONResponse
from app.ocr import OCRService
from app.core_tools import parse_invoice, validate_invoice, calculate_bas
from app.agent import ChatBASAgent
import sys


ocr_service = OCRService()
chat_agent = ChatBASAgent()


def process_batch_invoices_sync(files: list[UploadFile]):
    """
    Sequential (non-async) version for debugging.
    Properly reads and closes each uploaded file.
    """
    numeric_results = []
    total_collected = total_paid = 0.0

    for file in files:
        print(f"🔍 Processing: {file.filename}")
       

        # ✅ Safe read and close
        with file.file as f:
            content = f.read()

        text = ocr_service.extract_text(content)
        
       

        parsed = parse_invoice(text)
        validated = validate_invoice(parsed)
        result = calculate_bas([validated])


        numeric_results.append(result)
        total_collected += result.get("gst_collected", 0)
        total_paid += result.get("gst_paid", 0)

    net_liability = total_collected - total_paid
    num_invoices = len(numeric_results)

    aggregate = {
        "gst_collected": round(total_collected, 2),
        "gst_paid": round(total_paid, 2),
        "net_liability": round(net_liability, 2),
        "invoice_count": num_invoices,
    }

    summary_text = (
        f"📦 **Batch Summary**\n"
        f"- Invoices Processed: {num_invoices}\n"
        f"- GST Collected: ${aggregate['gst_collected']:.2f}\n"
        f"- GST Paid: ${aggregate['gst_paid']:.2f}\n"
        f"- Net BAS Position: ${aggregate['net_liability']:.2f}\n\n"
    )


    return JSONResponse(
        content={
            "response": summary_text,
            "aggregate_summary": aggregate,
            "batch_results": numeric_results,
        },
        status_code=200,
    )

   
