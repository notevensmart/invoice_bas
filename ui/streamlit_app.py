import streamlit as st
import requests

# ------------------------------
# API Endpoints
# ------------------------------
API_URL_SINGLE = "https://invoicebas-production.up.railway.app/chat"
API_URL_BATCH  = "https://invoicebas-production.up.railway.app/process-batch"

# ------------------------------
# Streamlit Config
# ------------------------------
st.set_page_config(page_title="Smart BAS Assistant", page_icon="🧾", layout="centered")

if "messages" not in st.session_state:
    st.session_state["messages"] = []  # list of {"role": "user"|"assistant", "content": str}

st.title("🧾 Smart BAS Assistant")
st.caption("Upload invoices and chat about your BAS or GST.")

# ------------------------------
# Controls (stable widgets)
#   - One uploader (accepts many); we decide single vs batch in code
#   - Radio doesn't rebuild uploader, so no state weirdness
# ------------------------------
mode = st.radio("Upload mode:", ["Single Invoice", "Batch Upload"], horizontal=True)

uploaded_files = st.file_uploader(
    "Upload invoice(s) (PDF or image)",
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=True,      # keep one consistent widget
)

# ------------------------------
# Chat Input FIRST (so we can render history AFTER updates)
# ------------------------------
message = st.chat_input("Ask a question (e.g., 'How much GST did I pay?')")

if message:
    # 1) Record the user message now
    st.session_state["messages"].append({"role": "user", "content": message})

    # 2) Build request payload
    data = {"message": message}
    files_payload = None

    if uploaded_files:
        # If Single mode AND exactly one file → /chat (single)
        if mode == "Single Invoice" and len(uploaded_files) == 1:
            f = uploaded_files[0]
            files_payload = {"file": (f.name, f.read(), f.type)}
            endpoint = API_URL_SINGLE
        else:
            # Otherwise treat as batch
            files_payload = [("files", (f.name, f.read(), f.type)) for f in uploaded_files]
            endpoint = API_URL_BATCH
    else:
        # No files → pure conversational mode
        endpoint = API_URL_SINGLE

    # 3) Call backend
    with st.spinner("Processing ..."):
        try:
            r = requests.post(endpoint, data=data, files=files_payload)
            if r.status_code == 200:
                payload = r.json()

                # Prefer unified "response" if backend provides it
                if isinstance(payload, dict) and "response" in payload:
                    reply = payload["response"]

                # Fallback: if batch returns only aggregate fields
                elif isinstance(payload, dict) and "aggregate_summary" in payload:
                    s = payload["aggregate_summary"]
                    try:
                        reply = (
                            "📦 **Batch Summary**\n"
                            f"- GST Collected: ${float(s.get('gst_collected', 0)):.2f}\n"
                            f"- GST Paid: ${float(s.get('gst_paid', 0)):.2f}\n"
                            f"- Net BAS Position: ${float(s.get('net_liability', 0)):.2f}\n\n"
                            "Would you like me to break this down per supplier or compare months?"
                        )
                    except Exception:
                        reply = f"✅ Batch processed.\n\nRaw result:\n```\n{payload}\n```"

                else:
                    # Last-resort fallback: show whatever we got
                    reply = f"✅ Processed.\n\n```\n{payload}\n```"
            else:
                reply = f"⚠️ Backend error ({r.status_code})"
        except Exception as e:
            reply = f"❌ Connection error: {e}"

    # 4) Append assistant reply
    st.session_state["messages"].append({"role": "assistant", "content": reply})

# ------------------------------
# NOW render chat history (includes any new messages from this turn)
# ------------------------------
chat_box = st.container(height=420)
for msg in st.session_state["messages"]:
    with chat_box:
        st.chat_message(msg["role"]).markdown(msg["content"], unsafe_allow_html=True)
