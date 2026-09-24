import json
import logging
import os
import uuid
from typing import List, Optional

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import SessionLocal, get_db
from ..services.llm_service import LLMService
from ..services.pdf_processor import PDFProcessorService
from ..services.vector_db import (
    search_chunks_in_qdrant_with_scores,
    store_chunks_in_qdrant,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/summarizer",
    tags=["PDF Summarizer"]
)

UPLOAD_DIR = "./uploaded_pdfs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


@router.get("/models")
async def list_available_models():
    """Returns all installed Ollama models and curated recommendations."""
    installed = await LLMService.get_available_models()
    return {
        "installed": installed,
        "recommended": LLMService.RECOMMENDED_MODELS
    }


async def process_pdf_worker(pdf_id: int, file_path: str, filename: str):
    """Background worker for text extraction and vector indexing."""
    db = SessionLocal()
    try:
        pdf_record = db.query(models.PDFDocument).filter(models.PDFDocument.id == pdf_id).first()
        if not pdf_record:
            return

        pdf_record.status = "processing"
        db.commit()

        extracted_text = PDFProcessorService.extract_text(file_path)
        pdf_record.raw_text = extracted_text
        db.commit()

        chunks = PDFProcessorService.chunk_text(extracted_text, chunk_size=4000, chunk_overlap=300)
    except Exception as e:
        logger.exception("process_pdf_worker: extraction failed for PDF ID %s", pdf_id)
        try:
            db.rollback()
            pdf_record = db.query(models.PDFDocument).filter(models.PDFDocument.id == pdf_id).first()
            if pdf_record:
                pdf_record.summary = f"Error during extraction: {str(e)}"
                pdf_record.status = "failed"
                db.commit()
        except Exception:
            db.rollback()
        return
    finally:
        db.close()

    try:
        if chunks:
            await store_chunks_in_qdrant(pdf_id, chunks, filename=filename)
        ai_summary = await LLMService.summarize_chunks(chunks)
    except Exception as e:
        logger.exception("process_pdf_worker: indexing failed for PDF ID %s", pdf_id)
        db = SessionLocal()
        try:
            pdf_record = db.query(models.PDFDocument).filter(models.PDFDocument.id == pdf_id).first()
            if pdf_record:
                pdf_record.summary = f"Error during indexing: {str(e)}"
                pdf_record.status = "failed"
                db.commit()
        finally:
            db.close()
        return

    db = SessionLocal()
    try:
        pdf_record = db.query(models.PDFDocument).filter(models.PDFDocument.id == pdf_id).first()
        if pdf_record:
            pdf_record.summary = ai_summary
            pdf_record.status = "completed"
            db.commit()
    finally:
        db.close()


@router.post("/upload", response_model=List[schemas.PDFDocumentResponse], status_code=status.HTTP_201_CREATED)
async def upload_pdfs(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    uploaded_records = []
    for file in files[:3]:
        if not file.filename.lower().endswith(".pdf"):
            continue

        safe_filename = f"{uuid.uuid4().hex[:12]}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)

        total_bytes = 0
        with open(file_path, "wb") as buffer:
            while content := await file.read(1024 * 1024):
                total_bytes += len(content)
                if total_bytes > MAX_UPLOAD_BYTES:
                    buffer.close()
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File {file.filename} exceeds {MAX_UPLOAD_MB} MB limit"
                    )
                buffer.write(content)

        new_pdf = models.PDFDocument(
            filename=file.filename,
            file_path=file_path,
            status="pending"
        )
        db.add(new_pdf)
        db.commit()
        db.refresh(new_pdf)

        background_tasks.add_task(process_pdf_worker, new_pdf.id, file_path, file.filename)
        uploaded_records.append(new_pdf)

    return uploaded_records


