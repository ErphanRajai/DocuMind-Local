import streamlit as st
import httpx

st.set_page_config(page_title="Local Doc Chatbot AI", page_icon="🤖", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pdf_id" not in st.session_state:
    st.session_state.pdf_id = 1

st.title("💬 Conversational Document AI")
st.caption("Upload a file to generate a summary, then chat with it freely using local resources.")

REGISTRATION_URL = "http://127.0.0.1:8888/summarizer/upload"
STREAM_URL = "http://127.0.0.1:8888/summarizer/upload/stream"
CHAT_URL = "http://127.0.0.1:8888/summarizer/chat"

trigger_summary_stream = False
uploaded_file_payload = None

with st.sidebar:
    st.header("Document Setup")
    uploaded_file = st.file_uploader("Upload Target PDF", type=["pdf"])
    
    if uploaded_file and st.button("Process & Summarize Document", type="primary"):
        trigger_summary_stream = True
        uploaded_file_payload = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


if trigger_summary_stream and uploaded_file_payload:
    with st.spinner("Processing text maps and registering document..."):
        try:
            with httpx.Client(timeout=300.0) as client:
                upload_res = client.post(REGISTRATION_URL, files=uploaded_file_payload)
                if upload_res.status_code == 201:
                    doc_data = upload_res.json()
                    st.session_state.pdf_id = doc_data.get("id")
                else:
                    st.error(f"Registration failed with status code: {upload_res.status_code}")
        except Exception as e:
            st.error(f"Pipeline database error: {str(e)}")
            trigger_summary_stream = False

    if trigger_summary_stream:
        with st.chat_message("assistant"):
            full_summary = ""
            summary_placeholder = st.empty()
            
            try:
                with httpx.Client(timeout=300.0) as client:
                    with client.stream("POST", STREAM_URL, files=uploaded_file_payload) as response:
                        for chunk in response.iter_bytes():
                            if chunk:
                                token = chunk.decode("utf-8", errors="ignore")
                                full_summary += token
                                summary_placeholder.markdown(full_summary + "▌")
                
                summary_placeholder.markdown(full_summary)
                st.session_state.messages.append({"role": "assistant", "content": full_summary})
            except Exception as e:
                st.error(f"Streaming transmission failure: {str(e)}")

if user_prompt := st.chat_input("Ask me anything about the uploaded file..."):
    with st.chat_message("user"):
        st.markdown(user_prompt)
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        ai_response = ""
        
        try:
            payload = {"pdf_id": st.session_state.pdf_id, "question": user_prompt}
            
            with httpx.Client(timeout=120.0) as client:
                with client.stream("POST", CHAT_URL, json=payload) as response:
                    for chunk in response.iter_bytes():
                        if chunk:
                            token = chunk.decode("utf-8", errors="ignore")
                            ai_response += token
                            response_placeholder.markdown(ai_response + "▌")
            
            response_placeholder.markdown(ai_response)
            st.session_state.messages.append({"role": "assistant", "content": ai_response})
        except Exception as e:
            st.error(f"Chat communication failure: {str(e)}")