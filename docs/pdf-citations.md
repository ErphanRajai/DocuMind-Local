# PDF answers you can check

DocuMind now keeps a page location with every extracted excerpt. New answers can contain clickable markers such as **1 · p. 2**. Clicking one opens the original PDF's second physical page in a separate tab. The **Source pages** panel shows the exact excerpts sent to the model, and those links survive saved-conversation reloads.

This feature uses the existing FastAPI, SQLite, Qdrant, PyMuPDF and Streamlit stack. It adds no package or external service, and it keeps the selected chat model and its 8,192-token budget.

## 1. Preserve evidence while processing a PDF

Previously, extraction flattened pages into a single string. A search result could identify some relevant words but could not reliably say which page contained them. Guessing page numbers from that string would be misleading, particularly for scanned or blank pages.

In `app/services/pdf_processor.py`, each page becomes an `ExtractedPage(number, text, label)`. Blank pages keep their position. Chunking happens **inside** a page:

```python
for page in pages:
    page_chunks = PDFProcessorService.chunk_text(page.text, chunk_size=2000, chunk_overlap=200)
    chunks.extend(page_chunks)
    chunk_pages.extend([page.number] * len(page_chunks))
```

Inputs are a saved PDF path; outputs are extracted pages, chunks, their page numbers, and extraction warnings. For example, if page 2 contains a budget and page 3 is blank, the budget chunks remain on page 2 and page 4 stays page 4. Reference sections are retained rather than removed by a heading heuristic.

`PDFPage` in `app/models.py` stores `(pdf_id, number, label, text)`. `save_extracted_pages` in `app/services/documents.py` writes the page map and flattened compatibility text in one database transaction: either the complete write commits, or it rolls back. The worker passes `chunk_pages` into Qdrant alongside each chunk. Its payload now contains `page_number` and `source_version=1`.

Existing SQLite databases receive additive columns and a `pdf_pages` table. Initialization makes a `.before_page_citations.bak` backup when upgrading a database that already has the earlier diagnostic columns; an older database gets the existing `.before_processing_diagnostics.bak` backup. Existing documents, answers and IDs remain in place.

Older PDFs are upgraded only when selected for a new answer. `ensure_page_index` in `app/services/citations.py` re-extracts the original PDF, stores the real page map and rebuilds that document's vectors. A per-document lock prevents two concurrent requests in this single API process from upgrading the same PDF twice. The version is marked ready only after indexing succeeds. Failed upgrades return a recoverable error and can be retried. New vectors are written before old unlocated vectors are removed. Missing original files return an explicit error instead of guessed citations.

**Tradeoff:** this stores text in both page rows and the existing compatibility field, and a legacy document's first new question can take longer. The lock is local to the existing single API process; several API processes would need a database lease or external job coordinator. OCR warnings are preserved, and OCR may still misread text.

## 2. Retrieve and generate with explicit source IDs

`search_page_sources` in `app/services/vector_db.py` preserves the Qdrant hit's document and page metadata. It queries every selected PDF, combines adjacent hits on a page and returns up to three page sources per document. Dense semantic search and sparse keyword search still work together. A retrieval score orders candidates; it is not a probability that an answer is correct.

`bind_sources` verifies that the document is selected and the page is within its stored page count. It assigns request-local IDs:

```python
{"id": "S1", "pdf_id": 72, "page": 2,
 "filename": "citation-demo.pdf", "title": "[S1] citation-demo.pdf — PDF page 2",
 "text": "The approved supplies budget is 240 dollars."}
```

IDs restart for each answer. They are labels for that answer's evidence, not permanent database keys.

`GROUNDED_SYSTEM` tells the model to use the supplied excerpts for document facts, cite supported claims with `[S1]`, identify inferences, admit missing evidence, and treat instructions found inside PDFs as untrusted document content. Prior assistant messages are not evidence. These are behavioral instructions; they reduce risk but are not a security boundary or an entailment checker.

`build_prompt` in `app/services/context_budget.py` budgets the question, history, page excerpts and answer together. Its metadata returns only the excerpts actually placed in the prompt, including any truncation markers. The API sends that source metadata before streaming answer text.

```python
warning = citation_warning(answer, metadata.get("sources", []))
if warning == "invalid":
    raise GenerationError("The model used an unknown source citation. ...")
```

The stream ends with an error if a model invents an unknown marker such as `[S99]`. The existing frontend completion protocol then prevents that draft from being saved. A completed answer without inline markers is kept with a visible warning and the retrieved pages. Code examples are excluded from the marker check. Model/network failures still end as error events, never successful answer text.

