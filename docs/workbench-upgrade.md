# DocuMind workbench: engineering and code walkthrough

This upgrade keeps FastAPI, Ollama, Qdrant and SQLite and adds an independent Next.js 16 / React 19 / TypeScript frontend in `documind-web`. The Streamlit source and its saved conversations are preserved. No existing document files are deleted or re-uploaded by the migration.

## Start and check the application

From the project root:

```powershell
cd documind-web
npm ci
npm run build
npm run start -- --port 3100
```

Open `http://127.0.0.1:3100`. The Node server proxies `/api/summarizer/...` to the local FastAPI service on port 8888. Set `DOCUMIND_BACKEND_URL` in the Node process environment if that address differs. Docker/Qdrant and Ollama must still be running. `launcher.py` now starts the production Next server by default, after starting the existing backend stack. It requires the build above. `DOCUMIND_UI=classic` selects the old Streamlit frontend; set its URL to port 8501 if also overriding `DOCUMIND_FRONTEND_URL`. The Classic interface link requires Streamlit to be running.

The new frontend saves conversations in **this browser's local storage**, separately from Streamlit's JSON history. Export conversation downloads a JSON backup. API keys are kept only in component memory and are never included in the saved workspace. Clearing browser storage clears new conversation history, but does not remove original PDFs in the backend. There is no automatic import or synchronization of Streamlit history in this release.

## Follow-up questions: give retrieval context

**Problem:** searching only for “Who approved it?” loses the subject. The language model sees history later, but may already have been given the wrong evidence.

`app/services/retrieval_context.py` implements `retrieval_query`. It detects common conversational references and combines the current question with up to two earlier **user** questions, each capped at 700 characters:

```python
previous = [message["content"] for message in history if message["role"] == "user"][-2:]
context = "\n".join(text[:700] for text in previous)
return f"Earlier user questions:\n{context}\nCurrent question:\n{question}", True
```

`routers/summarizer.py` uses that string for Qdrant search. It still gives the original question and bounded conversation history to the answering model. A metadata flag lets the interface say conversation context was used. Failed and stopped assistant drafts are excluded from history by `lib/workspaces.ts`.

**Try:** ask “What is the approved supplies budget?” and then “Who approved it?” on the evaluation fixture. **Tradeoff:** this is a bounded heuristic, not a model rewrite or guaranteed pronoun resolution. It adds no extra generation round trip, but old questions can sometimes dilute search. The real-model fixture tests the expected follow-up case; ambiguous multi-topic conversations remain a limitation.

## Complete reviews: every readable page, bounded prompts

**Problem:** the quick overview samples start/middle/end pages, so it cannot claim to review every page.

`SummaryRequest.mode` accepts `quick` (default for compatibility) or `complete`. `services/complete_review.py` reads the saved page rows and splits **every readable page** into overlapping segments capped at 1,800 UTF-8 bytes. A byte is a unit of encoded text; this bound also protects the conservative token counter for Chinese text and emoji. The model still uses the existing 8,192-token context, with space reserved for the answer. If budgeting would shorten a segment, the review fails explicitly rather than silently skipping text.

```python
for index, (source, text) in enumerate(segments):
    yield event("status", phase="reviewing", message=..., completed=index, total=len(segments))
    # Read cached result or generate this segment's findings.
    yield event("text", content=heading + result["answer"])
```

Each one-source model prompt uses **local `[S1]`**. The server validates that marker, then maps it to the complete review's stable page ID, such as `[S7]`. This avoids asking a small model to keep an arbitrary global source counter in mind. The mapped answer retains its actual original PDF page.

Caching uses a SHA-256 digest: a stable fingerprint of the document/page text, selected model/provider, answer length, directive, account fingerprint and review version. `ReviewCache` in `models.py` stores completed segment results in SQLite. Changing any relevant input invalidates reuse. Credentials are hashed for account separation and are not stored in cache values. Successful segments are committed separately, so failure or cancellation does not discard completed work. Restarted reviews reuse matching segments; failed or truncated segments are not cached.

**Output:** a complete, page-by-page report of segment findings, not one final compressed global synthesis. This avoids dropping earlier findings into a single final context window. It does not guarantee that every fact was understood or that contradictions between distant segments were resolved. Extraction/OCR warnings and unreadable pages still matter. The local resource limit is 600 segments per review; larger documents receive an actionable error. Cache entries currently have no automatic eviction; local cache maintenance is a future lifecycle task.

**Try:** click Complete review, inspect its coverage details, then run it again. The second run should report cached segments when settings and evidence match. Live checks on the synthetic two-page PDF completed both pages, then reused both cached segments.

## Quote checking: validate exact passages

**Problem:** a valid source marker identifies a real page, but the model may quote words that the excerpt never contained.

`check_quotes` in `services/citations.py` checks explicit straight/curly double-quoted passages of at least 12 characters. It ignores code, normalizes case and whitespace, and compares each quote with excerpts named by nearby citation markers. Unknown source IDs still fail the answer. An unmatched explicit quote now emits an error rather than a successful completion. Quote-check records accompany successful answers.

```python
checks = check_quotes(answer, metadata.get("sources", []))
if any(not check["verified"] for check in checks):
    raise GenerationError("A quotation could not be matched to its cited excerpt. ...")
```

