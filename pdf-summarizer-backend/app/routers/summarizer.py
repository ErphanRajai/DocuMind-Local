import os
import asyncio
import json
import httpx
from pydantic import BaseModel
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..services.pdf_processor import PDFProcessorService
from ..services.llm_service import LLMService

router = APIRouter(
    prefix="/summarizer",
    tags=["PDF Summarizer"]
)

UPLOAD_DIR = "./uploaded_pdfs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def process_pdf_worker(pdf_id: int, file_path: str, db_session: Session):
    """
    Asynchronous background worker using a separate context-safe DB transaction.
    """
    try:
        db = db_session
        pdf_record = db.query(models.PDFDocument).filter(models.PDFDocument.id == pdf_id).first()

        if pdf_record:
            pdf_record.status = "processing"
            db.commit()

            extracted_text = PDFProcessorService.extract_text(file_path)
            pdf_record.raw_text = extracted_text
            db.commit()

            chunks = PDFProcessorService.chunk_text(extracted_text, chunk_size=1000, chunk_overlap=200)
            ai_summary = asyncio.run(LLMService.summarize_chunks(chunks))

            pdf_record.summary = ai_summary
            pdf_record.status = "completed"
            db.commit()

    except Exception as e:
        db = db_session
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
    """
    Standard asynchronous background upload. Saves data to the DB and returns instantly.
    """
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
async def upload_and_stream_summary(file: UploadFile = File(...)):
    """
    High-velocity streaming endpoint. Bypasses persistent database tracking
    to stream tokens from Ollama straight to the client in real time.
    """
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
                
        # 1. Process and Chunk the text inside the request thread
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
        LLMService.stream_summarize_chunks(chunks),
        media_type="text/event-stream"
    )


@router.get("/{pdf_id}", response_model=schemas.PDFDocumentResponse)
async def get_pdf_status(
    pdf_id: int,
    db: Session = Depends(get_db)
):
    """
    Queries the current processing or completion status of an uploaded PDF file.
    """
    pdf_record = db.query(models.PDFDocument).filter(models.PDFDocument.id == pdf_id).first()

    if not pdf_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PDF document with ID {pdf_id} not found"
        )
    
    return pdf_record

from pydantic import BaseModel

class ChatRequest(BaseModel):
    pdf_id: int
    question: str

@router.post("/chat")
async def chat_with_pdf(payload: ChatRequest, db: Session = Depends(get_db)):
    """
    Exposes a conversation endpoint allowing users to ask specific questions
    about an ingested PDF using local context matching.
    """
    pdf_record = db.query(models.PDFDocument).filter(models.PDFDocument.id == payload.pdf_id).first()
    
    if not pdf_record or not pdf_record.raw_text:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document context not found. Please upload and process the file first."
        )
        
    document_context = pdf_record.raw_text[:12000]
    
    chat_payload = {
        "model": "llama3.2:3b",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert AI assistant conversing about a specific document.\n"
                    "Use the provided document context to answer the user's question accurately.\n"
                    "If the answer cannot be found in the context, use your general knowledge but state clearly "
                    "that it is an inference outside the source text. Keep your responses precise and professional."
                )
            },
            {
                "role": "user",
                "content": f"Context:\n{document_context}\n\nQuestion: {payload.question}"
            }
        ],
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