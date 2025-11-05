import streamlit as st
import requests

API_URL = "https://invoicebas-production.up.railway.app/chat"

st.set_page_config(page_title="Smart BAS Assistant", page_icon="🧾", layout="centered")
if "messages" not in st.session_state:
    st.session_state["messages"] = []

st.title("🧾 Smart BAS Assistant")
st.caption("Upload your invoice and ask me anything about your BAS or GST.")

# Scrollable chat history
chat_box = st.container(height=400)
for msg in st.session_state["messages"]:
    with chat_box:
        st.chat_message(msg["role"]).markdown(msg["content"], unsafe_allow_html=True)

# Input area
message = st.chat_input("Ask a question (e.g., 'How much GST did I pay?')")
uploaded_file = st.file_uploader("Upload an invoice (PDF or image)", type=["pdf", "png", "jpg", "jpeg"])

if message:
    st.session_state["messages"].append({"role": "user", "content": message})
    with st.spinner("Thinking..."):
        files = {"file": uploaded_file.getvalue()} if uploaded_file else None
        data = {"message": message}
        resp = requests.post(API_URL, data=data, files=files)
        if resp.status_code == 200:
            data = resp.json()
            bot_reply = data.get("response", "")
        else:
            bot_reply = f"⚠️ Backend error ({resp.status_code})"
        st.session_state["messages"].append({"role": "assistant", "content": bot_reply})
        st.rerun()
