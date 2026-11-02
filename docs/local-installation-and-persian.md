# Local installation and multilingual exams

## Installing

Double-click **Install_DocuMind.cmd** in the project folder. It starts the Windows setup script, checks Python, Node.js, Docker Desktop and Ollama, and offers the official WinGet installers for missing prerequisites. Vendor permission, first-run, licence and reboot prompts remain interactive. Setup never claims completion while Docker/WSL is unavailable; rerun the same file to resume.

The installer creates/reuses `.venv`, downloads `qwen3:4b-instruct-2507-q4_K_M` for text and `bge-m3` for multilingual retrieval, builds Next and the backend image, caches CPU search assets, enables local-only mode and verifies backend health. Ollama resumes model blobs and verifies them. Allow at least 10 GB free; model files alone are approximately 3.7 GB. A GPU helps, but CPU operation is supported and slower; 16 GB system RAM is a practical recommendation, not a benchmarked minimum.

After successful setup, use **Start_DocuMind.bat** or the **DocuMind Local** desktop shortcut. The launcher selects a usable local port and opens the actual address. Keep the project folder in place; this is a double-click project installer, not a signed MSI or a standalone bundled executable. It does not move private PDFs into a system installation folder.

Run `Install_DocuMind.cmd -CheckOnly` for a read-only prerequisite/model/build report. If an update changes dependencies or the frontend, rerun the installer. Existing PDFs, SQLite data, older models and older vector collections are retained. Setup replaces only its owned environment keys and preserves other settings without displaying credentials.

Initial installation needs internet for software, container layers, fonts and models. After these assets are installed, normal local text/PDF use needs no internet. This is **offline operation in a local browser**, not public internet hosting. Optional vision models and Docling require separate installation; the text workflow does not silently download them.

## Why these files exist

- `Install_DocuMind.cmd` is the double-click entry, so a fresh user does not need Python to start setup.
- `scripts/install-windows.ps1` finds or installs Windows prerequisites, refreshes PATH, starts Docker Desktop when needed, creates a launcher environment and adds a desktop shortcut without replacing an existing one.
- `setup_documind.py` uses Python's standard library to inspect services, select an available Ollama port, download models with progress, preserve settings, build/cache assets and check health. `.venv/setup-ready.json` is written only after successful verification.
- `Start_DocuMind.bat` enters setup if that completion marker is absent; ordinary launches reuse the installed environment rather than installing the classic Streamlit dependencies.

The distinction is **installation versus runtime**: network access is needed to obtain software once; a runtime should use the software already on disk. The backend's local-only mode rejects hosted providers and cloud-labelled/delegating Ollama models. FastEmbed is configured to use cached files only; missing caches cause an actionable setup failure rather than a hidden background download.

## Language and mathematical formatting

The model is not retrained by this change. It is an existing multilingual local model, combined with language instructions and source retrieval. The answer-language selector can match the question/paper or request a supported language. Script detection handles Persian/Arabic and several other writing systems; Latin-script questions also carry an instruction to answer in their own language. Automatic language identification and translation are not universally reliable. Explicit language selection resolves ambiguity.

`app/services/languages.py` normalizes Persian/Arabic digits and Arabic presentation-form characters, detects common scripts, builds language instructions and localizes the Persian calculator text. The model receives the language rule in chat, study, summary and exam flows. A successful calculation still verifies the interpreted inputs rather than the wording of the original problem.

The shared `Answer` renderer automatically parses `$…$`, `$$…$$`, `\(…\)` and `\[…\]`, preserves code blocks and produces KaTeX HTML plus MathML. Models are instructed to choose mathematical notation without requiring the student to ask each time. Persian prose uses a locally bundled Vazirmatn fallback, automatic text direction and isolated left-to-right equations/citations. LaTeX commands remain untrusted and expansion stays bounded.

The Docker image includes Persian and Arabic OCR packs alongside English. OCR output is editable and unverified; scans and handwriting can still be wrong. Native PDF extraction now normalizes presentation-form text. Question parsing handles Persian question prefixes, Persian/Arabic digits and number/content splits found in real PDF text extraction.

## The exam workflow

1. Upload study notes to a workspace.
2. Open **Exam paper**, then **Upload question paper**. The paper can be separate from the workspace's three reference slots.
3. Select study references and an answer language; leave it on **Match question / exam** for the detected paper language.
4. Choose **Answer this paper**. Up to 20 numbered questions run sequentially, with progress and cancellation. No excess questions are silently omitted.
5. Review each answer, its citations and any interpreted mathematical inputs. Completed question answers are saved in Study library even if a later question fails or the task is stopped.

The question paper supplies questions, not evidence for answering itself. `ExamRequest` rejects overlapping exam/reference IDs. Each question has its own source map, so `[S1]` on one answer cannot accidentally resolve to another question's sources. Embedded instructions in a paper are treated as untrusted data. Unsupported questions and missing evidence remain explicit.

