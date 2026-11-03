import asyncio
import json
import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .. import schemas
from ..services.documents import ingest_uploads, read_documents, update_document, save_extracted_pages
from ..services.citations import GROUNDED_SYSTEM, bind_sources, citation_warning, ensure_page_index, summary_sources, check_quotes, quotes_requested, canonical_citations
from ..services.languages import language_instruction, detect_language
from ..services.question_batches import numbered_questions, CitationStream
from ..services.context_budget import CONTEXT_TOKENS, OUTPUT_TOKENS
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


async def _answer_events(tokens, metadata, metrics, quote_question=''):
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
        if metrics.get('done_reason') == 'length':
            raise GenerationError('The answer reached its output limit and is incomplete. Request less detail or split the task into numbered questions.')
        warning = citation_warning(answer, metadata.get("sources", []))
        if warning == "invalid":
            raise GenerationError("The model used an unknown source citation. This is not a completed answer; please retry the question.")
        if warning:
            metrics["citation_warning"] = warning
        checks = check_quotes(answer, metadata['sources'], strict=metadata.get('quotes_requested', False), question=quote_question) if metadata.get('sources') else []
        metrics["quote_checks"] = checks
        if any(not check["verified"] for check in checks):
            raise GenerationError("A quotation could not be matched to its cited excerpt. This is not a completed answer; retry or ask for a paraphrase.")
        yield _event("done", metrics=metrics)
    except GenerationError as exc:
        yield _event("error", message=str(exc), metrics=metrics)
    except Exception:
        logger.exception("Answer generation failed")
        yield _event("error", message="The answer could not be completed. Check the model connection and try again.")
    finally:
        await tokens.aclose()