@router.post("/upload/stream")
async def upload_and_stream_multi_summary(
    files: List[UploadFile] = File(...),
    custom_prompt: Optional[str] = Form(None),
    model: Optional[str] = Form(None)
):
    all_chunks = []
    for file in files[:3]:
        if not file.filename.lower().endswith(".pdf"):
            continue

        safe_filename = f"{uuid.uuid4().hex[:12]}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)

        with open(file_path, "wb") as buffer:
            while content := await file.read(1024 * 1024):
                buffer.write(content)

        extracted_text = PDFProcessorService.extract_text(file_path)
        doc_header = f"=== SOURCE DOCUMENT: {file.filename} ===\n"
        chunks = PDFProcessorService.chunk_text(doc_header + extracted_text, chunk_size=4000, chunk_overlap=300)
        all_chunks.extend(chunks)

    if not all_chunks:
        raise HTTPException(status_code=400, detail="No readable text extracted from uploaded PDFs.")

    return StreamingResponse(
        LLMService.stream_summarize_chunks(all_chunks, custom_prompt=custom_prompt, model=model),
        media_type="text/event-stream"
    )


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    pdf_id: Optional[int] = None
    pdf_ids: Optional[List[int]] = []
    question: str
    history: Optional[List[ChatMessage]] = []
    model: Optional[str] = None


@router.post("/chat")
async def chat_with_pdf_or_general(payload: ChatRequest, db: Session = Depends(get_db)):
    active_ids = list(payload.pdf_ids or [])
    if payload.pdf_id and payload.pdf_id not in active_ids:
        active_ids.append(payload.pdf_id)

    relevant_chunks = []
    scores = []
    ret_latency_ms = 0.0

    if active_ids:
        relevant_chunks, scores, ret_latency_ms = await search_chunks_in_qdrant_with_scores(
            pdf_ids=active_ids,
            query_text=payload.question,
            limit=4
        )

        doc_records = db.query(models.PDFDocument).filter(models.PDFDocument.id.in_(active_ids)).all()
        doc_names = ", ".join([d.filename for d in doc_records])

        if relevant_chunks:
            document_context = "\n\n---\n\n".join(relevant_chunks)
        else:
            document_context = "\n\n".join([
                f"=== Document: {d.filename} ===\n{d.raw_text[:4000] if d.raw_text else (d.summary or 'No text available')}"
                for d in doc_records
            ])

        system_instruction = (
            f"You are DocuMind, an elite AI document analysis engine reviewing: {doc_names}.\n"
            "You have direct access to the extracted source document content provided below in [SOURCE CONTEXT].\n"
            "Never claim you cannot view, open, or access files. Answer directly using the extracted context.\n\n"
            f"[SOURCE CONTEXT]:\n{document_context}"
        )
    else:
        system_instruction = (
            "You are DocuMind, an intelligent, helpful, and concise AI assistant. "
            "Help the user with programming, engineering, and technical explanations."
        )

    top_score = scores[0] if scores else (1.0 if not active_ids else 0.0)
    avg_score = sum(scores) / len(scores) if scores else top_score

    messages_payload = [{"role": "system", "content": system_instruction}]

    if payload.history:
        for msg in payload.history[-8:]:
            messages_payload.append({"role": msg.role, "content": msg.content})

    messages_payload.append({"role": "user", "content": payload.question})

    selected_model = payload.model if payload.model else LLMService.CHAT_MODEL

    chat_payload = {
        "model": selected_model,
        "messages": messages_payload,
        "options": {"temperature": 0.2},
        "stream": True
    }

    async def chat_stream_generator():
        telemetry_init = {
            "__type__": "telemetry",
            "retrieval_ms": round(ret_latency_ms, 1),
            "top_score": round(top_score, 3),
            "avg_score": round(avg_score, 3),
            "chunks_retrieved": len(relevant_chunks)
        }
        yield f"__META__{json.dumps(telemetry_init)}\n"

        client_timeout = httpx.Timeout(connect=20.0, read=None, write=300.0, pool=60.0)
        async with httpx.AsyncClient(timeout=client_timeout) as client:
            try:
                async with client.stream("POST", LLMService.API_URL, json=chat_payload) as response:
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            if line:
                                data = json.loads(line)
                                token = data.get("message", {}).get("content", "")
                                yield token
                    elif response.status_code == 404:
                        yield f"[Backend Error: Model '{selected_model}' is not pulled in Ollama. Run 'ollama run {selected_model}' in terminal to install it.]"
                    else:
                        yield f"[Backend Error: Status {response.status_code}]"
            except Exception as e:
                yield f"[Chat Connection Error: {str(e)}]"

    return StreamingResponse(chat_stream_generator(), media_type="text/event-stream")