
# DocuMind-Local: Privacy-First Document AI & RAG Pipeline

DocuMind-Local is an enterprise-grade, fully localized Retrieval-Augmented Generation (RAG) application designed to process, chunk, and summarize complex PDF documents. Built with a strict **zero-data-leakage philosophy**, this system ensures that your documents never leave your host machine. There are no API keys, no paywalls, and no external tracking—just a 100% free, secure, and private AI ecosystem running directly on your hardware.

## Architecture Overview

The application is engineered as a decoupled, high-performance environment, separating the heavy ML inference from the service orchestration to maximize GPU efficiency:

* **Host-Native LLM Engine (Ollama):** Removed from the Docker network to run natively on the host OS. This architectural decision bypasses Docker's virtualization layer, granting the AI models direct, unhindered access to native GPU drivers (Nvidia/Apple Silicon) for maximum inference speed.
* **Vector Storage Engine (Qdrant):** A dedicated, containerized vector database that stores high-dimensional embeddings. It powers the semantic search capabilities of the RAG pipeline, ensuring the LLM has accurate, mathematically grounded context for every query.
* **Backend API (FastAPI):** An asynchronous orchestration layer handling PDF processing, advanced text-chunking algorithms, vector indexing, and fallback OCR capabilities (via Tesseract) for scanned documents.
* **Frontend UI (Streamlit):** An interactive dashboard providing drag-and-drop file uploaders, real-time token streaming, and an intuitive conversational interface.

## Prerequisites

Ensure you have the following installed on your host system:
* **Docker Desktop** (For orchestrating the backend and vector database)
* **Python 3.10+** (For running the Streamlit client)
* **Ollama** (For local LLM and embedding generation)

> **Network Note for Restricted Regions:** If you are running this entirely entirely behind a strict firewall or in a region with Docker Hub access restrictions, ensure your system proxy/VPN is active during the initial Docker build to prevent `403 Forbidden` errors.

## Installation & Setup

### Step 1: Initialize the Local AI Engine
To ensure maximum performance and native hardware acceleration, install Ollama directly on your machine rather than inside a container.

1. Download and install Ollama from [ollama.com](https://ollama.com).
2. Open your host terminal and pull the required models into your local cache. We use Llama 3.2 for summarization/chat and Nomic for vector embeddings:

```bash
ollama pull llama3.2
ollama pull nomic-embed-text
```

### Step 2: Clone the Repository

```bash
git clone [https://github.com/ErphanRajai/DocuMind-Local.git](https://github.com/ErphanRajai/DocuMind-Local.git)
cd DocuMind-Local

```

### Step 3: Launch the Core Infrastructure

Run Docker Compose from the root directory to build the FastAPI backend and Qdrant vector database. The backend is configured to automatically bridge the container network to your host machine's Ollama instance via `host.docker.internal`.

```bash
docker compose up -d --build

```

*Note: To shut down the infrastructure later, use `docker compose down`.*

### Step 4: Initialize the Frontend Interface

Open a **new, separate terminal window**, navigate to the frontend directory, and set up your Python environment.

#### Option A: Using standard venv (Windows/Mac/Linux)

```bash
cd pdf-summarizer-frontend
python -m venv front_env

# Windows (PowerShell):
front_env\Scripts\activate
# Mac / Linux:
source front_env/bin/activate

pip install streamlit httpx
streamlit run app.py --server.port 8550 --server.address 127.0.0.1

```

#### Option B: Using Anaconda / Miniconda

```bash
cd pdf-summarizer-frontend
conda activate base # Or your dedicated conda env

pip install streamlit httpx
streamlit run app.py --server.port 8550 --server.address 127.0.0.1

```

Your web browser will automatically open to: **`http://127.0.0.1:8550`**

## Verification Protocol (How to Test)

1. **Vector Indexing & RAG:** Upload a standard, text-selectable PDF. The backend will automatically parse the document, generate chunks, extract semantic embeddings via `nomic-embed-text`, and index them into Qdrant.
2. **Scanned PDF Fallback (OCR):** Upload a purely image-based PDF. The backend will automatically detect the missing digital layer, trigger the Tesseract OCR engine, extract the text, and proceed with the RAG pipeline.
3. **Conversational AI:** Use the chat interface to ask specific questions about the uploaded document. The system will query the Qdrant database for the most relevant vectors and stream the synthesized answer back to the UI in real-time.

## Project Structure

```text
DocuMind-Local/
├── pdf-summarizer-backend/     # FastAPI Service Layer
│   ├── app/                    # Routing, LLM Services, and RAG Logic
│   └── Dockerfile              # Container compilation template (Python + Tesseract)
├── pdf-summarizer-frontend/    # Streamlit User Workspace
│   └── app.py                  # UI layout and async network streaming pipelines
├── docker-compose.yml          # Container orchestration (FastAPI + Qdrant)
└── .gitignore                  # Active tracking exceptions (Blocks databases/environments)

```

## Security & Best Practices

* **Air-Gapped Capability:** Once the Docker images and Ollama models are cached locally, this application requires zero internet connection to function.
* **Volume Isolation:** The Qdrant vector database is mapped to a strictly isolated local volume (`qdrant_storage`), which is ignored by Git to prevent accidental leakage of proprietary document data.
* **Dynamic Routing:** All API cross-talk is handled via environment variables (`OLLAMA_API_URL`, `QDRANT_HOST`), preventing hardcoded vulnerability vectors.

```

```