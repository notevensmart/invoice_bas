# app/batch_processor.py
import asyncio
from fastapi import UploadFile
from fastapi.responses import JSONResponse
from app.ocr import OCRService
from app.core_tools import parse_invoice, validate_invoice, calculate_bas
from app.agent import ChatBASAgent
import logging 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ocr_service = OCRService()
chat_agent = ChatBASAgent()


async def process_batch_invoices(files: list[UploadFile]):
    """
    Deterministic batch processor for multiple invoices.
    - Extracts text from each invoice
    - Parses, validates, and calculates numeric GST data
    - Aggregates totals
    - Generates final LLM summary (once)
    """

    async def handle_file(file: UploadFile):
        try:
            content = await file.read()
            text = await asyncio.to_thread(ocr_service.extract_text, content)
            parsed = parse_invoice(text)
            validated = validate_invoice(parsed)
            result = calculate_bas([validated])
            logger.info(f"DEBUG-INVOICE parsed: {parsed}")
            logger.info(f"DEBUG-INVOICE validated: {validated}")
            logger.info(f"DEBUG-INVOICE result: {result}")
            return result
        except Exception as e:
            # Safe fallback: return zeros if any invoice fails
            return {"gst_collected": 0, "gst_paid": 0, "net_liability": 0, "error": str(e)}

    # -------------------------
    # Process all invoices concurrently
    # -------------------------
    numeric_results = await asyncio.gather(*(handle_file(f) for f in files))

    # -------------------------
    # Aggregate numeric results
    # -------------------------
    total_collected = sum(r.get("gst_collected", 0) for r in numeric_results)
    total_paid = sum(r.get("gst_paid", 0) for r in numeric_results)
    net_liability = total_collected - total_paid
    num_invoices = len(numeric_results)

    aggregate = {
        "gst_collected": round(total_collected, 2),
        "gst_paid": round(total_paid, 2),
        "net_liability": round(net_liability, 2),
        "invoice_count": num_invoices,
    }

    # -------------------------
    # Build clean batch summary
    # -------------------------
    position_text = (
        "You'll likely owe GST this period."
        if net_liability > 0
        else "You're due a GST refund this period."
        if net_liability < 0
        else "Your GST collected and paid are balanced this period."
    )

    summary_text = (
        f"📦 **Batch Summary**\n"
        f"- Invoices Processed: {num_invoices}\n"
        f"- GST Collected: ${aggregate['gst_collected']:.2f}\n"
        f"- GST Paid: ${aggregate['gst_paid']:.2f}\n"
        f"- Net BAS Position: ${aggregate['net_liability']:.2f}\n\n"
        f"💬 {position_text}\n\n"
        "Would you like me to compare suppliers or forecast the next BAS?"
    )

    # -------------------------
    # Feed into agent for reasoning / memory
    # -------------------------
    memory_prompt = (
        f"Remember this batch BAS summary for context:\n\n"
        f"{summary_text}\n\n"
        "This represents the most recent batch of invoices processed."
    )
    agent_result = chat_agent.run(memory_prompt, mode="chat")

    # -------------------------
    # Return unified response
    # -------------------------
    return JSONResponse(
        content={
            "response": summary_text,
            "aggregate_summary": aggregate,
            "batch_results": numeric_results,
            "agent_memory_ack": agent_result["response"],
        },
        status_code=200,
    )
