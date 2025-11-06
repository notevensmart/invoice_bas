import streamlit as st
import requests

# ------------------------------
# API Endpoints
# ------------------------------
API_URL_SINGLE = "https://invoicebas-production.up.railway.app/chat"
API_URL_BATCH = "https://invoicebas-production.up.railway.app/process-batch"

# ------------------------------
# Streamlit Config
# ------------------------------
st.set_page_config(page_title="Smart BAS Assistant", page_icon="🧾", layout="centered")

if "messages" not in st.session_state:
    st.session_state["messages"] = []

st.title("🧾 Smart BAS Assistant")
st.caption("Upload invoices and chat about your BAS or GST.")

# ------------------------------
# Chat History Container
# ------------------------------
chat_box = st.container(height=400)
for msg in st.session_state["messages"]:
    with chat_box:
        st.chat_message(msg["role"]).markdown(msg["content"], unsafe_allow_html=True)

# ------------------------------
# Upload Section
# ------------------------------
mode = st.radio("Select upload mode:", ["Single Invoice", "Batch Upload"], horizontal=True)

if mode == "Single Invoice":
    uploaded_files = st.file_uploader(
        "Upload a single invoice (PDF or image)",
        type=["pdf", "png", "jpg", "jpeg"],
        key="single_uploader",
        accept_multiple_files=False,
    )
else:
    uploaded_files = st.file_uploader(
        "Upload multiple invoices (PDF or image)",
        type=["pdf", "png", "jpg", "jpeg"],
        key="batch_uploader",
        accept_multiple_files=True,
    )

# ------------------------------
# Chat Input Field
# ------------------------------
message = st.chat_input("Ask a question (e.g., 'How much GST did I pay?')")

if message:
    # Save user message in chat history
    st.session_state["messages"].append({"role": "user", "content": message})

    # Build data payload
    data = {"message": message}
    files_payload = None

    # ------------------------------
    # Decide which endpoint to call
    # ------------------------------
    if uploaded_files:
        if mode == "Single Invoice":
            files_payload = {"file": (uploaded_files.name, uploaded_files.read(), uploaded_files.type)}
            endpoint = API_URL_SINGLE
        else:
            files_payload = [("files", (f.name, f.read(), f.type)) for f in uploaded_files]
            endpoint = API_URL_BATCH
    else:
        endpoint = API_URL_SINGLE  # No upload → chat only

    # ------------------------------
    # Send request to backend
    # ------------------------------
    with st.spinner("Processing..."):
        try:
            response = requests.post(endpoint, data=data, files=files_payload)
            if response.status_code == 200:
                data = response.json()
                bot_reply = data.get("response", "")
            else:
                bot_reply = f"⚠️ Backend error ({response.status_code})"
        except Exception as e:
            bot_reply = f"❌ Connection error: {e}"

    # ------------------------------
    # Display reply & cleanup
    # ------------------------------
    st.session_state["messages"].append({"role": "assistant", "content": bot_reply})

    # Safely close and reset uploader (no direct session write)
    if uploaded_files:
        if isinstance(uploaded_files, list):
            for f in uploaded_files:
                f.close()
        else:
            uploaded_files.close()

        # 🚀 Trigger UI refresh to clear uploader
        st.rerun()
