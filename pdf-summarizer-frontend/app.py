import hashlib
import html
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx
import streamlit as st

st.set_page_config(page_title="DocuMind", page_icon="✦", layout="wide", initial_sidebar_state="auto")

# Keep the visual system in one stylesheet, rather than layered overrides.
CSS_FILE = Path(__file__).with_name("ui.css")
st.markdown(f"<style>{CSS_FILE.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


@st.cache_resource
def get_backend_base_url() -> str:
    """Return the configured local API address."""
    return os.getenv("DOCUMIND_BACKEND_URL", "http://127.0.0.1:8888").rstrip("/")


BACKEND_BASE_URL = get_backend_base_url()
HEALTH_URL = f"{BACKEND_BASE_URL}/healthz"
MODELS_URL = f"{BACKEND_BASE_URL}/summarizer/models"
REGISTRATION_URL = f"{BACKEND_BASE_URL}/summarizer/upload"
STREAM_URL = f"{BACKEND_BASE_URL}/summarizer/upload/stream"
CHAT_URL = f"{BACKEND_BASE_URL}/summarizer/chat"
HISTORY_FILE = os.getenv(
    "DOCUMIND_HISTORY_FILE",
    str(Path(__file__).resolve().parents[1] / "documind_sessions.json"),
)
SOCKET_TIMEOUT = httpx.Timeout(connect=20.0, read=None, write=300.0, pool=60.0)


@st.cache_data(ttl=15)
def fetch_backend_health():
    try:
        response = httpx.get(HEALTH_URL, timeout=2.0)
        if response.status_code == 200:
            return response.json()
    except httpx.HTTPError:
        pass
    return {"status": "offline", "qdrant": "unknown", "ollama": "unknown"}


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
    if not metrics or not st.session_state.get("show_response_details", False):
        return
    ttft = metrics.get("ttft_ms", 0)
    ret_ms = metrics.get("retrieval_ms", 0)

    st.markdown(
        f"""
        <div class="metrics-bar">
            <span><b>First response:</b> {ttft} ms</span>
            <span><b>Document search:</b> {ret_ms} ms</span>
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
            f'<div class="pdf-badge" title="{html.escape(str(name), quote=True)}">'
            f'<span class="pdf-icon">PDF</span>'
            f'<span class="pdf-name">{html.escape(str(name))}</span>'
            f'</div>'
            for name in filenames
        ]
    )
    st.markdown(f'<div class="pdf-card-container">{badge_items}</div>', unsafe_allow_html=True)


def generate_semantic_title(sample_text: str, model: str = "llama3.2:3b") -> str:
    """Create a workspace label locally without an extra model round trip."""
    del model
    text = " ".join(sample_text.strip().split())
    if not text:
        return "New workspace"
    sentence = text.split(". ", 1)[0]
    return sentence[:38].rstrip(" ,:;.-") + ("…" if len(sentence) > 38 else "")


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
        st.error(f"Could not save workspace history: {e}")


def create_new_workspace():
    new_id = str(uuid.uuid4())
    new_session = {
        "title": "New workspace",
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


@st.dialog("Delete workspace?")
def confirm_delete_dialog(session_id: str):
    target_title = st.session_state.sessions.get(session_id, {}).get("title", "WORKSPACE")
    st.write(f"Delete **{target_title}** and its chat history?")

    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("Delete", type="primary", use_container_width=True):
            delete_workspace(session_id)
    with col_no:
        if st.button("Cancel", use_container_width=True):
            st.rerun()


def response_text_chunks(response, telemetry):
    """Decode incremental UTF-8 and handle a metadata header split across packets."""
    response.raise_for_status()
    pending = ""
    header_done = False
    for text in response.iter_text():
        if not header_done:
            pending += text
            if "__META__".startswith(pending):
                continue
            if pending.startswith("__META__"):
                if "\n" not in pending:
                    continue
                header, _, text = pending.partition("\n")
                try:
                    telemetry.update(json.loads(header[len("__META__"):]))
                except (ValueError, TypeError):
                    pass
            else:
                text = pending
            pending = ""
            header_done = True
        if text:
            yield text
    if pending and not pending.startswith("__META__"):
        yield pending


def stream_with_metrics(client, url, payload, placeholder):
    t_start = time.perf_counter()
    ttft = None
    telemetry = {}
    ai_text = ""
    token_count = 0
    last_render = 0.0

    with client.stream("POST", url, json=payload) as response:
        for raw_text in response_text_chunks(response, telemetry):
            if ttft is None:
                ttft = (time.perf_counter() - t_start) * 1000.0

            token_count += 1
            ai_text += raw_text
            now = time.perf_counter()
            if now - last_render >= 0.04:
                placeholder.markdown(ai_text + " ▍")
                last_render = now

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
installed_models = model_dir.get("installed", [])
if not installed_models:
    installed_models = ["llama3.2:3b"]
recommended_models = model_dir.get("recommended", [])
backend_health = fetch_backend_health()

# A quiet navigation rail keeps history and documents close to the conversation.
with st.sidebar:
    st.markdown(
        '<div class="sidebar-brand"><span class="brand-symbol">✦</span>'
        '<div><div class="brand-name">DocuMind</div>'
        '<div class="brand-caption">A little clarity, every day</div></div></div>',
        unsafe_allow_html=True,
    )
    if st.button("New workspace", icon=":material/add:", use_container_width=True, type="primary"):
        create_new_workspace()
        st.session_state.editing_idx = None
        st.rerun()

    workspace_search = st.text_input(
        "Search conversations", placeholder="Search conversations…", label_visibility="collapsed",
        key="workspace_search",
    )
    st.markdown('<div class="sidebar-section-label">Recent conversations</div>', unsafe_allow_html=True)
    with st.container(key="workspace-list"):
        matches = [
            (s_id, s_data) for s_id, s_data in st.session_state.sessions.items()
            if workspace_search.lower() in s_data.get("title", "New workspace").lower()
        ]
        visible_count = st.session_state.get("visible_conversations", 8)
        for s_id, s_data in matches[:visible_count]:
            full_title = s_data.get("title") or "New workspace"
            is_active = s_id == st.session_state.active_session_id
            with st.container(key=f"{'active-workspace' if is_active else 'workspace'}-{s_id}"):
                if st.button(
                    full_title[:31] + ("…" if len(full_title) > 31 else ""),
                    key=f"btn_{s_id}", icon=":material/chat_bubble_outline:",
                    use_container_width=True, help=full_title,
                ) and not is_active:
                    st.session_state.active_session_id = s_id
                    st.session_state.editing_idx = None
                    st.rerun()
        if not matches:
            st.caption("No conversations found.")
        elif len(matches) > visible_count:
            if st.button("Show more", use_container_width=True):
                st.session_state.visible_conversations = visible_count + 8
                st.rerun()

    st.divider()
    with st.expander(f"Documents · {len(current_session['documents'])}/3", expanded=bool(current_session['documents'])):
        if current_session["documents"]:
            render_pdf_badges([doc["filename"] for doc in current_session["documents"]])
        else:
            st.caption("Use the + button in the message box to attach a PDF. Send it without a question to get a summary.")

    with st.container(key="sidebar-tools"):
        healthy = backend_health.get("status") == "healthy"
        st.markdown(
            f'<div class="connection-row"><span class="connection-dot {"good" if healthy else "warn"}"></span>'
            f'{"Local services ready" if healthy else "Check your connection"}</div>',
            unsafe_allow_html=True,
        )
        with st.expander("Connection & details"):
            st.caption(f"Backend: {backend_health.get('status', 'unknown')}")
            st.caption(f"Document search: {backend_health.get('qdrant', 'unknown')}")
            st.caption(f"Ollama: {backend_health.get('ollama', 'unknown')}")
            st.toggle("Show response details", key="show_response_details")
            if st.button("Refresh connection", icon=":material/refresh:", use_container_width=True):
                fetch_backend_health.clear()
                fetch_model_directory.clear()
                st.rerun()

# Model settings are available from the top of the workspace without filling the sidebar.
def render_model_controls():
    model_source = st.selectbox(
        "Model source", ["Local · Ollama", "API key · OpenAI-compatible"], key="model_source",
    )
    if model_source.startswith("Local"):
        default_model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:3b")
        if st.session_state.get("local_chat_model") not in installed_models:
            st.session_state.local_chat_model = default_model if default_model in installed_models else installed_models[0]
        selected_model = st.selectbox("Chat model", installed_models, key="local_chat_model")
        provider_settings = {"provider": "ollama"}
        st.caption("Your prompts and documents stay on this computer.")
        with st.expander("Add another local model"):
            st.caption("Download a model with Ollama, then refresh the connection in the sidebar.")
            st.code("ollama pull llama3.2:3b", language="bash")
    else:
        st.session_state.setdefault("api_base_url", "https://api.openai.com/v1")
        st.session_state.setdefault("api_model", "gpt-4o-mini")
        api_base_url = st.text_input("API base URL", key="api_base_url", placeholder="https://api.openai.com/v1")
        selected_model = st.text_input("Model ID", key="api_model", placeholder="Your provider's model ID")
        api_key = st.text_input("API key", type="password", key="provider_api_key", placeholder="Paste your API key")
        provider_settings = {"provider": "openai-compatible", "api_base_url": api_base_url.strip(), "api_key": api_key}
        st.caption("Your key is kept only in this session. Messages and relevant document text are sent to your chosen provider.")
    return model_source, selected_model, provider_settings

with st.container(key="chat-toolbar"):
    model_column, options_column = st.columns([0.78, 0.22])
    with model_column:
        preferred_local_model = st.session_state.get("local_chat_model") or os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:3b")
        local_model_label = preferred_local_model if preferred_local_model in installed_models else installed_models[0]
        model_label = (
            st.session_state.get("api_model") or "Connect a model"
            if st.session_state.get("model_source", "Local").startswith("API key")
            else local_model_label
        )
        with st.popover(model_label, icon=":material/auto_awesome:", help="Choose a model or connect an API", key="model-picker"):
            st.markdown("**Choose your model**")
            model_source, selected_model, provider_settings = render_model_controls()
    with options_column:
        with st.popover("Workspace", icon=":material/more_horiz:", use_container_width=True):
            workspace_title = st.text_input("Workspace name", value=current_session.get("title", "New workspace"), key=f"rename-{st.session_state.active_session_id}")
            if st.button("Save name", use_container_width=True):
                current_session["title"] = workspace_title.strip() or "New workspace"
                save_sessions(st.session_state.sessions)
                st.rerun()
            transcript = "\n\n".join(f"{m['role'].title()}\n{m['content']}" for m in current_session["messages"])
            st.download_button("Download conversation", transcript, file_name="documind-conversation.txt", use_container_width=True)
            if st.button("Delete workspace", icon=":material/delete_outline:", use_container_width=True):
                confirm_delete_dialog(st.session_state.active_session_id)

is_empty_workspace = not current_session["messages"]
if is_empty_workspace:
    st.markdown(
        '<div class="workspace-hero"><div class="hero-symbol" aria-hidden="true"></div>'
        '<div class="hero-kicker">YOUR SPACE TO THINK</div>'
        '<h1>What would you like<br>to <span class="hero-accent">understand?</span></h1>'
        '<p class="hero-copy">Bring a document. Ask a question.<br>Find the details that matter.</p></div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(f"## {html.escape(current_session.get('title') or 'Your conversation')}")
    st.markdown(
        f'<div class="workspace-meta">{len(current_session["documents"])} document(s) · {html.escape(selected_model)}</div>',
        unsafe_allow_html=True,
    )

# Render Timeline
idx = 0
while idx < len(current_session["messages"]):
    msg = current_session["messages"][idx]
    is_user = msg["role"] == "user"

    if is_user and st.session_state.editing_idx == idx:
        with st.container():
            st.markdown(f"**Edit question {idx + 1}**")
            with st.form(key=f"edit_form_{idx}"):
                edited_text = st.text_area("Your message", value=msg["content"], height=90)
                col_save, col_cancel = st.columns([0.5, 0.5])
                with col_save:
                    save_clicked = st.form_submit_button("Save and regenerate", type="primary", use_container_width=True)
                with col_cancel:
                    cancel_clicked = st.form_submit_button("Cancel", use_container_width=True)

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
                            **provider_settings,
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
                            st.error(f"Could not get a response: {str(e)}")

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
            with st.container(horizontal=True, horizontal_alignment="right", key=f"message-actions-{idx}"):
                with st.popover("Copy", icon=":material/content_copy:", help="Copy this question"):
                    st.code(msg["content"], language=None)
                if st.button("Edit", key=f"ed_{idx}", icon=":material/edit:", type="tertiary", help="Edit this question and regenerate"):
                    st.session_state.editing_idx = idx
                    st.rerun()

    idx += 1

# The first composer sits beneath the welcome; active chats keep it at the bottom.
def render_composer():
    return st.chat_input(
        "Ask a question, or attach a PDF…", key="chat_composer", accept_file="multiple",
        file_type=["pdf"], max_upload_size=50, height=120 if is_empty_workspace else "content",
    )


def draft_prompt(text):
    st.session_state.chat_composer = text


if is_empty_workspace:
    with st.container(key="welcome-composer"):
        prompt_input = render_composer()
        st.markdown('<div class="composer-note">Attach up to 3 PDFs · 50 MB per file · Enter to send</div>', unsafe_allow_html=True)
    with st.container(key="quick-starts"):
        starter_columns = st.columns(3)
        for column, label, icon, text in zip(
            starter_columns,
            ["Summarize a document", "Find key takeaways", "Compare documents"],
            [":material/description:", ":material/lightbulb:", ":material/compare_arrows:"],
            ["Summarize the attached document clearly and concisely.", "What are the key takeaways from the attached document?", "Compare the attached documents and explain the main differences."],
        ):
            with column:
                st.button(label, icon=icon, use_container_width=True, on_click=draft_prompt, args=(text,))
else:
    prompt_input = render_composer()

if prompt_input:
    if model_source.startswith("API key") and (not selected_model.strip() or not provider_settings.get("api_key")):
        st.error("Open the model picker above and enter your model ID and API key.")
        st.stop()

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
        existing_docs = current_session.get("documents", [])
        existing_hashes = {d.get("file_hash") for d in existing_docs}
        existing_names = {d.get("filename") for d in existing_docs}

        newly_attached = []
        unique_upload_count = 0
        matched_existing = []
        for f in attached_files:
            f_bytes = f.getvalue()
            f_hash = hashlib.sha256(f_bytes).hexdigest()
            if f_hash in existing_hashes or f.name in existing_names:
                if f.name in existing_names and f.name not in matched_existing:
                    matched_existing.append(f.name)
                continue

            if all(item[0].name != f.name for item in newly_attached):
                unique_upload_count += 1
                if len(current_session["documents"]) + len(newly_attached) < 3:
                    newly_attached.append((f, f_bytes, f_hash))
                    existing_hashes.add(f_hash)
                    existing_names.add(f.name)

        remaining_slots = max(0, 3 - len(current_session["documents"]))
        if unique_upload_count > remaining_slots:
            st.warning(f"This workspace can hold 3 PDFs. Only the first {remaining_slots} new file(s) were added.")

        file_names = (
            [f[0].name for f in newly_attached]
            if newly_attached
            else matched_existing[:3]
        )

        default_prompt = (
            f"Analyze and summarize the contents of: {', '.join(file_names)}"
            if file_names
            else "Analyze and summarize the documents already attached to this workspace."
        )
        display_prompt = user_text or default_prompt
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
                    <span>✦</span> <span>Reading your PDFs…</span>
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
                        st.error(f"Could not upload your PDF: {upload_res.text}")
            except Exception as e:
                st.error(f"Could not upload your PDF: {str(e)}")

            status_box.markdown(
                f"""
                <div class="pipeline-status">
                    <span>✦</span> <span>Preparing your answer…</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            with st.chat_message("assistant"):
                ai_response = ""
                placeholder = st.empty()
                form_data = {"model": selected_model}
                form_data.update(provider_settings)
                if user_text:
                    form_data["custom_prompt"] = user_text

                try:
                    t0 = time.perf_counter()
                    ttft = None
                    tokens = 0
                    last_render = 0.0
                    with httpx.Client(timeout=SOCKET_TIMEOUT) as client:
                        with client.stream(
                            "POST", STREAM_URL, files=files_payload, data=form_data
                        ) as response:
                            status_box.empty()
                            for token in response_text_chunks(response, {}):
                                if ttft is None:
                                    ttft = (time.perf_counter() - t0) * 1000.0
                                tokens += 1
                                ai_response += token
                                now = time.perf_counter()
                                if now - last_render >= 0.04:
                                    placeholder.markdown(ai_response + " ▍")
                                    last_render = now

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
                    st.error(f"Could not prepare an answer: {str(e)}")

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
                    **provider_settings,
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
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not get a response: {str(e)}")

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
                **provider_settings,
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
                st.rerun()
            except Exception as e:
                st.error(f"Could not get a response: {str(e)}")
