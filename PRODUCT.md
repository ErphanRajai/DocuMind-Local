# DocuMind
<!-- impeccable:product-schema 1 -->
## Platform
web
## Stack
Existing FastAPI, SQLite, Qdrant and Ollama backend. User explicitly requests Next.js and TypeScript frontend replacing the primary Streamlit experience; keep Streamlit as a fallback.
## Users
People reading and asking questions about their PDFs on a local computer. Research-workbench emphasis inferred from the delegated redesign brief; no institutional audience is claimed.
## Product Purpose
Answer homework/exam question PDFs from uploaded source PDFs, including books over 100 pages, in the exam language. Direct answers with inspectable evidence are primary; tutoring is optional and secondary.
## Operating Context
Local Windows application; Docker backend and search, local Ollama. Upload at most three PDFs per batch, 50MB each. Selected local model and 8192-token context remain supported. Optional compatible providers already exist.
## Capabilities and Constraints
Upload once, bounded extraction/OCR, indexed page sources, streamed answers, clickable citations. New scope: follow-up retrieval, complete reviews with caching, real-model evaluations, quote checks, stop/retry/progress. Preserve existing documents and unrelated work. Never expose private document contents in demos or logs.
## Evidence on Hand
Synthetic garden PDFs and automated fixtures. No customer, speed or accuracy marketing claims are available.
## Product Principles
Evidence stays beside answers. Missing information is explicit. Progress reflects actual work. Failed and cancelled drafts are distinguishable from completed answers. Product output prioritizes final answers; explanations and checks remain available on demand. Developer-facing documentation explains the actual code.
