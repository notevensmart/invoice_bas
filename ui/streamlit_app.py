import streamlit as st
import requests

API_URL_SINGLE = "https://invoicebas-production.up.railway.app/chat"
API_URL_BATCH  = "https://invoicebas-production.up.railway.app/process-batch"

st.set_page_config(page_title="Smart BAS Assistant", page_icon="🧾", layout="wide")

# Layout: two columns → chat on left, notes on right
col_chat, col_notes = st.columns([3, 1])

with col_chat:
    st.title("🧾 Smart BAS Assistant")
    st.caption("Upload invoices and chat about your BAS or GST.")

    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    # Chat history
    chat_box = st.container(height=420)
    for msg in st.session_state["messages"]:
        with chat_box:
            st.chat_message(msg["role"]).markdown(msg["content"], unsafe_allow_html=True)

    # Mode + file upload
    mode = st.radio("Upload mode:", ["Single Invoice", "Batch Upload"], horizontal=True)
    uploaded_files = st.file_uploader(
        "Upload invoice(s) (PDF or image)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    # Chat input
    message = st.chat_input("Ask a question (e.g., 'How much GST did I pay?')")

    if message:
        st.session_state["messages"].append({"role": "user", "content": message})
        data = {"message": message}

        # Decide endpoint
        if uploaded_files:
            if mode == "Single Invoice" and len(uploaded_files) == 1:
                files_payload = {"file": (uploaded_files[0].name, uploaded_files[0].read(), uploaded_files[0].type)}
                endpoint = API_URL_SINGLE
            else:
                files_payload = [("files", (f.name, f.read(), f.type)) for f in uploaded_files]
                endpoint = API_URL_BATCH
        else:
            files_payload = None
            endpoint = API_URL_SINGLE

        with st.spinner("Processing..."):
            try:
                r = requests.post(endpoint, data=data, files=files_payload)
                if r.status_code == 200:
                    payload = r.json()
                    reply = payload.get("response", str(payload))
                else:
                    reply = f"⚠️ Backend error ({r.status_code})"
            except Exception as e:
                reply = f"❌ Connection error: {e}"

        st.session_state["messages"].append({"role": "assistant", "content": reply})

# ---------------- Notes / Tips column ----------------
with col_notes:
    st.markdown("### Dev Comments")
    st.markdown(
        """
        ** Version 1.0 **
        **Team Vision**
        To create a one-stop BAS assistant that understands your business activity, automates paperwork, and provides data-driven insights — not just reports
        **Common Issues & Fixes**
        - If you receive a backend error after the first message then please retry, it should work the second time.
        - To engage in conversation with the agent, make sure all files are removed from the dropdown.
        
        **Best Practices**
        - Use clear scans or PDFs for accurate GST extraction.   
        - If results seem off, re-upload cleaner copies or check ABN formatting.

        **Need Help?**
        You can type questions like:
        - “What does my BAS summary mean?”
        - “How much refund am I getting?”
        - “Compare my suppliers.”

        **Extensions for clients**
        - Direct integrations with Xero, QuickBooks, or Gmail for automatic invoice fetching.
        - Secure cloud storage and team-based access.
        - Custom dashboards to visualise BAS, supplier trends, or cashflow insights.
        - Private deployments on your preferred cloud (GCP, AWS, or Azure).
        """
        
    )