Mathematical interpretation requires review by default. The optional **Calculate model-interpreted mathematics automatically** control explicitly authorizes tool calculation for that run, but does not certify the model's interpretation. Generated rubric feedback and arbitrary proofs are not independently verified.

## Multilingual indexes

BGE-M3 produces 1,024-dimensional vectors; the previous Nomic collection uses 768. Mixing them would fail or corrupt retrieval assumptions. Setup selects a separate `pdf_chunks_bge_m3_1024` collection and leaves the old one intact. Selected existing documents can rebuild their index from saved page text without re-uploading originals. The English-only cross-encoder is skipped for Persian/Arabic/CJK queries rather than being advertised as a multilingual relevance improvement.

## Persian sample and verification

Public fixtures: `docs/examples/persian/study-fa.pdf` and `exam-fa.pdf`, generated by `evaluation/persian_exam.py`. Their PNG companions are programmatic renders of those PDFs, not generated photographs or private documents. The notes define energy, state an initial water temperature, include a quadratic example and explicitly omit a laboratory name. The exam asks four corresponding questions, including the missing-information case.

Run from `pdf-summarizer-backend`:

```powershell
.\venv_win\Scripts\python.exe evaluation/persian_exam.py
```

The evaluation uses the real upload/index/model/calculator pipeline, checks Persian output, expected facts, roots, mathematical notation, missing evidence and reference-only citations. It explicitly approves calculation for this known synthetic fixture. Results are written to `output/persian-exam.json`; one small fixture is not an accuracy estimate for arbitrary exams. The final handoff records actual results, timings and any failures rather than promising 100% answer accuracy.

## Actual verification on this computer

The full Windows setup completed: both models downloaded, Next and the Docker backend built, retrieval assets cached, health verified and a desktop shortcut created. The read-only check subsequently reported setup complete. Existing prerequisites were already installed here; installing missing prerequisites on a clean Windows VM has **not** been tested. Docker's first-run/WSL requirements can still need user interaction or a reboot.

The final real-model fixture passed **10/10 checks**, with four Persian responses: energy is the ability to do work; initial temperature is 20 °C; the equation has roots 2 and 3, verified by the calculator; the laboratory name is absent from the notes and explicitly classified as `needs_information`. The warm API run took 5.7 seconds on this machine; this tiny cached example is not a general speed benchmark. Separate browser runs checked right-to-left output, rendered equations and clickable reference handlers. The citation action called the correct local PDF/page URL and that file returned HTTP 200; this automation harness did not expose the new PDF tab as a popup event. A spaced/localized marker such as `[ S1 ]` or `[س۱]` is normalized, but an unknown source ID never becomes a source link.

Early trials exposed two real problems: the structured math prompt exceeded the context budget, and the model once interpreted “solve” as a derivative operation. The first was fixed by compacting the duplicated schema and budgeting references separately. An explicit single-variable equation with a clear solve request now goes directly into the restricted calculator plan; general word problems still require interpretation review. These failures are retained in diagnostic reports rather than hidden.

A process-level socket guard also passed **6/6 offline checks**: 1,024-dimensional embeddings, local retrieval, cached reranking, local generation, checked mathematics and no nonlocal connections. This tests the core backend process; it is not an OS-wide air-gap test or a disconnected clean-machine installation test. The machine's Qdrant client/server version warning remains, although the tested requests succeeded.

The full test suites passed: **217 backend tests**, **61 frontend tests**, **7 browser tests**, plus the production build. Backend coverage rounded to 86%; frontend statement coverage was 84.51%. Most unit tests use controlled substitutes; the Persian fixture and offline smoke are additional real-service checks.

## Learn the important code

Changed-code map (links resolve from this guide):

| Feature | Important implementation |
| --- | --- |
| Double-click setup, prerequisite checks and shortcut | [Windows setup](../scripts/install-windows.ps1), [resumable installer](../setup_documind.py), [launch entry](../Start_DocuMind.bat) |
| Local model defaults and runtime network boundary | [Compose settings](../docker-compose.yml), [model requests](../pdf-summarizer-backend/app/services/llm_service.py), [request validation](../pdf-summarizer-backend/app/schemas.py) |
| Language matching, native digits and Persian OCR | [language helpers](../pdf-summarizer-backend/app/services/languages.py), [PDF processing](../pdf-summarizer-backend/app/services/pdf_processor.py), [OCR packages](../pdf-summarizer-backend/Dockerfile) |
| Multilingual search with a separate vector collection | [vector storage](../pdf-summarizer-backend/app/services/vector_db.py), [retrieval](../pdf-summarizer-backend/app/services/advanced_retrieval.py) |
| Separate exam/reference documents and per-question status | [exam job](../pdf-summarizer-backend/app/services/exam_assistant.py), [study generation](../pdf-summarizer-backend/app/services/study_assistant.py), [exam UI](../documind-web/components/exam-runner.tsx) |
| Automatic mathematics and RTL reading | [answer renderer](../documind-web/components/answer.tsx), [language selector](../documind-web/components/language-select.tsx), [study styles](../documind-web/app/study.css) |
| Checked equations and bounded local context | [study interpretation](../pdf-summarizer-backend/app/services/study_assistant.py), [restricted calculator](../pdf-summarizer-backend/app/services/math_engine.py), [token budgeting](../pdf-summarizer-backend/app/services/context_budget.py) |
| Real Persian/offline evaluation | [Persian sample runner](../pdf-summarizer-backend/evaluation/persian_exam.py), [offline smoke](../pdf-summarizer-backend/evaluation/offline_smoke.py), [multilingual tests](../pdf-summarizer-backend/tests/test_multilingual.py) |

