import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from datetime import datetime

import httpx
import streamlit as st

st.set_page_config(page_title="DOCUMIND", layout="wide")

# Modern Monospace Visual Architecture & Styled Indicators
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,300;0,400;0,600;0,700;1,400&display=swap');

    html, body, p, span:not([data-testid="stIconMaterial"]), div:not([data-testid="stIconMaterial"]), button, input, textarea {
        font-family: 'JetBrains Mono', monospace !important;
    }

    .stApp {
        background-color: #0c0d0e;
        color: #d1d5db;
    }

    button[data-testid="stSidebarCollapseButton"] span,
    button[data-testid="stSidebarHeaderCollapseButton"] span,
    [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
        font-style: normal;
        text-transform: none;
    }

    section[data-testid="stSidebar"] {
        background-color: #080808 !important;
        border-right: 1px solid #1f2428;
    }

    h1, h2, h3, h4, h5, h6 {
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 700 !important;
        color: #f3f4f6 !important;
        letter-spacing: -0.5px;
    }

    div[data-testid="stChatMessageAvatarUser"],
    div[data-testid="stChatMessageAvatarAssistant"],
    .stChatMessage [data-testid="stChatMessageAvatar"] {
        display: none !important;
    }

    .stChatMessage {
        background-color: transparent !important;
        border: none !important;
        padding: 0 !important;
        margin-bottom: 0.35rem !important;
        display: flex !important;
        width: 100% !important;
    }

    .stChatMessage > div:nth-child(2) {
        padding: 0.9rem 1.2rem !important;
        border-radius: 4px !important;
        font-size: 0.90rem !important;
        line-height: 1.6 !important;
    }

    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]),
    .stChatMessage:has([aria-label*="user"]) {
        flex-direction: row-reverse !important;
    }

    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) > div:nth-child(2),
    .stChatMessage:has([aria-label*="user"]) > div:nth-child(2) {
        max-width: 75% !important;
        width: auto !important;
        background-color: #16181d !important;
        border: 1px solid #272a30 !important;
        color: #e2e8f0 !important;
        margin-left: auto !important;
        text-align: left !important;
    }

    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarAssistant"]) > div:nth-child(2),
    .stChatMessage:has([aria-label*="assistant"]) > div:nth-child(2) {
        max-width: 88% !important;
        width: auto !important;
        background-color: #0e1013 !important;
        border: 1px solid #1a1d23 !important;
        border-left: 2px solid #3b82f6 !important;
        color: #d1d5db !important;
        margin-right: auto !important;
    }

    /* Horizontal Slideable PDF Attachment Carousel */
    .pdf-card-container {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        gap: 8px !important;
        margin-bottom: 10px !important;
        padding-bottom: 6px !important;
        scrollbar-width: thin !important;
        scrollbar-color: #27272a transparent !important;
        -webkit-overflow-scrolling: touch !important;
        max-width: 100% !important;
    }

    .pdf-card-container::-webkit-scrollbar {
        height: 4px !important;
    }

    .pdf-card-container::-webkit-scrollbar-thumb {
        background: #27272a !important;
        border-radius: 2px !important;
    }

    .pdf-badge {
        flex: 0 0 auto !important;
        display: inline-flex !important;
        align-items: center !important;
        gap: 6px !important;
        background: #111317 !important;
        border: 1px solid #2c313a !important;
        border-radius: 4px !important;
        padding: 4px 10px !important;
        font-size: 0.75rem !important;
        color: #e2e8f0 !important;
        max-width: 260px !important;
        box-sizing: border-box !important;
    }

    .pdf-icon {
        color: #ef4444 !important;
        font-weight: 800 !important;
        font-size: 0.72rem !important;
        background: rgba(239, 68, 68, 0.15) !important;
        padding: 1px 4px !important;
        border-radius: 2px !important;
        flex-shrink: 0 !important;
    }

    .pdf-name {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        display: inline-block !important;
    }

    /* Model Hub and Cards Styling */
    .model-card {
        background: #101216;
        border: 1px solid #22262e;
        border-radius: 3px;
        padding: 6px 8px;
        margin-bottom: 6px;
        font-size: 0.73rem;
    }
    .model-card b {
        color: #93c5fd;
    }
    .model-card .desc {
        color: #71717a;
        margin: 2px 0 4px 0;
        font-size: 0.68rem;
    }
    .model-card a {
        color: #60a5fa !important;
        text-decoration: none;
        font-weight: 600;
    }
    .model-card a:hover {
        text-decoration: underline;
    }

    .pipeline-status {
        font-size: 0.78rem !important;
        color: #93c5fd !important;
        background: rgba(15, 23, 42, 0.55) !important;
        border: 1px dashed rgba(59, 130, 246, 0.35) !important;
        padding: 8px 12px !important;
        border-radius: 4px !important;
        margin-bottom: 10px !important;
        display: flex !important;
        align-items: center !important;
        gap: 8px !important;
        animation: pulse 1.8s infinite ease-in-out !important;
    }

    @keyframes pulse {
        0% { opacity: 0.6; }
        50% { opacity: 0.95; }
        100% { opacity: 0.6; }
    }

    .stButton > button {
        font-family: 'JetBrains Mono', monospace !important;
        border-radius: 2px !important;
        border: 1px solid #27272a !important;
        background-color: #121316 !important;
        color: #a1a1aa !important;
        font-size: 0.78rem !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        display: block !important;
        text-align: left !important;
        padding: 0.25rem 0.5rem !important;
        transition: all 0.15s ease-in-out;
    }

    .stButton > button:hover {
        border-color: #3b82f6 !important;
        color: #ffffff !important;
        background-color: #18191d !important;
    }

    .stButton > button[kind="primary"] {
        background-color: #1e293b !important;
        border-color: #3b82f6 !important;
        color: #60a5fa !important;
    }

    .metrics-bar {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.70rem !important;
        color: #71717a !important;
        background: #090a0c !important;
        border: 1px solid #1c1e22 !important;
        padding: 3px 8px !important;
        border-radius: 2px !important;
        margin-top: -4px !important;
        margin-bottom: 12px !important;
        display: inline-flex !important;
        gap: 12px !important;
        max-width: 88% !important;
    }
    .metrics-bar b {
        color: #a1a1aa !important;
    }

    div[data-baseweb="select"] > div {
        background-color: #111317 !important;
        border-color: #27272a !important;
        border-radius: 2px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.80rem !important;
        color: #e2e8f0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_backend_base_url() -> str:
    """Discovers the dynamically bound host port for documind_backend."""
    for test_port in [8888, 8899, 8000]:
        try:
            r = httpx.get(f"http://127.0.0.1:{test_port}/healthz", timeout=0.3)
            if r.status_code == 200:
                return f"http://127.0.0.1:{test_port}"
        except Exception:
            pass

    try:
        cmd = ["docker", "port", "documind_backend", "8888"]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        match = re.search(r":(\d+)$", output)
        if match:
            dyn_port = match.group(1)
            return f"http://127.0.0.1:{dyn_port}"
    except Exception:
        pass

    return "http://127.0.0.1:8888"


BACKEND_BASE_URL = get_backend_base_url()
MODELS_URL = f"{BACKEND_BASE_URL}/summarizer/models"
REGISTRATION_URL = f"{BACKEND_BASE_URL}/summarizer/upload"
STREAM_URL = f"{BACKEND_BASE_URL}/summarizer/upload/stream"
CHAT_URL = f"{BACKEND_BASE_URL}/summarizer/chat"
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"

HISTORY_FILE = "documind_sessions.json"
SOCKET_TIMEOUT = httpx.Timeout(connect=20.0, read=None, write=300.0, pool=60.0)


@st.cache_data(ttl=20)
def fetch_model_directory():
    """Queries backend for installed and recommended Ollama models."""
    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(MODELS_URL)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {
        "installed": ["llama3.2:3b"],
        "recommended": [
            {"name": "llama3.2:3b", "desc": "Lightweight & Fast", "url": "https://ollama.com/library/llama3.2"},
            {"name": "llama3.1:8b", "desc": "Balanced Accuracy", "url": "https://ollama.com/library/llama3.1"},
            {"name": "qwen2.5:7b", "desc": "High Technical Precision", "url": "https://ollama.com/library/qwen2.5"},
            {"name": "mistral:7b", "desc": "Instruction Following", "url": "https://ollama.com/library/mistral"},
            {"name": "deepseek-r1:8b", "desc": "Deep Reasoning", "url": "https://ollama.com/library/deepseek-r1"},
            {"name": "phi4:14b", "desc": "High Logic & Math", "url": "https://ollama.com/library/phi4"},
        ]
    }


def render_metrics_badge(metrics: dict):
    if not metrics:
        return
    ttft = metrics.get("ttft_ms", 0)
    ret_ms = metrics.get("retrieval_ms", 0)
    sim = metrics.get("top_score", 0.0)
    speed = metrics.get("tok_per_sec", 0.0)

    st.markdown(
        f"""
        <div class="metrics-bar">
            <span><b>TTFT:</b> {ttft}ms</span>
            <span><b>RET:</b> {ret_ms}ms</span>
            <span><b>SIM:</b> {sim}</span>
            <span><b>SPEED:</b> {speed} tok/s</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pdf_badges(filenames: list):
    """Renders slideable, un-indented HTML PDF badges."""
    if not filenames:
        return
    badge_items = "".join(
        [
            f'<div class="pdf-badge" title="{str(name).replace('"', "&quot;")}">'
            f'<span class="pdf-icon">PDF</span>'
            f'<span class="pdf-name">{name}</span>'
            f'</div>'
            for name in filenames
        ]
    )
    st.markdown(f'<div class="pdf-card-container">{badge_items}</div>', unsafe_allow_html=True)


def generate_semantic_title(sample_text: str, model: str = "llama3.2:3b") -> str:
    prompt = (
        "Generate a short, concise workspace title (maximum 3 to 5 words) that captures the core subject of this text. "
        "Do NOT use quotes, emojis, punctuation, or conversational filler. Return ONLY the title words.\n\n"
        f"Text excerpt:\n{sample_text[:1200]}"
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.2, "num_ctx": 4096},
        "stream": False,
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(OLLAMA_CHAT_URL, json=payload)
            if resp.status_code == 200:
                title = resp.json().get("message", {}).get("content", "").strip()
                cleaned = title.replace('"', "").replace("'", "").strip()
                return cleaned if cleaned else "WORKSPACE"
    except Exception:
        pass
    return "WORKSPACE"


def load_sessions():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_sessions(sessions):
    tmp_file = f"{HISTORY_FILE}.tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, HISTORY_FILE)
    except Exception as e:
        st.error(f"[SYS_ERR] Failed to persist session data: {e}")


def create_new_workspace():
    new_id = str(uuid.uuid4())
    new_session = {
        "title": "INIT_WORKSPACE",
        "documents": [],
        "messages": [],
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    st.session_state.sessions = {new_id: new_session, **st.session_state.sessions}
    st.session_state.active_session_id = new_id
    save_sessions(st.session_state.sessions)
    return new_id


def delete_workspace(session_id: str):
    if session_id in st.session_state.sessions:
        del st.session_state.sessions[session_id]

        if not st.session_state.sessions:
            create_new_workspace()
        elif st.session_state.active_session_id == session_id:
            st.session_state.active_session_id = list(st.session_state.sessions.keys())[0]

        save_sessions(st.session_state.sessions)
        st.rerun()


@st.dialog("CONFIRM_ACTION")
def confirm_delete_dialog(session_id: str):
    target_title = st.session_state.sessions.get(session_id, {}).get("title", "WORKSPACE")
    st.write(f"DELETE TARGET WORKSPACE: `{target_title}`?")

    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("[CONFIRM]", type="primary", use_container_width=True):
            delete_workspace(session_id)
    with col_no:
        if st.button("[ABORT]", use_container_width=True):
            st.rerun()


def stream_with_metrics(client, url, payload, placeholder):
    t_start = time.perf_counter()
    ttft = None
    telemetry = {}
    ai_text = ""
    token_count = 0

    with client.stream("POST", url, json=payload) as response:
        for chunk in response.iter_bytes():
            if not chunk:
                continue
            raw_text = chunk.decode("utf-8", errors="ignore")

            if raw_text.startswith("__META__"):
                meta_line, _, remainder = raw_text.partition("\n")
                meta_json = meta_line.replace("__META__", "").strip()
                try:
                    telemetry = json.loads(meta_json)
                except Exception:
                    pass
                raw_text = remainder

            if not raw_text:
                continue

            if ttft is None:
                ttft = (time.perf_counter() - t_start) * 1000.0

            token_count += 1
            ai_text += raw_text
            placeholder.markdown(ai_text + "█")

    placeholder.markdown(ai_text)
    t_end = time.perf_counter()

    gen_duration = max(t_end - (t_start + (ttft or 0.0) / 1000.0), 0.001)
    tok_per_sec = round(token_count / gen_duration, 1)

    metrics = {
        "ttft_ms": round(ttft or 0.0, 1),
        "retrieval_ms": telemetry.get("retrieval_ms", 0.0),
        "top_score": telemetry.get("top_score", 0.0),
        "tok_per_sec": tok_per_sec,
    }

    return ai_text, metrics


if "sessions" not in st.session_state:
    st.session_state.sessions = load_sessions()

if "editing_idx" not in st.session_state:
    st.session_state.editing_idx = None

if (
    "active_session_id" not in st.session_state
    or st.session_state.active_session_id not in st.session_state.sessions
):
    if st.session_state.sessions:
        st.session_state.active_session_id = list(st.session_state.sessions.keys())[0]
    else:
        create_new_workspace()

current_session = st.session_state.sessions[st.session_state.active_session_id]

# Auto-migrate legacy format
if "documents" not in current_session:
    current_session["documents"] = []
    if current_session.get("pdf_id") and current_session.get("filename"):
        current_session["documents"].append({
            "id": current_session["pdf_id"],
            "filename": current_session["filename"],
            "file_hash": current_session.get("file_hash", "")
        })

model_dir = fetch_model_directory()
installed_models = model_dir.get("installed", ["llama3.2:3b"])
recommended_models = model_dir.get("recommended", [])

# Sidebar
with st.sidebar:
    st.markdown("### `DOCUMIND`")
    st.caption("v1.2.0 // MULTI-DOC RAG ENGINE")

    if st.button("[+] NEW_WORKSPACE", use_container_width=True, type="primary"):
        create_new_workspace()
        st.session_state.editing_idx = None
        st.rerun()

    st.divider()

    st.caption("ACTIVE_MODEL_ENGINE")
    selected_model = st.selectbox(
        "Active Model:",
        options=installed_models,
        index=0,
        label_visibility="collapsed",
        help="Select any local model installed in your Ollama runtime.",
    )

    with st.expander("GET MORE MODELS"):
        for rec in recommended_models:
            is_installed = any(rec["name"] in inst for inst in installed_models)
            badge = "<span style='color:#4ade80;'>[READY]</span>" if is_installed else "<span style='color:#f87171;'>[NOT PULLED]</span>"
            st.markdown(
                f"""
                <div class="model-card">
                    <b>{rec['name']}</b> {badge}
                    <div class="desc">{rec['desc']}</div>
                    <a href="{rec['url']}" target="_blank">View Model Docs ↗</a>
                </div>
                """,
                unsafe_allow_html=True
            )
            if not is_installed:
                st.code(f"ollama run {rec['name']}", language="bash")

    st.divider()

    st.caption("MOUNTED_DOCUMENTS (MAX 3)")
    if current_session["documents"]:
        for doc in current_session["documents"]:
            raw_fname = doc["filename"]
            display_fname = (raw_fname[:18] + "...") if len(raw_fname) > 21 else raw_fname
            st.markdown(
                f'<div class="pdf-badge" style="max-width:100%; width:100%; margin-bottom:4px;" title="{raw_fname}">'
                f'<span class="pdf-icon">PDF</span><span class="pdf-name">{display_fname}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("[STANDBY] NO_DOCUMENTS_ATTACHED (CHATBOT MODE)")

    st.divider()
    st.caption("SESSION_INDEX")

    for s_id, s_data in list(st.session_state.sessions.items()):
        full_title = s_data.get("title", "UNTITLED")
        is_active = s_id == st.session_state.active_session_id
        btn_type = "secondary" if not is_active else "primary"
        truncated_title = (full_title[:18] + "...") if len(full_title) > 21 else full_title

        col_select, col_del = st.columns([0.86, 0.14])
        with col_select:
            prefix = "> " if is_active else "  "
            if st.button(
                f"{prefix}{truncated_title}",
                key=f"btn_{s_id}",
                use_container_width=True,
                type=btn_type,
                help=full_title,
            ):
                if not is_active:
                    st.session_state.active_session_id = s_id
                    st.session_state.editing_idx = None
                    st.rerun()
        with col_del:
            if st.button(
                "×",
                key=f"del_{s_id}",
                use_container_width=True,
                help=f"Delete '{full_title}'",
            ):
                confirm_delete_dialog(s_id)

st.markdown(f"## `DOCUMIND // {current_session['title']}`")

# Render Timeline
idx = 0
while idx < len(current_session["messages"]):
    msg = current_session["messages"][idx]
    is_user = msg["role"] == "user"

    if is_user and st.session_state.editing_idx == idx:
        with st.container():
            st.markdown(f"**`>_ EDIT PROMPT #{idx + 1}`**")
            with st.form(key=f"edit_form_{idx}"):
                edited_text = st.text_area("PROMPT_BUFFER:", value=msg["content"], height=90)
                col_save, col_cancel = st.columns([0.3, 0.7])
                with col_save:
                    save_clicked = st.form_submit_button("[REGENERATE]", type="primary", use_container_width=True)
                with col_cancel:
                    cancel_clicked = st.form_submit_button("[CANCEL]", use_container_width=True)

                if save_clicked and edited_text.strip():
                    clean_text = edited_text.strip()
                    current_session["messages"] = current_session["messages"][:idx]
                    current_session["messages"].append({
                        "role": "user",
                        "content": clean_text,
                        "files": msg.get("files", [])
                    })
                    st.session_state.editing_idx = None
                    save_sessions(st.session_state.sessions)

                    history_payload = [
                        {"role": m["role"], "content": m["content"]}
                        for m in current_session["messages"][:-1]
                        if m["role"] in ["user", "assistant"]
                    ]

                    active_doc_ids = [d["id"] for d in current_session.get("documents", [])]

                    with st.chat_message("assistant"):
                        placeholder = st.empty()
                        payload = {
                            "pdf_ids": active_doc_ids,
                            "question": clean_text,
                            "history": history_payload,
                            "model": selected_model,
                        }
                        try:
                            with httpx.Client(timeout=SOCKET_TIMEOUT) as client:
                                ai_response, metrics = stream_with_metrics(client, CHAT_URL, payload, placeholder)
                                render_metrics_badge(metrics)
                            current_session["messages"].append({
                                "role": "assistant",
                                "content": ai_response,
                                "metrics": metrics,
                            })
                            save_sessions(st.session_state.sessions)
                        except Exception as e:
                            st.error(f"[EXEC_ERR] Query failed: {str(e)}")

                    st.rerun()

                elif cancel_clicked:
                    st.session_state.editing_idx = None
                    st.rerun()

    else:
        with st.chat_message(msg["role"]):
            if is_user and msg.get("files"):
                render_pdf_badges(msg["files"])
            st.markdown(msg["content"])

        if msg["role"] == "assistant" and msg.get("metrics"):
            render_metrics_badge(msg["metrics"])

        if is_user:
            col_spacer, col_copy, col_edit = st.columns([0.76, 0.12, 0.12])
            with col_copy:
                if st.button("[COPY]", key=f"cp_{idx}", help="Copy prompt"):
                    st.toast("Prompt buffered.")
            with col_edit:
                if st.button("[EDIT]", key=f"ed_{idx}", help="Edit prompt and re-branch"):
                    st.session_state.editing_idx = idx
                    st.rerun()

    idx += 1

# Chat Input
prompt_input = st.chat_input(
    "Write your prompt here...",
    accept_file="multiple",
    file_type=["pdf"],
)

if prompt_input:
    user_text = (
        prompt_input.text
        if hasattr(prompt_input, "text") and prompt_input.text
        else ""
    )
    attached_files = (
        prompt_input.files
        if hasattr(prompt_input, "files") and prompt_input.files
        else []
    )

    if attached_files:
        existing_hashes = {d.get("file_hash") for d in current_session.get("documents", [])}
        existing_names = {d.get("filename") for d in current_session.get("documents", [])}

        newly_attached = []
        for f in attached_files:
            f_bytes = f.getvalue()
            f_hash = hashlib.sha256(f_bytes).hexdigest()
            if f_hash not in existing_hashes and f.name not in existing_names:
                if len(current_session["documents"]) + len(newly_attached) < 3:
                    newly_attached.append((f, f_bytes, f_hash))

        file_names = [f[0].name for f in newly_attached] if newly_attached else [f.name for f in attached_files[:3]]

        display_prompt = user_text if user_text else f"Analyze and summarize the contents of: {', '.join(file_names)}"
        current_session["messages"].append({
            "role": "user",
            "content": display_prompt,
            "files": file_names
        })
        current_session["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_sessions(st.session_state.sessions)

        with st.chat_message("user"):
            render_pdf_badges(file_names)
            st.markdown(display_prompt)

        # Ingest newly attached PDFs
        if newly_attached:
            files_payload = [
                ("files", (f_item[0].name, f_item[1], "application/pdf"))
                for f_item in newly_attached
            ]

            status_box = st.empty()
            status_box.markdown(
                """
                <div class="pipeline-status">
                    <span>⚡</span> <span><b>[01/03]</b> INGESTING & PARSING PDF DOCUMENT AST...</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            try:
                with httpx.Client(timeout=SOCKET_TIMEOUT) as client:
                    upload_res = client.post(REGISTRATION_URL, files=files_payload)
                    if upload_res.status_code in [200, 201]:
                        records = upload_res.json()
                        for rec, f_item in zip(records, newly_attached):
                            current_session["documents"].append({
                                "id": rec.get("id"),
                                "filename": rec.get("filename"),
                                "file_hash": f_item[2]
                            })
                        save_sessions(st.session_state.sessions)
                    else:
                        st.error(f"[ERR] Backend rejected upload: {upload_res.text}")
            except Exception as e:
                st.error(f"[ERR] Document registration failed: {str(e)}")

            status_box.markdown(
                f"""
                <div class="pipeline-status">
                    <span>🧠</span> <span><b>[02/03]</b> COMPUTING HYBRID BM25 + DENSE EMBEDDINGS & SYNTHESIZING ({selected_model})...</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            with st.chat_message("assistant"):
                ai_response = ""
                placeholder = st.empty()
                form_data = {"model": selected_model}
                if user_text:
                    form_data["custom_prompt"] = user_text

                try:
                    t0 = time.perf_counter()
                    ttft = None
                    tokens = 0
                    with httpx.Client(timeout=SOCKET_TIMEOUT) as client:
                        with client.stream(
                            "POST", STREAM_URL, files=files_payload, data=form_data
                        ) as response:
                            status_box.empty()
                            for chunk in response.iter_bytes():
                                if chunk:
                                    if ttft is None:
                                        ttft = (time.perf_counter() - t0) * 1000.0
                                    tokens += 1
                                    token = chunk.decode("utf-8", errors="ignore")
                                    ai_response += token
                                    placeholder.markdown(ai_response + "█")

                    placeholder.markdown(ai_response)
                    t1 = time.perf_counter()

                    speed = round(tokens / max(t1 - (t0 + (ttft or 0.0) / 1000.0), 0.001), 1)
                    metrics = {
                        "ttft_ms": round(ttft or 0.0, 1),
                        "retrieval_ms": 0.0,
                        "top_score": 1.0,
                        "tok_per_sec": speed,
                    }
                    render_metrics_badge(metrics)

                    current_session["messages"].append({
                        "role": "assistant",
                        "content": ai_response,
                        "metrics": metrics,
                    })

                    if ai_response:
                        semantic_title = generate_semantic_title(ai_response, model=selected_model)
                        current_session["title"] = semantic_title

                    save_sessions(st.session_state.sessions)
                    st.rerun()

                except Exception as e:
                    status_box.empty()
                    st.error(f"[EXEC_ERR] Synthesis failed: {str(e)}")

        else:
            # Files already present in workspace -> Multi-Doc Q&A
            history_payload = [
                {"role": m["role"], "content": m["content"]}
                for m in current_session["messages"][:-1]
                if m["role"] in ["user", "assistant"]
            ]
            active_doc_ids = [d["id"] for d in current_session.get("documents", [])]

            with st.chat_message("assistant"):
                placeholder = st.empty()
                payload = {
                    "pdf_ids": active_doc_ids,
                    "question": display_prompt,
                    "history": history_payload,
                    "model": selected_model,
                }
                try:
                    with httpx.Client(timeout=SOCKET_TIMEOUT) as client:
                        ai_response, metrics = stream_with_metrics(client, CHAT_URL, payload, placeholder)
                        render_metrics_badge(metrics)
                    current_session["messages"].append({
                        "role": "assistant",
                        "content": ai_response,
                        "metrics": metrics,
                    })
                    save_sessions(st.session_state.sessions)
                except Exception as e:
                    st.error(f"[EXEC_ERR] Query failed: {str(e)}")

    else:
        # General Chatbot Mode
        current_session["messages"].append({"role": "user", "content": user_text})
        save_sessions(st.session_state.sessions)

        with st.chat_message("user"):
            st.markdown(user_text)

        history_payload = [
            {"role": m["role"], "content": m["content"]}
            for m in current_session["messages"][:-1]
            if m["role"] in ["user", "assistant"]
        ]

        active_doc_ids = [d["id"] for d in current_session.get("documents", [])]

        with st.chat_message("assistant"):
            placeholder = st.empty()
            payload = {
                "pdf_ids": active_doc_ids,
                "question": user_text,
                "history": history_payload,
                "model": selected_model,
            }

            try:
                with httpx.Client(timeout=SOCKET_TIMEOUT) as client:
                    ai_response, metrics = stream_with_metrics(client, CHAT_URL, payload, placeholder)
                    render_metrics_badge(metrics)
                current_session["messages"].append({
                    "role": "assistant",
                    "content": ai_response,
                    "metrics": metrics,
                })
                save_sessions(st.session_state.sessions)
            except Exception as e:
                st.error(f"[EXEC_ERR] Query failed: {str(e)}")