Summaries also use page sources. They sample the start, middle and end readable pages of each PDF and disclose the number of pages represented. They are **excerpt summaries**, not exhaustive long-document reviews. Targeted chat questions search all indexed pages, including a question sent alongside a newly attached PDF: that frontend path now calls `/chat` after indexing. Attaching a PDF without a question still requests a default overview. Multi-stage whole-document summaries, automatic claim verification, and a reranker are possible later improvements that would add model work and latency; they are not included here.

**Tradeoff:** giving each selected PDF a retrieval allowance helps comparisons, but a weakly related PDF may still contribute a source. A valid marker proves only that the supplied excerpt and page exist. The model can still misunderstand the excerpt or attach a real citation to an unsupported claim. Check the linked original page for consequential conclusions. Existing saved answers keep their original content; new page links are available on new answers.

## 3. Open the actual original page

`app/routers/document_viewer.py` adds three read-only endpoints:

| Request | Output |
| --- | --- |
| `GET /summarizer/documents/{id}/view?page=2` | Page viewer with Previous, Next, a page number form and an original PDF link |
| `GET /summarizer/documents/{id}/pages/2.png` | Rendered image of original physical PDF page 2 |
| `GET /summarizer/documents/{id}/file` | Original PDF with inline content disposition; append `#page=2` for native PDF viewers |

Rendering uses the bounded PDF process executor so it does not run inside the API event loop. Images are limited to 1,800 pixels on their longest side. The image viewer also works where a browser has no native PDF viewer. It shows the actual document layout, scans and diagrams rather than reconstructing the page from extracted text.

`document_file` resolves the database path and requires it to be inside the configured upload directory. Client filenames never become filesystem paths. The viewer escapes filenames and uses a restrictive content policy, private caching and a no-sniff header. A nonexistent page/file returns 404; corrupt PDFs return 422; a full process queue returns 503 with a retry hint. These endpoints share the app's current local-only access model. They do not add multi-user authorization.

`pdf-summarizer-frontend/citations.py` builds the link from verified numeric metadata:

```python
return f"{backend_url.rstrip('/')}/summarizer/documents/{source['pdf_id']}/view?page={source['page']}"
```

`cited_markdown` replaces `[S1]` with that URL during streaming and when rendering saved answers. Markers inside code or existing links are left alone. Raw answer text and source metadata are saved together, so reloading does not destroy the source relationship. The source panel renders excerpts as plain text to prevent PDF content becoming executable markup.

**Tradeoff:** rendered images give predictable page navigation but do not offer text selection or search. Use **Open original PDF** for the browser's full PDF controls. A physical PDF page may differ from a printed page label such as `iv` or `12`; the interface deliberately says **PDF page**.

## Try it

1. Attach a PDF and ask a concrete question such as “What is the supplies budget, and who coordinates collection?”
2. Click the inline page link; compare the answer with the original page. Try Previous/Next and the page number form.
3. Expand **Source pages** to see the text the model actually received.
4. Ask for information absent from the document. The model should say the excerpts do not contain it. This behavior is model dependent and should be checked, not assumed.
5. Reload the conversation and click the same link again. Older answers created before this feature have no citation metadata and are not retroactively rewritten.

For an API example, replace the ID with an uploaded, ready document:

```powershell
$body = @{pdf_ids=@(72); question='What is the supplies budget? Cite the page.'} | ConvertTo-Json
curl.exe -N http://127.0.0.1:8888/summarizer/chat -H 'Content-Type: application/json' --data-raw $body
Start-Process 'http://127.0.0.1:8888/summarizer/documents/72/view?page=2'
```

Run checks from `pdf-summarizer-backend`:

```powershell
.\venv_win\Scripts\python.exe -m pytest -q
```

The citation tests use synthetic PDFs and mocked generation/search for repeatability. They cover page boundaries and blank pages, reference retention, metadata-preserving retrieval, index write ordering, context-budget excerpts, concurrent/retryable legacy upgrades, streamed citation validation, frontend marker rendering, and viewer page/path/escaping limits. Browser checks with the real model complement these tests; they do not establish correctness for every document or question.

Implementation verification: **99 tests passed**. The test runner reports one existing Starlette/httpx TestClient deprecation warning. Live browser checks with the selected local model verified a page-2 citation, Previous/Next navigation, reloaded conversation links, a missing rain-date answer, and a question attached to a five-page PDF finding a fact on page 2 outside the overview's page sample. Desktop (1,360px) and mobile (390px) source panels and viewer fit without horizontal page overflow. The source disclosure contrast correction was reviewed as resolved. A regression check also ensures the summary notice counts only page excerpts that survive context budgeting. No model change or new dependency was required.
