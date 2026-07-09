
# DocuMind-Local

DocuMind-Local is an enterprise-grade, localized multi-container AI application designed to process, chunk, and summarize complex PDF documents without letting data leave your host machine. Featuring an asynchronous FastAPI backend paired with an interactive Streamlit UI, it handles both digital text parsing and scanned image layouts via a robust fallback OCR engine, leveraging an isolated local LLM orchestration framework.

---

## 🏗️ Architecture Overview

The application is engineered as a decoupled, multi-service environment orchestrated entirely via Docker:

* **Frontend UI (Streamlit):** Provides an interactive dashboard, drag-and-drop file uploaders, and an asynchronous conversational chat window.
* **Backend API (FastAPI):** Orchestrates PDF processing, manages local storage paths, handles SQLite database states, and coordinates chunks via custom text-splitting metrics.
* **Local LLM Node (Ollama):** A dedicated Linux-based container managing neural model states and serving token streaming pipes internally without external API dependencies.
* **OCR Layer (Tesseract):** Automated system-level pipeline that kicks in whenever a document lacks a native digital text layer.

---

## 🚀 Getting Started

Follow these instructions to spin up the entire ecosystem on your local machine.

### 📋 Prerequisites

Ensure you have the following installed on your host system:
* [Docker Desktop](https://www.docker.com/products/docker-desktop/)
* Python 3.10+ (if running the frontend natively outside Docker)

> **⚠️ Network Note for Restricted Regions:** If you are running this from a country with Docker Hub access restrictions (e.g., Iran), ensure your system proxy/VPN is active before building the containers to prevent `403 Forbidden` connection drops during base image registration.

---

### 🛠️ Installation & Setup

#### 1. Clone and Navigate to the Workspace
```bash
git clone [https://github.com/ErphanRajai/DocuMind-Local.git](https://github.com/ErphanRajai/DocuMind-Local.git)
cd DocuMind-Local

```

#### 2. Launch the Core Infrastructure (Backend & AI Engine)

Run Docker Compose from the root directory to build the core services. This setup automatically configures the volumes and triggers an automated script container to download the `llama3.2:3b` model weights directly into your Docker storage layer.

```bash
docker compose up -d

```

To verify that the infrastructure is up and healthy, run:

```bash
docker ps

```

You should see `pdf_backend` listening on port `8888` and `ollama_node` listening on port `11434`.

#### 3. Initialize the Frontend Interface

Open a **new, separate terminal window** and navigate to the frontend directory:

```bash
cd pdf-summarizer-frontend

```

Choose the environment setup option that matches your local system configuration below:

##### Option A: Using a Standard Python Virtual Environment (Windows / Mac / Linux)

```bash
# 1. Create the virtual environment
python -m venv front_env

# 2. Activate the environment
# For Windows (PowerShell):
front_env\Scripts\activate
# For Mac / Linux:
source front_env/bin/activate

# 3. Install core client dependencies
pip install streamlit httpx

# 4. Boot the app interface
streamlit run app.py --server.port 8550 --server.address 127.0.0.1

```

##### Option B: Using an Anaconda / Miniconda Environment

```bash
# 1. Activate your conda base environment (or your preferred named env)
conda activate base

# 2. Install core client dependencies
pip install streamlit httpx

# 3. Boot the app interface
streamlit run app.py --server.port 8550 --server.address 127.0.0.1

```

Once the application initializes, your web browser will automatically open to:
👉 **`http://127.0.0.1:8550`**

---

## 🧪 Verification Protocol (How to Test)

1. **Digital Document Streaming:** Upload a standard text-selectable PDF and click **"Process & Summarize Document"**. The text will chunk automatically, save to the local SQL state, and stream the summary token-by-token down the chat window.
2. **Scanned PDF Fallback (OCR):** Upload a document that is purely a scanned image or photo. The backend will catch the empty layer, print `DEBUG: Digital text layer missing. Launching OCR...` in your Docker console, parse the pixels using Tesseract, and return a clean textual summary.
3. **Conversational Follow-up:** Type a contextual prompt in the bottom chat interface (e.g., *"What was the exact percentage mentioned in section 2?"*) to test the persistent memory/RAG layer.

---

## 📂 Project Structure

```text
DocuMind-Local/
│
├── pdf-summarizer-backend/     # FastAPI Service Layer
│   ├── app/                    # Endpoints, Services, & Database Models
│   ├── tests/                  # Isolated Test Harnesses / Sanity Scripts
│   └── Dockerfile              # Linux compilation template (Python + Tesseract)
│
├── pdf-summarizer-frontend/    # Streamlit User Workspace
│   └── app.py                  # UI layout and network streaming pipelines
│
├── docker-compose.yml          # Global multi-service orchestration layout
└── .gitignore                  # Active tracking exceptions (Blocks local environments/DBs)

```

---

## 🔒 Security & Best Practices

* **No Hardcoded Secrets:** All system routing parameters use flexible environment definitions (`os.getenv`), falling back to local loops if empty.
* **Strict Volumetric Mapping:** Active databases (`pdf_summarizer.db`) and target PDF assets stay locked inside isolated volumes, completely filtered out of remote Git records via structural ignore parameters.

---

```

```
