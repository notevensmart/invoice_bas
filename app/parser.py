from langchain_ollama import OllamaLLM

class InvoiceParser:
    def __init__(self, model: str = "mistral"):
        self.llm = OllamaLLM(model=model)

    def parse_invoice(self, text: str) -> dict:
        prompt = (
            "Extract the supplier name, ABN, date, total, and GST from the following text.\n"
            "Return a valid JSON object.\n\n"
            f"Invoice:\n{text}"
        )
        response = self.llm.invoke(prompt)
        return {"raw_response": response}