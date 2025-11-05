from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os
import re , json
load_dotenv(".env")

class InvoiceParser:
    def __init__(self):
        self.llm = ChatGroq(
            model="llama-3.1-8b-instant",
            groq_api_key=os.getenv("GROQ_API_KEY"),
            temperature=0.1,
        )

    def parse_invoice(self, text: str):
        """Ask the LLM to return clean, valid JSON fields from invoice text."""
    
        prompt = f"""
        You are a precise invoice data extractor.
        Extract the following fields from the invoice text provided below.
        Return ONLY valid JSON, no commentary.

        Required keys:
        - supplier
        - abn
        - date
        - amount_ex_gst
        - gst
        - total

        If a field is missing, use null.

        Invoice text:
        {text}
        """

        response = self.llm.invoke(prompt)
        raw = getattr(response, "content", str(response))

        # --- Clean and ensure we only parse the JSON part ---
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            raw_json = match.group(0)
        else:
            raw_json = "{}"

        try:
            return json.loads(raw_json)
        except Exception:
            return {"raw_response": raw_json}