**Try:** ask for the exact workshop-time sentence and its citation. A quote with 999 dollars cannot match a source saying 240 dollars. **Tradeoff:** this is exact-passage checking, not semantic verification. It does not check every paraphrase, short quote, single-quoted phrase or blockquote. OCR can alter spelling. The UI never presents this as an overall factual confidence score. In the new frontend, failed drafts remain visibly labeled for inspection, are excluded from history, and cannot become completed answers. Streamlit retains its existing behavior of saving completed answers only.

## Stop, retry, progress: generation jobs

**Problem:** a long request needs a stable identity so another request can stop it, while the browser receives real progress and handles disconnects.

`services/jobs.py` owns a bounded job registry. `routers/jobs.py` exposes:

| Endpoint | Behavior |
| --- | --- |
| `POST /summarizer/jobs` | Accept `{kind: "chat" | "summary", payload: ...}` and return a job ID with HTTP 202 |
| `GET /summarizer/jobs/{id}` | Current state without prompt, document text or credentials |
| `GET /summarizer/jobs/{id}/events?after=0` | Replay NDJSON events, then follow new events |
| `POST /summarizer/jobs/{id}/cancel` | Cancel the owned task and close its generation stream |

NDJSON means one JSON object per line. Text and control events are separate. State moves through preparing, waiting, generating, then completed/failed/cancelled. Complete reviews additionally report actual segment counts. Heartbeats keep idle connections alive without claiming generation progress. A replay cursor counts events, not tokens.

```python
job.task.cancel()
await asyncio.gather(job.task, return_exceptions=True)
```

Cancellation propagates through the async generator and closes the Ollama/provider HTTP stream, releasing the local generation lock. A PDF process already running cannot be forcibly cancelled by this job; it keeps its executor slot until finishing. The UI Stop action cancels the job and aborts its stream. Leaving the page sends a best-effort cancellation beacon; network failure can prevent delivery. Retry uses the same saved PDFs and reuses completed review segments, rather than uploading again. Failed drafts stay labeled and excluded from future prompt history.

**Tradeoff:** this registry supports the current **single API process**. It allows four active jobs, retains up to 32 jobs and expires terminal jobs after about 30 minutes. Jobs do not survive a backend restart. A real multi-worker deployment would require shared job state/coordination; this release does not pretend to be a durable task queue. Review caches survive restarts. Existing direct chat/summary endpoints still work.

## Next.js workbench: evidence beside the answer

`app/page.tsx` coordinates upload, indexing, generation, retry, preferences and workspace storage. Pure protocol functions live in `lib/api.ts`, persistence/history rules in `lib/workspaces.ts`, and typed data contracts in `lib/types.ts`. `app/api/[...path]/route.ts` proxies only the fixed backend API namespace, streams request/response bodies, preserves PDF range-related headers, and returns an actionable 502 if the backend is unavailable.

`components/answer.tsx` parses Markdown and transforms known citation markers into buttons. It skips code and existing links. Raw HTML from the model is not executed. Clicking a citation passes the server-owned `Source` object to `openSource`:

```tsx
setPage(source.page);
setViewDoc(workspace.documents.find(d => d.id === source.pdf_id));
setSelected(source);
setMobileView("evidence");
```

The original page image appears in the PDF pane, and the selected excerpt remains visible below it. Mobile uses Conversation / PDF & evidence tabs, keeping the composer separate from the viewer. Original PDF access remains available for text selection and native PDF controls. An image renderer is predictable across browsers but is not a full PDF editing/search application.

The new design uses bundled Instrument Sans fonts, semantic CSS tokens, tonal green surfaces, quiet navigation and one evidence-selection transition. Fonts work locally after installation; there are no runtime Google Fonts requests. Reduced motion disables spatial transitions. API credentials are not saved with conversations. The new frontend is still a local single-user app, not an authenticated multi-user service.

## Tests and real-model evaluation

Run from `pdf-summarizer-backend`:

```powershell
.\venv_win\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv_win\Scripts\python.exe -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=80
.\venv_win\Scripts\python.exe evaluation/run_quality.py --output ../output/quality.json
```

The evaluation command intentionally creates one synthetic five-page PDF in the backend. It does not read private documents. It checks known facts, follow-ups, missing information, a superseded conflicting draft, exact quotes and an instruction-injection example. The report records answers, expected-page citation checks, first-text latency and actual Ollama generation metrics. Keyword and page checks are useful regressions, not a general accuracy percentage. The entire six-case suite passed in the final live run; the initial strict quote-format failure prompted a general prompt improvement, not a relaxed evaluator.

Run from `documind-web` with the production server on port 3100:

```powershell
npm run typecheck
npm run test:coverage
npm run build
npm run test:e2e
```

Frontend coverage thresholds guard statements, branches, functions and lines. Component tests exercise real React interactions with mocked API boundaries. Browser tests cover upload-to-answer-to-source flow, saved conversations, mobile tabs, settings keyboard dismissal and key-storage isolation using synthetic API responses. Separate live browser/API checks exercise actual PDF rendering, Ollama generation, complete review caching and cancellation. A passing test suite cannot prove every model answer correct.

The old Starlette/httpx TestClient deprecation warning remains. It does not fail tests. Original-page rendering and generation require the actual local services to be available; backend unit tests deliberately mock external boundaries.

See [the final verification record](workbench-verification.md) for actual test counts, coverage, live-model results and UI review scope. Framework reference: the frontend follows the [Next.js App Router installation](https://nextjs.org/docs/app/getting-started/installation) and uses native fetch/streaming route handlers. Actual local generation counts/timings come from the [Ollama chat response metrics](https://docs.ollama.com/api/chat), not received network chunk counts.
