from fastapi import FastAPI, UploadFile, File, Form
import asyncio
from app.ocr import OCRService
from app.agent import ChatBASAgent

app = FastAPI(title="Smart BAS Conversational Agent")
ocr_service = OCRService()
chat_agent = ChatBASAgent()

@app.post("/chat/")
async def chat_with_bas_agent(
    message: str = Form(...),
    file: UploadFile = File(None)):
    """Chat with the BAS agent; optional invoice file upload."""
    text = message
    if file:
        extracted = await asyncio.to_thread(ocr_service.extract_text, file.file)
        text += "\n\n" + extracted
    result = chat_agent.run(text)
    return result