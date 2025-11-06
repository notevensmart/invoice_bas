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
import re, uuid , json
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv


load_dotenv(".env")
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
        self.llm = ChatGroq(
        model="llama-3.1-8b-instant",
        groq_api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.3
        )
        self.thread_id = f"session_{uuid.uuid4().hex[:8]}"
        self.history = []  # transient memory (reset each restart)
        self.memory = MemorySaver() 
        self.graph = self._build_graph()
        self.concise = False

    # ------------------------------------------------------------------
    # Prompt builder: adds brief chat history and reasoning instructions
    # ------------------------------------------------------------------
    def _build_prompt(self, message: str):
        history = "\n".join(
            f"User: {u}\nAgent: {a}" for u, a in self.history[-6:]
        )
        system_role = (
        "You are a friendly, professional Australian BAS and small-business assistant.\n"
        "Your goal is to help café owners and small business operators understand invoices, GST, and BAS concepts clearly.\n"
        "When the user asks about their business, BAS obligations, or general accounting topics, "
        "respond conversationally in plain Australian English — helpful, confident, never overly formal.\n"
        "Avoid technical code or tool syntax unless the user explicitly asks for implementation details.\n"
        "If the message is casual or unrelated to BAS, respond naturally but keep a helpful, professional tone.\n"
        )
        return f"{system_role}\n{history}\nUser: {message}\nAgent:"
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
        
    def _safe_markdown(text: str) -> str:
        """Prevent Markdown/MathJax from breaking currency text."""
        # Escape dollar signs
        text = text.replace("$", "\\$")
        # Ensure space after currency when needed
        text = re.sub(r"(\\\$)(\d)", r"\1 \2", text)
        # Normalise multiple spaces
        text = re.sub(r"\s{2,}", " ", text)
        return text

    def _format_response(self, tool_name: str, tool_output, explanation: str):
        def clean_val(v):
            if v in [None, "N/A", "", "Unknown"]:
                return None
            s = str(v).replace("$$", "$")
            if not s.startswith("$") and any(ch.isdigit() for ch in s):
                s = f"${s}"
            return s

        formatted = ""

        if tool_name == "parse_invoice" and isinstance(tool_output, dict):
            parts = [
                f"- Supplier: {tool_output.get('supplier')}",
                f"- ABN: {tool_output.get('abn')}",
                f"- Date: {tool_output.get('date')}",
                f"- Amount (ex GST): {clean_val(tool_output.get('amount_ex_gst'))}",
                f"- GST: {clean_val(tool_output.get('gst'))}",
            ]
            formatted += "📄 **Invoice Extracted**\n" + "\n".join(p for p in parts if p.split(': ')[1]) + "\n\n"

        elif tool_name == "validate_invoice":
            formatted += (
                "✅ **Validation**\n"
                f"- ABN valid: {tool_output.get('abn_valid', 'Unknown')}\n"
                f"- All fields present: {tool_output.get('fields_ok', 'Unknown')}\n\n"
            )

        elif tool_name == "calculate_bas":
            formatted += (
                "📊 **BAS Summary**\n"
                f"- GST Collected: {clean_val(tool_output.get('gst_collected', 0))}\n"
                f"- GST Paid: {clean_val(tool_output.get('gst_paid', 0))}\n"
                f"- **Net Liability / Refund:** {clean_val(tool_output.get('net_liability'))}\n\n"
            )
            liability = tool_output.get("net_liability", 0)
            if isinstance(liability, (int, float)):
                if liability > 0:
                    formatted += f"💬 You'll owe approximately ${liability:.2f} in GST this period.\n\n"
                elif liability < 0:
                    formatted += f"💬 You're due a GST refund of ${abs(liability):.2f}.\n\n"
                else:
                    formatted += "💬 Your GST collected and paid are balanced this period.\n\n"

        formatted += f"🗣️ **Explanation:** {explanation.strip()}\n"
        return formatted

    def _clean_final_output(self, text: str):
        """Remove duplicate explanations, None values, and normalise phrasing."""
        lines = []
        seen_expl = False
        for line in text.splitlines():
            if "🗣️ **Explanation:**" in line:
                # Keep only the last explanation
                if seen_expl:
                    continue
                seen_expl = True
            # Replace None/Unknown
            line = line.replace(": None", ": —").replace("Unknown", "Not yet verified")
            # Ensure clean spacing
            if line.strip():
                lines.append(line)
        return "\n".join(lines).strip()


    def _parse_node(self, state: AgentState):
        text = state["input"]
        if not text:
            return {"parsed": {}, "explanation": "No text provided."}

        result = parse_invoice(text)

        parsed = {
            "supplier": result.get("supplier") or result.get("supplier_name"),
            "abn": result.get("abn") or result.get("ABN"),
            "date": result.get("date"),
            "amount_ex_gst": result.get("amount_ex_gst") or result.get("subtotal") or "N/A",
            "gst": result.get("gst") or result.get("GST") or "N/A",
        }
        return {"parsed": parsed}


    


    # Return only clean structured data
          

    # Node 2: Validate the parsed invoice 
    def _validate_node(self, state: AgentState):
        parsed = state["parsed"]
        abn = parsed.get("abn")
        fields_ok = all(parsed.values())
        validated = {
        "abn_valid": bool(abn and len(abn.replace(" ", "")) == 11),
        "fields_ok": fields_ok
        }
        return {"validated": validated}

    def _calculate_node(self, state: AgentState):
        parsed = state["parsed"]
        validated = state["validated"]

        # Optionally, merge them
        invoice_data = parsed.copy()
        invoice_data.update(validated)

        bas_summary = calculate_bas([invoice_data])
        return {"output": bas_summary}

    def _explain_node(self, state: AgentState):
        """
        Intelligent explain node:
        - Summarizes BAS intelligently (concise or detailed)
        - Reflects on financial meaning
        - Avoids redundant repetition across turns
        """
        parsed = state.get("parsed", {})
        validated = state.get("validated", {})
        bas_summary = state.get("output", {})

        supplier = parsed.get("supplier", "this supplier")
        liability = float(bas_summary.get("net_liability", 0) or 0)
        gst_paid = float(bas_summary.get("gst_paid", 0) or 0)
        gst_collected = float(bas_summary.get("gst_collected", 0) or 0)

        # --- Reflective reasoning: derive cashflow context
        if liability < 0:
            context_line = (
                f"You've paid ${gst_paid:,.2f} in GST on purchases but only collected ${gst_collected:,.2f}. "
                f"That means you're due a refund of ${abs(liability):,.2f} this period. "
                "It suggests your business expenses have outweighed your sales this cycle — something worth keeping an eye on."
            )

        elif liability > 0:
            context_line = (
                f"You've collected ${gst_collected:,.2f} in GST from sales but only paid ${gst_paid:,.2f} on purchases. "
                f"This means you'll likely owe around ${liability:,.2f} in your next BAS. "
                "It's a good idea to set that amount aside now to avoid a surprise at lodgement time."
            )

        else:
            context_line = (
                "Your GST collected and paid are balanced, meaning your business activity this period was neutral."
            )
        context_line = self._safe_markdown(context_line)

        # --- Construct output (concise vs detailed)
        if getattr(self, "concise", True):
            summary = (
                f"**BAS Summary for {supplier}**\n"
                f"- GST Collected: ${gst_collected:.2f}\n"
                f"- GST Paid: ${gst_paid:.2f}\n"
                f"- Net BAS Position: ${liability:.2f}\n\n"
                f"{context_line}\n"
                "Would you like a broader summary across suppliers or a quarterly BAS estimate?"
            )
            return {"explanation": summary}

        # --- Detailed mode (adds validation + insights)
        formatted = (
            f"**Invoice Details**\n"
            f"- Supplier: {supplier}\n"
            f"- ABN: {parsed.get('abn', 'N/A')}\n"
            f"- Date: {parsed.get('date', 'Unknown')}\n"
            f"- Amount (ex GST): ${parsed.get('amount_ex_gst', 0)}\n"
            f"- GST: ${parsed.get('gst', 0)}\n\n"
            f"**Validation**\n"
            f"- ABN valid: {validated.get('abn_valid', 'Unknown')}\n"
            f"- All fields present: {validated.get('fields_ok', 'Unknown')}\n\n"
            f"**BAS Summary**\n"
            f"- GST Collected: ${gst_collected:.2f}\n"
            f"- GST Paid: ${gst_paid:.2f}\n"
            f"- Net Liability / Refund: ${liability:.2f}\n\n"
            f"💬 **Interpretation:** {context_line}\n"
            "If you'd like, I can estimate your quarterly BAS position or flag categories with rising costs."
        )

        formatted = self._clean_final_output(formatted)
        formatted = self._safe_markdown(formatted)
        return {"explanation": formatted}

   
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
    def run(self, message: str, mode: str = "chat"):
        """
        Smarter hybrid reasoning loop with:
        - Context-aware conversation memory
        - Graph reasoning only when required (new invoice or structured data)
        - Reflection-based improvement on final answer
        """
        # Step 0: Recall prior context for continuity
        recent_context = "\n".join(f"User: {u}\nAgent: {a}" for u, a in self.history[-3:])
        last_report = getattr(self, "last_report", "")

        # --- Pure chat mode if no new invoice
        if mode == "chat":
            context = ""
            if last_report:
                context = (
                    f"\nEarlier BAS summary:\n{last_report}\n"
                    "If the user asks about 'it' or 'that', assume they mean this summary."
                )

            chat_prompt = (
                "You are a conversational Australian BAS and bookkeeping assistant.\n"
                "Be concise, insightful, and friendly. Never regenerate the same BAS table.\n"
                "If the user sounds confused or asks 'what does that mean', explain their last BAS summary in simple terms.\n"
                "If they ask 'how am I tracking' or 'am I doing okay', provide financial insight based on trends.\n"
                "If unclear, ask a clarifying question.\n\n"
                f"Conversation so far:\n{recent_context}\n\nUser: {message}\nAgent:{context}"
            )

            reply = self.llm.invoke(chat_prompt)
            reply_text = reply if isinstance(reply, str) else reply.content
            self.history.append((message, reply_text))
            return {
                "response": reply_text.strip(),
                "mode": "chat",
                "thread_id": self.thread_id,
            }

        # --- Invoice (structured) mode
        print(f"🧾 Running intelligent BAS reasoning for message: {message}")
        initial_state = {"input": message}
        result = self.graph.invoke(initial_state, config=config)
        graph_output = result.get("explanation", "")

        # Save last report for chat reference
        self.last_report = graph_output

        # Reflective post-processing (improve phrasing + check relevance)
        reflection_prompt = (
            "Review the following BAS summary for clarity and usefulness to a café owner. "
            "Ensure it's helpful and easy to understand, with plain Australian English. "
            "If improvements are needed, rewrite it. Otherwise, return it unchanged.\n\n"
            f"{graph_output}"
        )
        reflection_resp = self.llm.invoke(reflection_prompt)
        reflection_text = reflection_resp if isinstance(reflection_resp, str) else reflection_resp.content

        final_output = reflection_text.strip()
        self.history.append((message, final_output))
        if len(self.history) > 8:
            self.history = self.history[-8:]

        return {
            "response": final_output,
            "mode": "invoice",
            "thread_id": self.thread_id,
        }

