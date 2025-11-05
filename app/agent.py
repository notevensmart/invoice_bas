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
                    formatted += f"💬 You’ll owe approximately ${liability:.2f} in GST this period.\n\n"
                elif liability < 0:
                    formatted += f"💬 You’re due a GST refund of ${abs(liability):.2f}.\n\n"
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
        parsed = state.get("parsed", {})
        validated = state.get("validated", {})
        bas_summary = state.get("output", {})

        last_user_message = self.history[-1][0] if self.history else ""
        intent_prompt = (
            "You are a classification helper for a BAS assistant.\n"
            "Return a JSON list of one or more: ['gst', 'abn', 'bas', 'summary'] "
            "representing what the user is asking for.\n"
            f"User message: {last_user_message}"
        )
        intent_guess = self.llm.invoke(intent_prompt)
        intent_text = intent_guess if isinstance(intent_guess, str) else intent_guess.content

        try:
            requested_keys = json.loads(intent_text)
            if not isinstance(requested_keys, list):
                requested_keys = [requested_keys]
        except Exception:
            requested_keys = ["summary"]

        requested_keys = [k.lower() for k in requested_keys]
        liability = float(bas_summary.get("net_liability", 0) or 0)

        # --- Concise friendly mode ---
        if getattr(self, "concise", True):
            if "gst" in requested_keys or "abn" in requested_keys:
                if liability < 0:
                    message = (
                        f"You paid ${bas_summary.get('gst_paid', 0):.2f} GST on your "
                        f"{parsed.get('supplier', 'supplier')} invoice, so you're due a refund of "
                        f"${abs(liability):.2f} this period. "
                        "Looks like you've paid more GST on purchases than you collected from customers. "
                        "Would you like me to show how this affects your next BAS?"
                    )
                elif liability > 0:
                    message = (
                        f"You collected more GST than you paid — about ${liability:.2f} owing this period. "
                        "That means you'll likely have a GST liability for your next BAS. "
                        "Would you like me to estimate what that looks like across your invoices?"
                    )
                else:
                    message = (
                        "Your GST collected and paid are balanced this period. "
                        "If you'd like, I can help you double-check your supplier invoices for any missed credits."
                    )
                return {"explanation": message}

            # 🧾 Concise summary (when user says 'show summary' or 'bas')
            summary = (
                f"**BAS Summary**\n"
                f"- Supplier: {parsed.get('supplier')}\n"
                f"- ABN: {parsed.get('abn')}\n"
                f"- GST Collected: ${bas_summary.get('gst_collected', 0):.2f}\n"
                f"- GST Paid: ${bas_summary.get('gst_paid', 0):.2f}\n"
                f"- Net Liability / Refund: ${liability:.2f}\n"
            )
            return {"explanation": summary}

        # --- Detailed mode (for developer or user request) ---
        formatted = (
            self._format_response("parse_invoice", parsed, "") + "\n" +
            self._format_response("validate_invoice", validated, "") + "\n" +
            self._format_response("calculate_bas", bas_summary, "")
        )
        formatted = self._clean_final_output(formatted)
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
    def run(self, message: str):
        """
        Hybrid reasoning loop with:
        - Conversational memory (recalls recent turns)
        - Dynamic verbosity (concise/detailed switch)
        - Invoice reasoning graph
        - Friendly chat fallback
        """

        # ---- Step 0 | Context memory ----
        history_context = "\n".join(
            f"User: {u}\nAgent: {a}" for u, a in self.history[-4:]
        )
        context_prompt = (
            "You are a friendly, professional Australian BAS assistant.\n"
            "Use the short history below for continuity; greet naturally if returning.\n\n"
            f"History:\n{history_context}\n\nUser: {message}\nAgent:"
        )

        # ---- Step 1 | Intent classification ----
        interpret_prompt = (
            "Classify this message.\n"
            "If it involves invoices, receipts, or GST/BAS → [INVOICE_MODE].\n"
            "If it’s casual or unrelated → [CHAT_MODE].\n"
            "Respond with one tag only.\n\n"
            f"User: {message}\nAgent:"
        )
        intent_resp = self.llm.invoke(interpret_prompt)
        intent_text = intent_resp if isinstance(intent_resp, str) else intent_resp.content

        # ---- Step 2 | Invoice mode ----
        if "[INVOICE_MODE]" in intent_text.upper():
            print(f"🧩 Running structured BAS graph for message: {message}")

            # --- Dynamic verbosity (unless forced) ---
            if not getattr(self, "force_mode", False):
                verbosity_prompt = (
                    "Decide detail level for a BAS assistant.\n"
                    "If the user wants a quick figure (GST paid/refund/ABN) → [CONCISE].\n"
                    "If they request a full BAS summary/report → [DETAILED].\n"
                    "Respond with one tag only.\n\n"
                    f"User: {message}\nAssistant:"
                )
                verbosity_resp = self.llm.invoke(verbosity_prompt)
                verbosity_text = (
                    verbosity_resp if isinstance(verbosity_resp, str)
                    else verbosity_resp.content
                )
                if "[CONCISE]" in verbosity_text.upper():
                    self.concise = True
                elif "[DETAILED]" in verbosity_text.upper():
                    self.concise = False

            print(f"🧠 Agent verbosity set to: {'Concise' if self.concise else 'Detailed'}")

            # --- Detail detection (gst/abn/bas/summary) ---
            detail_prompt = (
                "Identify which details the user wants from the invoice.\n"
                "Possible options: gst, abn, bas, summary.\n"
                "Return a JSON list like ['gst','bas'].\n\n"
                f"User: {message}"
            )
            detail_resp = self.llm.invoke(detail_prompt)
            detail_text = detail_resp if isinstance(detail_resp, str) else detail_resp.content
            try:
                requested_keys = json.loads(detail_text)
                if not isinstance(requested_keys, list):
                    requested_keys = [requested_keys]
            except Exception:
                requested_keys = ["summary"]
            requested_keys = [k.lower() for k in requested_keys]

            # --- Step 3 | Run reasoning graph (with context prompt) ---
            initial_state = {"input": context_prompt}
            result = self.graph.invoke(initial_state, config=config)
            graph_output = result.get("explanation", "No explanation generated.")

            # --- Step 4 | Adaptive output formatting ---
            if getattr(self, "concise", True) and ("gst" in requested_keys or "abn" in requested_keys):
                concise_prompt = (
                    "Summarise this BAS report in 1-2 friendly sentences in plain Australian English.\n"
                    "Focus only on GST paid/collected and refund/liability.\n"
                    "No markdown or headings.\n\n"
                    f"Report:\n{graph_output}"
                )
                concise_resp = self.llm.invoke(concise_prompt)
                concise_text = concise_resp if isinstance(concise_resp, str) else concise_resp.content
                final_output = concise_text.strip()
            else:
                detailed_prompt = (
                    "Format this BAS report neatly in Markdown with clear sections.\n"
                    "Include Supplier, ABN, GST Collected, GST Paid, Net Liability / Refund.\n"
                    "End with one short friendly sentence offering further help.\n\n"
                    f"Report:\n{graph_output}"
                )
                detailed_resp = self.llm.invoke(detailed_prompt)
                detailed_text = detailed_resp if isinstance(detailed_resp, str) else detailed_resp.content
                final_output = f"👋 Hi there!\n\n{detailed_text.strip()}"

            # ---- Step 5 | Update short-term memory ----
            self.history.append((message, final_output))
            if len(self.history) > 8:
                self.history = self.history[-8:]

            return {
                "response": final_output,
                "mode": "invoice",
                "thread_id": self.thread_id,
            }

        # ---- Step 3 | Chat fallback ----
        print(f"💬 Chat mode triggered for message: {message}")
        chat_prompt = (
            "You are a friendly Australian BAS and bookkeeping assistant.\n"
            "Use the short history below for continuity.\n\n"
            f"History:\n{history_context}\n\nUser: {message}\nAgent:"
        )
        reply = self.llm.invoke(chat_prompt)
        reply_text = reply if isinstance(reply, str) else reply.content

        # Save to memory
        self.history.append((message, reply_text))
        if len(self.history) > 8:
            self.history = self.history[-8:]

        return {
            "response": reply_text,
            "mode": "chat",
            "thread_id": self.thread_id,
        }

