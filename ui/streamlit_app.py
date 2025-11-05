import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000/ask"

st.set_page_config(page_title="Smart BAS Assistant", page_icon="🧾")

st.title("🧾 Smart BAS Assistant")
st.caption("Upload your invoice and ask me anything about your BAS or GST.")

message = st.text_input("Ask a question (e.g., 'How much GST did I pay?')")

uploaded_file = st.file_uploader("Upload an invoice (PDF or image)", type=["pdf", "png", "jpg", "jpeg"])

if st.button("Submit"):
    if not message:
        st.warning("Please type a question first.")
    else:
        with st.spinner("Thinking..."):
            resp = requests.post(API_URL, data={"message": message})
            if resp.status_code == 200:
                data = resp.json()
                st.markdown(data["response"])
            else:
                st.error("Error contacting backend.")
