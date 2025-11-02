# app/agent.py
from langgraph.graph import StateGraph, END
from langchain_community.tools import StructuredTool
from langchain_ollama import OllamaLLM
from app.core_tools import extract_text, parse_invoice, validate_invoice, calculate_bas
from typing import TypedDict

class AgentState(TypedDict):
    input: str
    parsed: dict
    validated: dict
    output: dict

def parse_node(state: AgentState):
    text = state["input"]
    parsed = parse_invoice(text)
    return {"parsed": parsed}

    # Node 2: Validate the parsed invoice 
def validate_node(state: AgentState):
    validated = validate_invoice(state["parsed"])
    return {"validated": validated}

    # Node 3: Calculate BAS summary
def calculate_node(state: AgentState):
    bas_summary = calculate_bas([state["validated"]])
    return {"output": bas_summary}

def create_simpleagent():
    # Local Mistral brain
    llm = OllamaLLM(model="mistral")

    # Register available tools
    tools = [
        StructuredTool.from_function(parse_invoice),
        StructuredTool.from_function(validate_invoice),
        StructuredTool.from_function(calculate_bas),
    ]
    graph = StateGraph(AgentState)
    graph.add_node("parse", parse_node)
    graph.add_node("validate", validate_node)
    graph.add_node("calculate", calculate_node)

    graph.set_entry_point("parse")
    graph.add_edge("parse", "validate")
    graph.add_edge("validate", "calculate")
    graph.add_edge("calculate", END)

    # Compile into a runnable object
    compiled = graph.compile()
    return compiled


    # Create a ReAct-style agent that can call tools intelligently

# Example usage
if __name__ == "__main__":
    agent = create_simpleagent()
    result= agent.invoke({"input": input})

   
    print(result["output"])