def _stream(tokens, metadata=None, metrics=None, quote_question=''):
    return StreamingResponse(
        _answer_events(tokens, metadata or {}, metrics if metrics is not None else {}, quote_question),
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


async def _grounded_answer(payload, records, sources, question, history=None, spread=False, extra=None, system_suffix=''):
    if not sources:
        raise HTTPException(503, "No page sources were found. Check document search and try again.")
    try:
        language_text = payload.custom_prompt or sources[0]['text'] if isinstance(payload, schemas.SummaryRequest) else question
        plan = await LLMService.prepare_prompt(GROUNDED_SYSTEM + ' ' + language_instruction(payload.answer_language, language_text) + ' ' + system_suffix, question, history=history, sources=sources,
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
    metadata = {**plan.metadata, **details, 'quotes_requested': quotes_requested(question),
                "warnings": [record["warning_message"] for record in records if record["warning_message"]]}
    import hashlib
    metadata['document_versions'] = [{'pdf_id':record['id'],'text_sha256':hashlib.sha256((record.get('raw_text') or '').encode()).hexdigest()} for record in records]
    metrics = dict(metadata)
    return _stream(LLMService.stream_messages(plan.messages, model=payload.model, provider=payload.provider,
        api_base_url=payload.api_base_url, api_key=payload.api_key,
        answer_length=payload.answer_length, telemetry=metrics), metadata, metrics, quote_question=question)


@router.post("/chat")
async def chat_with_pdf_or_general(payload: schemas.ChatRequest):
    if payload.pdf_ids:
        records = await _ready_documents(payload.pdf_ids)
        try:
            parts = numbered_questions(payload.question)
        except GenerationError as exc:
            raise HTTPException(422, str(exc)) from exc
        if parts:
            return StreamingResponse(_question_batch_events(payload, records, parts), media_type='application/x-ndjson',
                                     headers={'Cache-Control':'no-cache', 'X-Accel-Buffering':'no'})
        return await _document_chat(payload, records)
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


async def _document_chat(payload, records, system_suffix='', query_text=None):
    try:
        query, contextual = retrieval_query(query_text or payload.question, [m.model_dump() for m in payload.history])
        details = {}
        if payload.search_mode == 'deep':
            hits, details = await retrieve(payload.pdf_ids, query, payload.focus_problem)
            retrieval_ms = details['retrieval_ms']
        else:
            hits, retrieval_ms = await search_page_sources(payload.pdf_ids, query)
    except Exception as exc:
        logger.exception('Document retrieval failed')
        raise HTTPException(503, 'Document search is unavailable. Check Ollama and Qdrant, then try again.') from exc
    return await _grounded_answer(payload, records, bind_sources(hits, records), payload.question,
        history=[message.model_dump() for message in payload.history], system_suffix=system_suffix,
        extra={**details, 'retrieval_ms':round(retrieval_ms,1), 'chunks_retrieved':len(hits), 'contextual_retrieval':contextual,
               'source_notice':'Sources show the page excerpts supplied to the model. A citation is a way to check a claim, not proof that it is correct.'})


async def _question_batch_events(payload, records, parts):
    """Search and budget each question independently; only one final terminal event."""
    sources, results, all_checks = [], [], []
    committed = ''
    language = detect_language(payload.question) if payload.answer_language == 'auto' else payload.answer_language
    # The whole request provides language/format instructions, but not one shared evidence search.
    instruction = ('Answer only the current question. The remaining numbered questions are separate tasks. '
                   'Do not restate the question. Use concise prose, aiming for at most '
                   + ('35 words in two or three short sentences. ' if payload.answer_length == 'short' else '220 words. '))
    totals = {'generated_tokens':0, 'prompt_tokens':0, 'generation_ms':0, 'retrieval_ms':0}
    yield _event('metadata', sources=[], question_count=len(parts), batch=True,
                 initial_max_output_tokens_per_question=OUTPUT_TOKENS[payload.answer_length],
                 retry_max_output_tokens=OUTPUT_TOKENS['long'])
    for index, part in enumerate(parts):
        yield _event('status', phase='question', message=f'Question {index + 1} of {len(parts)} · Finding page evidence', completed=index, total=len(parts))
        text, metadata, metrics, error, completed = '', {}, {}, None, False
        attempts = []
        shortened = False
        mapping = {}
        writer = CitationStream(mapping)
        started = False
        heading = f'\n\n### {"سؤال" if language == "fa" else "Question"} {part["number"]}\n\n'

        def live(update):
            nonlocal started
            if update is None:
                return None
            content, replace = update
            if replace:
                started = True
                return _event('replace_text', content=committed + heading + content)
            if not started:
                content = heading + content
                started = True
            return _event('text', content=content)

        try:
            single = payload.model_copy(update={'question': part['directive'] + '\n' + part['text'], 'history':[],
                                               'answer_language':language})
            for attempt in range(2):
                if attempt == 0:
                    response = await _document_chat(single, records, instruction, query_text=part['text'])
                else:
                    # Remove only this question's failed draft before streaming its retry.
                    yield _event('replace_text', content=committed)
                    shortened = payload.answer_length == 'long' and not quotes_requested(single.question)
                    retry_length = 'short' if shortened else 'long'
                    label = 'Checking a brief replacement' if shortened else 'Retrying with more answer space'
                    yield _event('status', phase='question', message=f'Question {index + 1} of {len(parts)} · {label}', completed=index, total=len(parts))
                    retry = single.model_copy(update={'answer_length':retry_length})
                    evidence = [{**s, 'title':f'[{s["id"]}] {s["filename"]} — PDF page {s["page"]}', 'text':s['excerpt']} for s in metadata.get('sources',[])]
                    mapping = {}
                    writer = CitationStream(mapping)
                    started = False
                    retry_instruction = ('Answer only this question in two or three short sentences, aiming for 35 words. Do not restate the question. ' if shortened else instruction)
                    response = await _grounded_answer(retry, records, evidence, retry.question,
                        system_suffix=retry_instruction + ' Start a fresh concise answer. The previous attempt was incomplete or failed citation validation. '
                        + ('Copy requested quotes exactly.' if quotes_requested(retry.question) else 'Paraphrase without quotation marks, including around terms.'))
                text, metadata, metrics, error, completed = '', {}, {}, None, False
                mapping = {}
                writer = CitationStream(mapping)
                started = False
                try:
                    async for line in response.body_iterator:
                        row = json.loads(line)
                        if row['type'] == 'metadata':
                            metadata.update(row)
                            for source in row.get('sources',[]):
                                shared = next((s for s in sources if all(s.get(k)==source.get(k) for k in ['pdf_id','page','excerpt'])), None)
                                if not shared:
                                    shared = {**source,'id':f'S{len(sources)+1}'}
                                    sources.append(shared)
                                mapping[source['id']] = shared['id']
                            # Source locations must be available before their text is visible.
                            yield _event('metadata', sources=sources, batch=True, question_count=len(parts))
                        elif row['type'] == 'text':
                            text += row.get('content','')
                            update = live(writer.feed(row.get('content','')))
                            if update: yield update
                        elif row['type'] == 'done': metrics.update(row.get('metrics',{})); completed = True
                        elif row['type'] == 'error': metrics.update(row.get('metrics',{})); error = row.get('message','Question failed')
                finally:
                    await response.body_iterator.aclose()
                update = live(writer.feed(final=True))
                if update: yield update
                attempts.append(dict(metrics))
                if not completed and not error: error = 'The question ended before completion. Retry it.'
                repairable = error and (metrics.get('done_reason') == 'length' or 'quotation' in error or 'unknown source citation' in error)
                if completed or not repairable: break
        except asyncio.CancelledError:
            raise
        except HTTPException as exc:
            error = str(exc.detail)
        except Exception:
            logger.exception('Numbered question %s failed', index + 1)
            error = 'This question could not be completed. Retry it.'
        for check in metrics.get('quote_checks',[]):
            all_checks.append({**check,'sources':[mapping.get(s,s) for s in check['sources']]})
        for key in totals:
            values = attempts[:1] if key == 'retrieval_ms' else attempts
            totals[key] += sum(m.get(key,0) or 0 for m in values)
        results.append({'number':part['number'],'status':'failed' if error else 'completed',
                        'done_reason':metrics.get('done_reason'), 'generated_tokens':metrics.get('generated_tokens'),
                        'attempts':len(attempts),
                        'shortened':shortened and not error,
                        **({'error':error} if error else {})})
        yield _event('metadata', sources=sources, batch=True, question_count=len(parts),
                     questions_completed=sum(r['status']=='completed' for r in results), question_results=results)
        update = live(writer.feed(final=True))
        if update: yield update
        if not started:
            yield _event('text', content=heading)
        content = ''
        if error:
            content = '\n\n' + ('**پاسخ این سؤال کامل نشد؛ دوباره تلاش کنید.**' if language == 'fa' else '**This answer is incomplete. Retry this question.**')
        elif shortened:
            content += '\n\n' + ('*پاسخ کوتاه‌تر ارائه شد؛ پیش‌نویس مفصل از بررسی شواهد عبور نکرد.*' if language == 'fa' else '*A brief answer is shown because the detailed draft did not pass validation.*')
        if content: yield _event('text', content=content)
        committed += heading + writer.rendered + content
        yield _event('status', phase='question', message=f'Processed {index + 1} of {len(parts)} questions', completed=index+1, total=len(parts))
    failed = sum(r['status']=='failed' for r in results)
    final = {**totals, 'sources':sources, 'quote_checks':all_checks, 'batch':True, 'question_count':len(parts),
             'questions_completed':len(parts)-failed, 'failed_questions':failed, 'question_results':results,
             'shortened_questions':sum(r['shortened'] for r in results),
             'context_tokens_per_question':CONTEXT_TOKENS, 'answer_length':payload.answer_length}
    if totals['generation_ms']:
        final['tok_per_sec'] = round(totals['generated_tokens']*1000/totals['generation_ms'],2)
    if failed:
        yield _event('error', message=f'{failed} of {len(parts)} answers are incomplete. Completed answers are retained; retry the marked questions.', metrics=final)
    else:
        yield _event('done', metrics=final)
