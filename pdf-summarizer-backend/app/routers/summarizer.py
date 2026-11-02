import asyncio
import json
import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .. import schemas
from ..services.documents import ingest_uploads, read_documents, update_document, save_extracted_pages
from ..services.citations import GROUNDED_SYSTEM, bind_sources, citation_warning, ensure_page_index, summary_sources, check_quotes
from ..services.languages import language_instruction
from ..services.retrieval_context import retrieval_query
from ..services.advanced_retrieval import retrieve
from ..services.complete_review import review_events
from ..services.errors import GenerationError, PDFProcessingError, ProcessingBusyError
from ..services.llm_service import LLMService
from ..services.pdf_executor import pdf_executor
from ..services.pdf_processor import PDFProcessorService
from ..services.vector_db import search_page_sources, store_chunks_in_qdrant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/summarizer", tags=["PDF Summarizer"])


@router.get("/models")
async def list_available_models():
    import os
    return {"installed": await LLMService.get_available_models(), "recommended": LLMService.RECOMMENDED_MODELS,
            "default": LLMService.CHAT_MODEL, "local_only": os.getenv('DOCUMIND_LOCAL_ONLY') == '1'}


@router.post("/models/preload", status_code=202)
async def preload_selected_model(payload: schemas.PreloadRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(LLMService.preload_model, payload.model)
    return {"model": payload.model, "status": "warming", "context_tokens": 8192, "keep_alive": "15m"}


async def process_pdf_worker(pdf_id: int, file_path: str, filename: str, engine='standard'):
    """Index only. Answer generation belongs to an explicit user request."""
    try:
        exists = await asyncio.to_thread(update_document, pdf_id, status="processing", error_message=None)
        if not exists:
            return
        extractor = PDFProcessorService.extract_document
        if engine == 'docling':
            from ..services.layout_extraction import extract_with_docling
            extractor = extract_with_docling
        result = await pdf_executor.run(extractor, file_path)
        if not result.text.strip() or not result.chunks:
            raise PDFProcessingError("No readable text could be extracted from this PDF.")
        warnings = "\n".join(result.warnings) or None
        await asyncio.to_thread(save_extracted_pages, pdf_id, result)
        await asyncio.to_thread(update_document, pdf_id, status="indexing")
        await store_chunks_in_qdrant(pdf_id, result.chunks, filename=filename, page_numbers=result.chunk_pages)
        await asyncio.to_thread(
            update_document, pdf_id, status="partial" if warnings else "completed", error_message=None, source_version=1
        )
    except asyncio.CancelledError:
        await asyncio.to_thread(
            update_document, pdf_id, status="failed", error_message="Processing was interrupted. Please upload the PDF again."
        )
        raise
    except Exception as exc:
        logger.exception("Document processing failed for PDF ID %s", pdf_id)
        message = str(exc) if isinstance(exc, (PDFProcessingError, ProcessingBusyError)) else (
            "Document processing failed. Check Ollama and document search, then upload the PDF again."
        )
        await asyncio.to_thread(update_document, pdf_id, status="failed", error_message=message, summary=None)


@router.post("/upload", response_model=List[schemas.PDFDocumentResponse], status_code=201)
async def upload_pdfs(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    records, staged = await ingest_uploads(files)
    for record, (filename, path) in zip(records, staged):
        if record['status'] not in {'completed', 'partial'}:
            background_tasks.add_task(process_pdf_worker, record["id"], path, filename)
    return records


@router.post("/upload/stream", deprecated=True)
async def retired_stream_upload():
    # This route no longer accepts files, so it cannot bypass upload validation
    # or accidentally create a second copy for the same answer.
    raise HTTPException(410, "Upload once to /summarizer/upload, then POST document IDs to /summarizer/summary/stream.")


@router.get("/documents/{pdf_id}", response_model=schemas.PDFDocumentResponse)
async def document_status(pdf_id: int):
    records = await asyncio.to_thread(read_documents, [pdf_id])
    if not records:
        raise HTTPException(404, "Document not found.")
    return records[0]


async def _ready_documents(pdf_ids):
    records = await asyncio.to_thread(read_documents, pdf_ids, include_text=True)
    if len(records) != len(pdf_ids):
        raise HTTPException(404, "One or more selected documents were not found.")
    for record in records:
        if record["status"] == "failed":
            raise HTTPException(409, f"{record['filename']}: {record['error_message'] or 'Processing failed.'}")
        if record["status"] not in {"completed", "partial"}:
            raise HTTPException(409, "The selected PDFs are still processing. Wait until indexing finishes.")
        if not record["raw_text"]:
            raise HTTPException(409, "A selected PDF has no readable text. Please upload it again.")
    return await ensure_page_index(records)


def _event(event_type, **values):
    return json.dumps({"type": event_type, **values}, ensure_ascii=False) + "\n"


async def _answer_events(tokens, metadata, metrics):
    """Errors and completion are control events, never generated answer text."""
    yield _event("metadata", **metadata)
    try:
        answer = ""
        async for token in tokens:
            if token:
                answer += token
                yield _event("text", content=token)
        if not answer:
            raise GenerationError("The model returned an empty answer. Please try again.")
        warning = citation_warning(answer, metadata.get("sources", []))
        if warning == "invalid":
            raise GenerationError("The model used an unknown source citation. This is not a completed answer; please retry the question.")
        if warning:
            metrics["citation_warning"] = warning
        checks = check_quotes(answer, metadata.get("sources", []))
        metrics["quote_checks"] = checks
        if any(not check["verified"] for check in checks):
            raise GenerationError("A quotation could not be matched to its cited excerpt. This is not a completed answer; retry or ask for a paraphrase.")
        yield _event("done", metrics=metrics)
    except GenerationError as exc:
        yield _event("error", message=str(exc))
    except Exception:
        logger.exception("Answer generation failed")
        yield _event("error", message="The answer could not be completed. Check the model connection and try again.")
    finally:
        await tokens.aclose()


def _stream(tokens, metadata=None, metrics=None):
    return StreamingResponse(
        _answer_events(tokens, metadata or {}, metrics if metrics is not None else {}),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/summary/stream")
async def summarize_documents(payload: schemas.SummaryRequest):
    records = await _ready_documents(payload.pdf_ids)
    if payload.mode == 'synthesis':
        from ..services.synthesis import synthesis_events
        async def consolidate():
            try:
                async for item in synthesis_events(payload, records, _event): yield item
            except GenerationError as exc: yield _event('error', message=str(exc))
        return StreamingResponse(consolidate(), media_type='application/x-ndjson')
    if payload.mode == "complete":
        async def events():
            try:
                async for item in review_events(payload, records, _event):
                    yield item
            except GenerationError as exc:
                yield _event("error", message=str(exc))
            except Exception:
                logger.exception("Complete review failed")
                yield _event("error", message="The review failed. Retry to resume cached segments.")
        return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache"})
    sources, readable_pages = await summary_sources(records)
    question = payload.custom_prompt or "Summarize the documents' purpose, main findings, and important details. Cite the supporting pages."
    return await _grounded_answer(payload, records, sources, question, spread=True,
        extra={"summary_readable_pages": readable_pages})


async def _grounded_answer(payload, records, sources, question, history=None, spread=False, extra=None):
    if not sources:
        raise HTTPException(503, "No page sources were found. Check document search and try again.")
    try:
        language_text = payload.custom_prompt or sources[0]['text'] if isinstance(payload, schemas.SummaryRequest) else question
        plan = await LLMService.prepare_prompt(GROUNDED_SYSTEM + ' ' + language_instruction(payload.answer_language, language_text), question, history=history, sources=sources,
            model=payload.model, provider=payload.provider, answer_length=payload.answer_length, spread=spread)
    except GenerationError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not plan.metadata["sources"]:
        raise HTTPException(422, "No page excerpts fit this question. Please shorten it.")
    details = dict(extra or {})
    if "summary_readable_pages" in details:
        details["source_notice"] = (
            f"Summary uses excerpts from {len(plan.metadata['sources'])} of {details['summary_readable_pages']} readable pages. "
            "Ask a specific question to search the document further."
        )
    metadata = {**plan.metadata, **details,
                "warnings": [record["warning_message"] for record in records if record["warning_message"]]}
    import hashlib
    metadata['document_versions'] = [{'pdf_id':record['id'],'text_sha256':hashlib.sha256((record.get('raw_text') or '').encode()).hexdigest()} for record in records]
    metrics = dict(metadata)
    return _stream(LLMService.stream_messages(plan.messages, model=payload.model, provider=payload.provider,
        api_base_url=payload.api_base_url, api_key=payload.api_key,
        answer_length=payload.answer_length, telemetry=metrics), metadata, metrics)


@router.post("/chat")
async def chat_with_pdf_or_general(payload: schemas.ChatRequest):
    if payload.pdf_ids:
        records = await _ready_documents(payload.pdf_ids)
        try:
            query, contextual = retrieval_query(payload.question, [m.model_dump() for m in payload.history])
            details = {}
            if payload.search_mode == 'deep':
                hits, details = await retrieve(payload.pdf_ids, query, payload.focus_problem)
                retrieval_ms = details['retrieval_ms']
            else:
                hits, retrieval_ms = await search_page_sources(payload.pdf_ids, query)
        except Exception as exc:
            logger.exception("Document retrieval failed")
            raise HTTPException(503, "Document search is unavailable. Check Ollama and Qdrant, then try again.") from exc
        return await _grounded_answer(payload, records, bind_sources(hits, records), payload.question,
            history=[message.model_dump() for message in payload.history],
            extra={**details, "retrieval_ms": round(retrieval_ms, 1), "chunks_retrieved": len(hits), "contextual_retrieval": contextual,
                   "source_notice": "Sources show the page excerpts supplied to the model. A citation is a way to check a claim, not proof that it is correct."})
    system = "You are DocuMind, a careful local study assistant. Help students understand and check their work. State missing information rather than guessing. " + language_instruction(payload.answer_language, payload.question)

    try:
        plan = await LLMService.prepare_prompt(
            system, payload.question, history=[message.model_dump() for message in payload.history],
            model=payload.model, provider=payload.provider, answer_length=payload.answer_length,
        )
    except GenerationError as exc:
        raise HTTPException(422, str(exc)) from exc
    metrics = dict(plan.metadata)
    return _stream(LLMService.stream_messages(
        plan.messages, model=payload.model, provider=payload.provider,
        api_base_url=payload.api_base_url, api_key=payload.api_key,
        answer_length=payload.answer_length, telemetry=metrics,
    ), plan.metadata, metrics)
