from fastapi import FastAPI, UploadFile, File, Form
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from app.ocr import OCRService
from app.agent import ChatBASAgent
from fastapi.responses import JSONResponse
from typing import List

app = FastAPI(title="Smart BAS Conversational Agent")
ocr_service = OCRService()
chat_agent = ChatBASAgent()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.post("/chat")
async def chat_with_bas_agent(
    message: str = Form(...),
    file: UploadFile = File(None)
):
    """
    Chat with the BAS agent.
    - If a file is uploaded, runs invoice reasoning (graph mode).
    - Otherwise, handles conversational Q&A (chat mode).
    """
    try:
        mode = "chat"   # default: conversational
        text = message.strip()

        # --- Invoice reasoning if file uploaded ---
        if file:
            content = await file.read()
            extracted = await asyncio.to_thread(ocr_service.extract_text, content)
            text += f"\n\n{extracted.strip()}"
            mode = "invoice"

        # --- Run the agent with correct mode ---
        result = chat_agent.run(text, mode=mode)

        # --- Wrap for response ---
        return JSONResponse(content=result, status_code=200)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={"error": str(e)},
            status_code=500,
        )
@app.post("/process-batch")
async def process_batch(
    files: List[UploadFile] = File(...),
):
    """
    Accept multiple invoices, process them concurrently, and return
    both individual results and an aggregated BAS summary.
    """
    try:
        async def handle_file(file: UploadFile):
            content = await file.read()
            extracted = await asyncio.to_thread(ocr_service.extract_text, content)
            result = chat_agent.run(extracted, mode="invoice")
            return result

        # Run all OCR + agent calls concurrently
        results = await asyncio.gather(*(handle_file(f) for f in files))

        # -------------------------
        # Aggregate BAS summaries
        # -------------------------
        total_collected = total_paid = 0.0
        for r in results:
            out = r.get("response", "")
            # crude parse: you could adapt your calculate_bas logic instead
            # safer option: modify ChatBASAgent to return structured JSON too
            try:
                if "GST Collected:" in out and "GST Paid:" in out:
                    lines = out.splitlines()
                    for line in lines:
                        if "GST Collected" in line:
                            total_collected += float(line.split("$")[-1].replace(",", "").strip())
                        if "GST Paid" in line:
                            total_paid += float(line.split("$")[-1].replace(",", "").strip())
            except Exception:
                pass

        net_liability = total_collected - total_paid

        aggregate = {
            "gst_collected": round(total_collected, 2),
            "gst_paid": round(total_paid, 2),
            "net_liability": round(net_liability, 2),
        }




        summary_text = (
            f"📦 **Batch Summary**\n"
            f"- GST Collected: ${aggregate['gst_collected']:.2f}\n"
            f"- GST Paid: ${aggregate['gst_paid']:.2f}\n"
            f"- Net BAS Position: ${aggregate['net_liability']:.2f}\n\n"
            
)
        memory_prompt = (
            f"Remember this batch BAS summary for context:\n\n"
            f"{summary_text}\n\n"
            "This represents the most recent batch of invoices processed."
        )

        # Run in 'chat' mode so it uses conversational memory
        agent_result = chat_agent.run(memory_prompt, mode="chat")

        # Optionally append manually too (for explicit logging)
        chat_agent.history.append(
            ("system", f"Stored batch summary: {summary_text}")
        )

        return JSONResponse(
            content={
                "response": summary_text,   # 👈 keeps frontend behavior consistent
                "aggregate_summary": aggregate,
                "batch_results": results
            },
            status_code=200
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)

# Required for Vercel / Railway handlers
handler = app