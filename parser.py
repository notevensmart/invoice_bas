from openai import OpenAI

class InvoiceParser:
    def __init__(self, model: str = "gpt-4-turbo"):
        self.client = OpenAI()
        self.model = model

    def parse_invoice(self, text: str) -> dict:
        prompt = f"Extract supplier name, ABN, date, total, and GST from this invoice text:\n{text}\nReturn JSON."
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        content = response.choices[0].message.content
        try:
            return eval(content) if isinstance(content, str) else content
        except Exception:
            return {"raw_output": content}
