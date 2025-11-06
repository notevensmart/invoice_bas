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


# Required for Vercel / Railway handlers
handler = app