Setup updates only settings it owns and writes them atomically:

```python
temporary.write_text('\n'.join(result) + '\n', encoding='utf-8')
temporary.replace(path)
```

In `setup_documind.py:update_environment`, `result` contains preserved unrelated lines plus the selected owned keys. A temporary file is replaced only after it has been written, reducing the chance of a partially written configuration. It never prints the original settings. Missing software, download failures or unhealthy services stop setup before the completion marker is written. Rerunning resumes model blobs and repeats the verification.

Exam inputs separate the task from the evidence:

```python
if self.exam_pdf_id in self.reference_pdf_ids:
    raise ValueError('Choose study references separately from the question paper.')
```

`app/services/exam_assistant.py:ExamRequest` validates document IDs before a job starts. `exam_events` extracts numbered questions, creates one `StudyRequest` at a time, retrieves only from the selected study references, saves each result and emits progress. A failed question is stored as failed and does not erase completed answers. Cancellation propagates instead of being converted into a successful answer. Sequential work bounds local model contention; large batches do not run in parallel.

For factual exam answers, the model must return validated structured output:

```python
class EvidenceAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['answered', 'needs_information']
    answer: str = Field(min_length=1, max_length=12000)
```

`study_assistant.py` requests this schema in the same grounded generation call. `exam_assistant.py` passes its status to storage and the UI. Thus an unsupported question can show **More information needed** and increment the review count; the application does not classify that state by searching for translated refusal phrases. This is the model's evidence assessment, not an independent factual verifier. Invalid JSON or an invalid status fails that question rather than silently displaying success.

Language and typography are separate responsibilities. `languages.py` supplies a language instruction and normalizes native digits before calculation; `Answer` renders the model's mathematical delimiters with KaTeX. The browser receives plain answer text and server-owned source metadata, not model-written PDF URLs. A citation button opens the server's actual PDF ID and page. A real page citation demonstrates where evidence came from; it does not independently prove that every claim follows from that evidence.

```python
DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
# Used before the restricted calculator parses an expression:
text.translate(DIGITS)
```

For example, `۲*x=۸` becomes `2*x=8`, preserving its numerical meaning. Arabic presentation-form glyph encodings are normalized with Unicode NFKC before indexing, so visually readable Persian PDF text is searchable as ordinary characters. OCR packs handle installed Persian/Arabic scans, but cannot guarantee correct recognition.

```tsx
<ReactMarkdown
  remarkPlugins={[remarkGfm, remarkMath, citationPlugin(sources)]}
  rehypePlugins={[[rehypeKatex, {trust: false, throwOnError: false,
    maxExpand: 100, maxSize: 20, output: 'htmlAndMathml'}]]}
>
  {mathMarkdown(text)}
</ReactMarkdown>
```

This core of `components/answer.tsx` turns Markdown math into readable typesetting with an accessible MathML representation. `trust:false` prevents trusted LaTeX commands from being enabled. Equations stay LTR while surrounding Persian prose is RTL; the local Vazirmatn font removes the need for a runtime web-font request. No student formatting instruction is necessary for ordinary equations.

For explicit equations, `study_assistant.py:explicit_equation` recognizes a narrow, allowlisted input and routes it to `math_engine.py`, whose restricted parser rejects arbitrary Python. The final answer distinguishes the extracted question, interpreted calculator inputs and checked result. That provides a verifiable calculation without claiming to verify arbitrary proofs or OCR interpretation.

Proposed repeat checks from the project root:

```powershell
.\Install_DocuMind.cmd -CheckOnly
.\pdf-summarizer-backend\venv_win\Scripts\python.exe -m pytest pdf-summarizer-backend/tests -q
npm --prefix documind-web run test
npm --prefix documind-web run build
$env:DOCUMIND_TEST_URL='http://127.0.0.1:4400'
npm --prefix documind-web run test:e2e
.\pdf-summarizer-backend\venv_win\Scripts\python.exe pdf-summarizer-backend/evaluation/persian_exam.py
```

`venv_win` is the development test environment on this checkout, not an installer prerequisite. Normal users only need the two double-click entry files. The sample evaluation creates a public demo workspace and saves answers; it is deliberately not a read-only check.
