import streamlit as st
import requests

API_URL_SINGLE = "https://invoicebas-production.up.railway.app/chat"
API_URL_BATCH  = "https://invoicebas-production.up.railway.app/process-batch"

st.set_page_config(page_title="Smart BAS Assistant", page_icon="🧾", layout="centered")

# Persistent chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

st.title("🧾 Smart BAS Assistant")
st.caption("Upload invoices and chat about your BAS or GST.")

# -----------------  Chat history  -----------------
chat_box = st.container(height=400)
for msg in st.session_state["messages"]:
    with chat_box:
        st.chat_message(msg["role"]).markdown(msg["content"], unsafe_allow_html=True)

# -----------------  Upload controls  -----------------
mode = st.radio("Upload mode :", ["Single Invoice", "Batch Upload"], horizontal=True)

if mode == "Single Invoice":
    uploaded_files = st.file_uploader(
        "Upload a single invoice (PDF or image)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=False,
    )
else:
    uploaded_files = st.file_uploader(
        "Upload multiple invoices (PDF or image)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

# -----------------  Chat input  -----------------
message = st.chat_input("Ask a question (e.g., 'How much GST did I pay?')")

if message:
    # 1️⃣ Show user message immediately
    st.session_state["messages"].append({"role": "user", "content": message})

    # 2️⃣ Build request
    data = {"message": message}
    if uploaded_files:
        if mode == "Single Invoice":
            files_payload = {"file": (uploaded_files.name, uploaded_files.read(), uploaded_files.type)}
            endpoint = API_URL_SINGLE
        else:
            files_payload = [("files", (f.name, f.read(), f.type)) for f in uploaded_files]
            endpoint = API_URL_BATCH
    else:
        files_payload = None
        endpoint = API_URL_SINGLE

    # 3️⃣ Call backend
    with st.spinner("Processing ..."):
        try:
            r = requests.post(endpoint, data=data, files=files_payload)
            if r.status_code == 200:
                reply = r.json().get("response", "")
            else:
                reply = f"⚠️ Backend error ({r.status_code})"
        except Exception as e:
            reply = f"❌ Connection error: {e}"

    # 4️⃣ Display assistant reply immediately
    st.session_state["messages"].append({"role": "assistant", "content": reply})
