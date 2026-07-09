import streamlit as st
import httpx
import json
import os
import uuid
from datetime import datetime

st.set_page_config(page_title="DocuMind Local AI", page_icon="⚡", layout="wide")

REGISTRATION_URL = "http://127.0.0.1:8888/summarizer/upload"
STREAM_URL = "http://127.0.0.1:8888/summarizer/upload/stream"
CHAT_URL = "http://127.0.0.1:8888/summarizer/chat"

HISTORY_FILE = "documind_sessions.json"

def load_sessions():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_sessions(sessions):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Failed to save local storage: {e}")

if "sessions" not in st.session_state:
    st.session_state.sessions = load_sessions()

if "active_session_id" not in st.session_state or st.session_state.active_session_id not in st.session_state.sessions:
    if st.session_state.sessions:
        st.session_state.active_session_id = list(st.session_state.sessions.keys())[0]
    else:
        new_id = str(uuid.uuid4())
        st.session_state.sessions[new_id] = {
            "title": "New Workspace",
            "pdf_id": None,
            "filename": None,
            "messages": [],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        st.session_state.active_session_id = new_id
        save_sessions(st.session_state.sessions)

current_session = st.session_state.sessions[st.session_state.active_session_id]

with st.sidebar:
    st.title("⚡ DocuMind Local")
    
    if st.button("➕ New Workspace", use_container_width=True, type="primary"):
        new_id = str(uuid.uuid4())
        new_session = {
            "title": "New Workspace",
            "pdf_id": None,
            "filename": None,
            "messages": [],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        st.session_state.sessions = {new_id: new_session, **st.session_state.sessions}
        st.session_state.active_session_id = new_id
        save_sessions(st.session_state.sessions)
        st.rerun()
        
    st.divider()
    
    if current_session.get("filename"):
        st.success(f"📎 Active Document:\n**{current_session['filename']}**")
        st.caption(f"Database ID: {current_session['pdf_id']}")
    else:
        st.info("No document loaded in this workspace.")

    st.divider()
    st.subheader("📚 Past Workspaces")
    
    for s_id, s_data in list(st.session_state.sessions.items()):
        title = s_data.get("title", "Untitled Workspace")
        is_active = (s_id == st.session_state.active_session_id)
        btn_type = "secondary" if not is_active else "primary"
        if st.button(f"💬 {title}", key=f"btn_{s_id}", use_container_width=True, type=btn_type):
            if not is_active:
                st.session_state.active_session_id = s_id
                st.rerun()

st.title(f"💬 {current_session['title']}")
st.caption("Attach a PDF file directly in the chat box below and ask for a summary or custom extraction.")

for msg in current_session["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt_input = st.chat_input(
    "Message DocuMind AI or attach a PDF...", 
    accept_file=True, 
    file_type=["pdf"]
)

if prompt_input:
    user_text = prompt_input.text if hasattr(prompt_input, "text") and prompt_input.text else ""
    attached_files = prompt_input.files if hasattr(prompt_input, "files") and prompt_input.files else []
    
    if attached_files:
        uploaded_file = attached_files[0]
        current_session["filename"] = uploaded_file.name
        current_session["title"] = uploaded_file.name[:25] + ("..." if len(uploaded_file.name) > 25 else "")
        current_session["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        display_prompt = user_text if user_text else f"Uploaded `{uploaded_file.name}` and requested summary."
        current_session["messages"].append({"role": "user", "content": display_prompt})
        save_sessions(st.session_state.sessions)
        
        with st.chat_message("user"):
            st.markdown(display_prompt)

        file_bytes = uploaded_file.getvalue()
        file_tuple = {"file": (uploaded_file.name, file_bytes, "application/pdf")}
        
        with st.spinner("Indexing document embeddings in Qdrant..."):
            try:
                with httpx.Client(timeout=300.0) as client:
                    upload_res = client.post(REGISTRATION_URL, files=file_tuple)
                    if upload_res.status_code == 201:
                        current_session["pdf_id"] = upload_res.json().get("id")
                        save_sessions(st.session_state.sessions)
                    else:
                        st.error("Failed to register document in backend.")
            except Exception as e:
                st.error(f"Database error: {str(e)}")

        with st.chat_message("assistant"):
            ai_response = ""
            placeholder = st.empty()
            form_data = {"custom_prompt": user_text} if user_text else {}
            
            try:
                with httpx.Client(timeout=300.0) as client:
                    with client.stream("POST", STREAM_URL, files=file_tuple, data=form_data) as response:
                        for chunk in response.iter_bytes():
                            if chunk:
                                token = chunk.decode("utf-8", errors="ignore")
                                ai_response += token
                                placeholder.markdown(ai_response + "▌")
                placeholder.markdown(ai_response)
                current_session["messages"].append({"role": "assistant", "content": ai_response})
                save_sessions(st.session_state.sessions)
            except Exception as e:
                st.error(f"Streaming failed: {str(e)}")

    else:
        if not current_session.get("pdf_id"):
            st.warning("Please attach a PDF file to your message first!")
        else:
            current_session["messages"].append({"role": "user", "content": user_text})
            save_sessions(st.session_state.sessions)
            
            with st.chat_message("user"):
                st.markdown(user_text)

            history_payload = [
                {"role": m["role"], "content": m["content"]}
                for m in current_session["messages"][:-1]
                if m["role"] in ["user", "assistant"]
            ]

            with st.chat_message("assistant"):
                ai_response = ""
                placeholder = st.empty()
                payload = {
                    "pdf_id": current_session["pdf_id"],
                    "question": user_text,
                    "history": history_payload
                }

                try:
                    with httpx.Client(timeout=120.0) as client:
                        with client.stream("POST", CHAT_URL, json=payload) as response:
                            for chunk in response.iter_bytes():
                                if chunk:
                                    token = chunk.decode("utf-8", errors="ignore")
                                    ai_response += token
                                    placeholder.markdown(ai_response + "▌")
                    placeholder.markdown(ai_response)
                    current_session["messages"].append({"role": "assistant", "content": ai_response})
                    save_sessions(st.session_state.sessions)
                except Exception as e:
                    st.error(f"Chat failed: {str(e)}")