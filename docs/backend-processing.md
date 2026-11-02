# How the document pipeline works

The UI now sends a PDF once. FastAPI saves it, validates its structure, creates its document record, and schedules extraction and indexing. After the document is ready, the UI asks for an answer using the saved ID. Indexing never calls the chat model.

```text
POST /summarizer/upload (multipart files)
  -> validate the whole batch -> commit document records -> background processing
  -> extract text in a process -> save text -> create search vectors -> ready

GET /summarizer/documents/{id}
  -> pending / processing / indexing / completed / partial / failed

POST /summarizer/summary/stream (JSON document IDs and model settings)
  -> reuse saved text -> generate the requested answer

POST /summarizer/chat
  -> validate ready document IDs -> retrieve excerpts -> generate answer
```

## 1. Upload once and reuse the result

The upload handler calls `ingest_uploads` and only schedules indexing:

```python
records, staged = await ingest_uploads(files)
for record, (filename, path) in zip(records, staged):
    background_tasks.add_task(process_pdf_worker, record["id"], path, filename)
```

The worker stores `raw_text` and vectors. It does not call `summarize_chunks`. The frontend polls the status endpoint and then calls `/summary/stream` with `pdf_ids`, `custom_prompt`, and the selected model/provider. That endpoint reads SQLite rather than reopening the PDF. Repeated answers therefore do not create duplicate files or repeat OCR.

The former `/upload/stream` endpoint returns HTTP 410 with instructions for the new API. It no longer accepts a second upload.

Sources: `app/services/documents.py`, `app/routers/summarizer.py`, and frontend `api_client.py` / `app.py`.

## 2. Keep blocking work outside the API event loop

`async def` lets a function wait without monopolizing the server only when its work yields control. PDF parsing and OCR are ordinary blocking calls. The new `PDFExecutor` runs them in separate processes:

```python
result = await pdf_executor.run(PDFProcessorService.extract_document, file_path)
```

The executor uses `ProcessPoolExecutor` with the spawn start method. Each process opens its own document. `PDF_PROCESS_WORKERS` defaults to 2; `PDF_MAX_PENDING` defaults to 8, counting both queued and running operations. A semaphore limits submissions to running process capacity; admission rejects overload with a clear error. Cancelling a caller does not incorrectly release a process slot while that process is still working.

Database operations use a different mechanism:

```python
await asyncio.to_thread(update_document, pdf_id, status="indexing")
```

Each helper creates, commits, and closes its own SQLAlchemy session in that thread. A database session is never shared between concurrent tasks or held open during OCR, indexing, or generation. Upload disk copies also run in a thread and enforce the byte limit as they copy.

This improves responsiveness; it does not make the selected model itself faster. Background tasks still live in the API process, so automatic restart recovery is outside this change.

## 3. Failures are not answers

Extraction returns `ExtractionResult(text, chunks, warnings)`. An isolated page or OCR failure preserves useful text and records a warning. An unreadable document raises `PDFProcessingError`. After successful indexing, documents with warnings become `partial`; fully readable documents become `completed`. Failures become `failed`, with `error_message` separate from `summary`.

Existing SQLite databases receive two additive text columns, `error_message` and `warning_message`. Before the first upgrade, a SQLite backup is saved beside the database as `pdf_summarizer.db.before_processing_diagnostics.bak`. Known legacy extraction/indexing error strings in failed records move out of the summary field. Existing text, documents, and conversation JSON are preserved.

Model services now raise `GenerationError` for HTTP failures, invalid responses, missing models, and streams ending without a completion marker. The router translates these into a JSON Lines control event:

```json
{"type":"metadata","retrieval_ms":12.5}
{"type":"text","content":"A piece of the answer"}
{"type":"done"}
```

On failure, `error` replaces `done`:

```json
{"type":"error","message":"The model could not complete the answer."}
```

The frontend assembles complete lines across network packets and requires `done` before returning an answer to the code that saves conversation history. A provider error cannot become answer text. Partial streamed text can remain visible during a failure but is not saved as a completed assistant message.

## 4. Validate before committing a batch

Every upload goes through one path. It requires one to three PDFs, validates filenames and size, checks that the file is an actual readable PDF, and rejects password-protected documents. A random UUID determines the stored filename; the client filename is display metadata only.

All files are staged and checked before any records are committed. All new records use one database transaction. A failure removes the batch's staged files; it does not leave the first document registered while rejecting a later file. An unreadable but structurally valid scan is identified during extraction and retained as an explicit failed document.

Chat schemas require a nonblank question of at most 8,000 characters, at most three positive document IDs, and at most eight history messages. Each history message is limited to 16,000 characters, with a total history/question budget of 64,000. Roles are restricted to `user` and `assistant`. Provider settings must be valid before generation begins. Missing documents return 404; documents still processing or failed return 409.

## Running the checks

Inside a backend development environment, install `requirements-dev.txt`, then run:

```powershell
python -m pytest -q
```

Tests use synthetic PDFs, temporary SQLite databases/upload directories, and mocked model/search connections. Process tests also exercise a real spawned process and verify that the event loop can continue while it works. The suite covers corrupt/oversized batches, one extraction per upload, repeated summaries without new uploads, partial OCR, separate error storage, provider failures, split UTF-8 streams, input limits, and an existing-database upgrade.
