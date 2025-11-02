# app/agent.py
from langchain.agents import create_tool_calling_agent
from langchain_ollama import OllamaLLM
from app.tool import extract_text, parse_invoice, validate_invoice, calculate_bas

def create_simpleagent():
    # Local Mistral brain
    llm = OllamaLLM(model="mistral")

    # Register available tools
    tools = [extract_text, parse_invoice, validate_invoice, calculate_bas]

    # Create a ReAct-style agent that can call tools intelligently
    agent = create_tool_calling_agent(llm,tools)
    return agent

# Example usage
if __name__ == "__main__":
    agent = create_simpleagent()
    query = (
        "Take the uploaded invoice and work out the essentials — who sent it, the ABN, "
    "the invoice date, total amount, and GST. "
    "Clean up the numbers, make sure the ABN looks legit, and then tell me "
    "how this affects my BAS — how much GST I’ve paid or collected and what my net position is. "
    "Use plain Aussie English and keep it practical — no accounting jargon. "
    "Return the result as simple structured JSON with two parts: "
    "'invoice_data' (the invoice details) and 'bas_summary' (GST paid/collected and net BAS figure)."
    )
    response = agent.invoke(query)
    print(response)
