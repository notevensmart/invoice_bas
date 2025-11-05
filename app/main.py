from fastapi import FastAPI, UploadFile, File, Form
import asyncio
from fastapi.middleware.cors import CORSMiddleware
from app.ocr import OCRService
from app.agent import ChatBASAgent
from fastapi.responses import JSONResponse

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
    """Chat with the BAS agent; optional invoice file upload."""
    text = message
    if file:
        content = await file.read()  
        extracted = await asyncio.to_thread(ocr_service.extract_text, content)
        text += "\n\n" + extracted

    result = chat_agent.run(text)
    return JSONResponse(content=result, status_code=200)

handler = app