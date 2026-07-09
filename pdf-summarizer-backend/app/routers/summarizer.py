import os
import asyncio
import json
import httpx
from pydantic import BaseModel
from typing import Optional, List
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..services.pdf_processor import PDFProcessorService
from ..services.llm_service import LLMService
from ..services.vector_db import store_chunks_in_qdrant, search_chunks_in_qdrant

router = APIRouter(
    prefix="/summarizer",
    tags=["PDF Summarizer"]
)

UPLOAD_DIR = "./uploaded_pdfs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def process_pdf_worker(pdf_id: int, file_path: str, db_session: Session):
    db = db_session
    try:
        pdf_record = db.query(models.PDFDocument).filter(models.PDFDocument.id == pdf_id).first()
        if pdf_record:
            pdf_record.status = "processing"
            db.commit()

            extracted_text = PDFProcessorService.extract_text(file_path)
            pdf_record.raw_text = extracted_text
            db.commit()

            chunks = PDFProcessorService.chunk_text(extracted_text, chunk_size=1000, chunk_overlap=200)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                print(f"DEBUG: Storing chunks in vector database for PDF ID {pdf_id}...")
                loop.run_until_complete(store_chunks_in_qdrant(pdf_id, chunks))

                print(f"DEBUG: Generating AI summary for PDF ID {pdf_id}...")
                ai_summary = loop.run_until_complete(LLMService.summarize_chunks(chunks))
            finally:
                loop.close()

            pdf_record.summary = ai_summary
            pdf_record.status = "completed"
            db.commit()

    except Exception as e:
        pdf_record = db.query(models.PDFDocument).filter(models.PDFDocument.id == pdf_id).first()
        if pdf_record:
            pdf_record.summary = f"Error occurred during background processing: {str(e)}"
            pdf_record.status = "failed"
            db.commit()


@router.post("/upload", response_model=schemas.PDFDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format, Only PDF files are allowed"
        )
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    try:
        with open(file_path, "wb") as buffer:
            while content := await file.read(1024 * 1024):
                buffer.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file : {str(e)}"
        )
    
    new_pdf = models.PDFDocument(
        filename=file.filename,
        file_path=file_path,
        status="pending"
    )
    db.add(new_pdf)
    db.commit()
    db.refresh(new_pdf)

    background_tasks.add_task(process_pdf_worker, new_pdf.id, file_path, db)

    return new_pdf


@router.post("/upload/stream")
async def upload_and_stream_summary(
    file: UploadFile = File(...),
    custom_prompt: Optional[str] = Form(None)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format, Only PDF files are allowed"
        )
    
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    try:
        with open(file_path, "wb") as buffer:
            while content := await file.read(1024 * 1024):
                buffer.write(content)
                
        extracted_text = PDFProcessorService.extract_text(file_path)
        chunks = PDFProcessorService.chunk_text(extracted_text, chunk_size=4000, chunk_overlap=400)
        
        if not chunks:
            raise ValueError("No readable text found inside the uploaded PDF.")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize streaming pipeline: {str(e)}"
        )

    return StreamingResponse(
        LLMService.stream_summarize_chunks(chunks, custom_prompt=custom_prompt),
        media_type="text/event-stream"
    )


@router.get("/{pdf_id}", response_model=schemas.PDFDocumentResponse)
async def get_pdf_status(
    pdf_id: int,
    db: Session = Depends(get_db)
):
    pdf_record = db.query(models.PDFDocument).filter(models.PDFDocument.id == pdf_id).first()

    if not pdf_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PDF document with ID {pdf_id} not found"
        )
    
    return pdf_record



class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    pdf_id: int
    question: str
    history: Optional[List[ChatMessage]] = []


@router.post("/chat")
async def chat_with_pdf(payload: ChatRequest, db: Session = Depends(get_db)):
    pdf_record = db.query(models.PDFDocument).filter(models.PDFDocument.id == payload.pdf_id).first()
    
    if not pdf_record or not pdf_record.raw_text:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document context not found. Please upload and process the file first."
        )
        
    relevant_chunks = await search_chunks_in_qdrant(pdf_id=payload.pdf_id, query_text=payload.question, limit=3)
    document_context = "\n\n---\n\n".join(relevant_chunks) if relevant_chunks else "nothing relatable was found during the search..."
    
    messages_payload = [
        {
            "role": "system",
            "content": (
                "You are an expert AI assistant conversing about a specific document.\n"
                "Use the provided document context and previous conversation history to answer accurately.\n"
                "If the answer cannot be found in the context, use your general knowledge but state clearly "
                "that it is an inference outside the source text. Keep your responses precise and professional.\n\n"
                f"Document Context:\n{document_context}"
            )
        }
    ]

    if payload.history:
        for msg in payload.history[-6:]:
            messages_payload.append({"role": msg.role, "content": msg.content})

    messages_payload.append({
        "role": "user",
        "content": payload.question
    })

    chat_payload = {
        "model": "llama3.2:3b",
        "messages": messages_payload,
        "options": {"temperature": 0.5},
        "stream": True
    }
    
    async def chat_stream_generator():
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                async with client.stream("POST", LLMService.API_URL, json=chat_payload) as response:
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            if line:
                                data = json.loads(line)
                                token = data.get("message", {}).get("content", "")
                                yield token
                    else:
                        yield f"[Backend Error: Status {response.status_code}]"
            except Exception as e:
                yield f"[Chat Connection Error: {str(e)}]"

    return StreamingResponse(chat_stream_generator(), media_type="text/event-stream")