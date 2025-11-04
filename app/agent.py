# app/agent.py
from langgraph.graph import StateGraph, END
from langchain_community.tools import StructuredTool
from langchain_community.chat_models import ChatOllama
from app.core_tools import extract_text, parse_invoice, validate_invoice, calculate_bas
from typing import TypedDict
# app/agent.py
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field
import re, uuid



class AgentState(TypedDict):
    input: str
    parsed: dict
    validated: dict
    output: dict
    explanation: str

class BASSummary(BaseModel):
    gst_collected: float = Field(description="Total GST collected from sales")
    gst_paid: float = Field(description="Total GST paid to suppliers")
    net_liability: float = Field(description="Net BAS liability or refund amount")



config = {
    "configurable": {
        "thread_id": f"session_{uuid.uuid4().hex[:8]}",
        "checkpoint_ns": "bas_agent"
    }
}

class ChatBASAgent:
    def __init__(self):
        # Local, free model via Ollama
        self.llm = ChatOllama(model="mistral")
        self.thread_id = f"session_{uuid.uuid4().hex[:8]}"
        self.history = []  # transient memory (reset each restart)

    # ------------------------------------------------------------------
    # Prompt builder: adds brief chat history and reasoning instructions
    # ------------------------------------------------------------------
    def _build_prompt(self, message: str):
        history = "\n".join(
            f"User: {u}\nAgent: {a}" for u, a in self.history[-6:]
        )
        tool_docs = (
            "You are a helpful Australian BAS assistant.\n"
            "You can use these tools:\n"
            "- parse_invoice(text:str): Extract supplier/date/amount/GST.\n"
            "- validate_invoice(parsed:dict): Validate invoice data.\n"
            "- calculate_bas(validated:dict): Compute GST collected/paid/net BAS.\n"
            "If the message isn't about invoices or GST, just respond conversationally.\n"
            "When you want to use a tool, output [TOOL: tool_name].\n"
            "After the tool runs, explain the result clearly.\n"
        )
        return f"{tool_docs}\n{history}\nUser: {message}\nAgent:"
    def _call_tool(self, name: str, text: str):
        try:
            if name == "parse_invoice":
                return parse_invoice(text)
            elif name == "validate_invoice":
                parsed = parse_invoice(text)
                return validate_invoice(parsed)
            elif name == "calculate_bas":
                parsed = parse_invoice(text)
                valid = validate_invoice(parsed)
                return calculate_bas([valid])
            else:
                return f"Unknown tool '{name}'."
        except Exception as e:
            return f"Tool '{name}' failed: {e}"
    def _format_response(self, tool_name: str, tool_output, explanation: str):
        """Format agent response to include all key invoice & BAS details."""
        formatted = ""

        if tool_name == "parse_invoice" and isinstance(tool_output, dict):
            formatted += (
            f"📄 **Parsed Invoice**\n"
            f"- Supplier: {tool_output.get('supplier', 'N/A')}\n"
            f"- ABN: {tool_output.get('abn', 'N/A')}\n"
            f"- Date: {tool_output.get('date', 'N/A')}\n"
            f"- Amount (ex GST): ${tool_output.get('amount_ex_gst', 'N/A')}\n"
            f"- GST: ${tool_output.get('gst', 'N/A')}\n"
        )

        elif tool_name == "validate_invoice" and isinstance(tool_output, dict):
            formatted += (
            f"✅ **Validation Results**\n"
            f"- ABN valid: {tool_output.get('abn_valid', 'Unknown')}\n"
            f"- All fields present: {tool_output.get('fields_ok', 'Unknown')}\n"
        )

        elif tool_name == "calculate_bas" and isinstance(tool_output, dict):
            formatted += (
            f"📊 **BAS Summary**\n"
            f"- GST Collected: ${tool_output.get('gst_collected', 'N/A')}\n"
            f"- GST Paid: ${tool_output.get('gst_paid', 'N/A')}\n"
            f"- **Net Liability / Refund:** ${tool_output.get('net_liability', 'N/A')}\n"
        )

        formatted += f"\n💬 **Explanation:** {explanation.strip()}\n"
        formatted += f"\n🧾 Session ID: `{self.thread_id}`"
        return formatted

    def _parse_node(self,state: AgentState):
        text = state["input"]
        if "invoice" in text.lower() or "$" in text or "gst" in text.lower():
            parsed = parse_invoice(text)
            return {"parsed": parsed}

    # Otherwise treat as conversation
        return {
        "parsed": None,
        "explanation": "Sure thing — when you upload an invoice I’ll calculate its BAS impact for you."
        }

    # Node 2: Validate the parsed invoice 
    def _validate_node(self,state: AgentState):
        validated = validate_invoice(state["parsed"])
        return {"validated": validated}

    def _calculate_node(self, state: AgentState):
        bas_summary = calculate_bas([state["validated"]])
        return {"output": bas_summary}

    def _explain_node(self, state: AgentState):
        """LLM explanation using conversation history."""
        llm = self.llm
        bas_summary = state["output"]
        user_input = state["input"]

        prompt = self.memory.build_prompt(
        f"The current BAS summary is:\n{bas_summary}\nExplain this to the user naturally."
        )

        explanation = llm.invoke(prompt)
        self.memory.update(user_input, explanation)
        return {"explanation": explanation}

    # ----- Build LangGraph -----
    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("parse", self._parse_node)
        graph.add_node("validate", self._validate_node)
        graph.add_node("calculate", self._calculate_node)
        graph.add_node("explain", self._explain_node)

        graph.set_entry_point("parse")
        graph.add_edge("parse", "validate")
        graph.add_edge("validate", "calculate")
        graph.add_edge("calculate", "explain")
        graph.add_edge("explain", END)
        return graph.compile(checkpointer=self.memory)

    # ----- Invoke the agent -----
    def run(self, message: str):
        prompt = self._build_prompt(message)
        reply = self.llm.invoke(prompt)
        reply_text = reply if isinstance(reply, str) else reply.content

        # detect [TOOL: xyz]
        tool_match = re.search(r"\[TOOL:\s*(\w+)\s*\]", reply_text)
        if not tool_match:
            self.history.append((message, reply_text))
            return {"response": reply_text, "thread_id": self.thread_id}

        tool_name = tool_match.group(1).lower()
        tool_output = self._call_tool(tool_name, message)

        # ask model to explain tool output
        explain_prompt = (
            f"The user message was:\n{message}\n"
            f"You ran the tool '{tool_name}' and got this result:\n{tool_output}\n"
            "Now explain this to the user in plain Australian English."
        )
        explanation = self.llm.invoke(explain_prompt)
        explanation_text = (
            explanation if isinstance(explanation, str) else explanation.content
        )

        self.history.append((message, explanation_text))
        formatted_output = self._format_response(tool_name, tool_output, explanation_text)
        return {
            "response": formatted_output,
            "tool": tool_name,
            "tool_output": tool_output,
            "thread_id": self.thread_id,
        }
   