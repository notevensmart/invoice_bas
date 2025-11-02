# app/main.py
from fastapi import FastAPI, UploadFile, File, Depends
from functools import lru_cache
from app.agent import create_simpleagent
from app.ocr import OCRService
from app.parser import InvoiceParser
from app.validator import InvoiceValidator
from app.bas_calculator import BASCalculator
import asyncio


app = FastAPI(title="Smart Invoice Inbox + BAS Estimator")
ocr_service = OCRService()
parser_service = InvoiceParser(model="mistral")
validator_service = InvoiceValidator()
bas_calculator = BASCalculator()
@lru_cache
def get_agent():
    """Singleton agent instance for reuse across requests."""
    return create_simpleagent()

@app.get("/")
async def root():
    return {"message": "Smart Invoice Inbox + BAS Estimator API running."}

@app.post("/run_agent/")
async def run_agent(file: UploadFile = File(...), agent=Depends(get_agent)):
    """
    Upload an invoice PDF or image. The system extracts text, runs the LangGraph agent,
    and returns structured invoice + BAS summary as JSON.
    """
    # Step 1: Extract text from the uploaded file (non-blocking)
    text = await asyncio.to_thread(ocr_service.extract_text, file.file)

    # Safety check
    if not text or text.strip() == "":
        return {"error": "OCR failed — could not extract text from file."}

    # Step 2: Run the structured agent pipeline
    result = agent.invoke({"input": text})

    # Step 3: Return structured output
    return {
        "filename": file.filename,
        "invoice_text_preview": text[:500],
        "parsed": result.get("parsed"),
        "validated": result.get("validated"), 
          # optional preview
        "agent_output": result.get("output")
    }
    
@app.post("/process_invoice/")
async def process_invoice(file: UploadFile = File(...)):
    """Extract, parse, validate, and compute BAS summary for an uploaded invoice."""
    # Offload OCR to threadpool to avoid blocking event loop
    text = await asyncio.to_thread(ocr_service.extract_text, file.file)
    parsed_data = parser_service.parse_invoice(text)
    validated_data = validator_service.validate_fields(parsed_data)
    bas_summary = bas_calculator.estimate_bas([validated_data])

    return {
        "invoice_data": validated_data,
        "bas_summary": bas_summary,
    }