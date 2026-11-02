# Exam answering and offline transfer

The primary exam task is now **source PDFs → question PDF → direct answers**. The exam desk opens first at `/study`. Worked explanations and tutoring remain optional. Existing conversations, documents and local data are preserved.

## Long sources

All readable pages are extracted, stored and indexed, including sources over 100 pages. Each question searches that full index; relevant page excerpts are budgeted into the model's 8,192-token context. This is retrieval from the whole source, not a claim that every page fits into one generation prompt. Scanned/unreadable pages can still lack usable evidence.

`advanced_retrieval.py:heading_matches` supplements hybrid search with explicit numbered headings. A Persian reference to `فصل ۱۲` can find `Chapter 12`, without accidentally matching chapter 120. Structural labels are normalized; this is not unrestricted translation or a replacement for semantic retrieval.

## Reviewed questions and answer classification

Open **Review or correct questions** to compare full extracted text with its original page. Correct symbols, choices, page numbers and subquestions. Add/split/remove reviewed questions before a run. Up to 100 reviewed questions are accepted. Text over 8,000 characters is retained and explicitly blocked until split; it is never silently shortened. More than 200 detected boundaries is an explicit parser error.

Native PDF soft hyphens can represent mathematical minus signs. Mathematical parsing normalizes them and the review screen flags their presence. This does not certify OCR: inspect the original page when notation is uncertain.

The exam router uses a validated local classification for concept, calculation, multiple-choice, proof, diagram and statistics questions. A required missing figure produces `needs_information`. Supported calculations use the bounded calculator; other answers remain source-grounded model output. General proofs/statistics are not independently verified by classifying them.

Factual answers require structured evidence fields. A response saying a requested datum is unavailable is distinct from solving that question. Conservative refusal detection also flags common absence statements; it can overflag a question asking specifically what is absent. No confidence percentage is manufactured.

Direct mathematical answers show the result; **Calculation checks & assumptions** and calculator-input disclosures provide detail separately. Automatic model-interpreted calculation remains an explicit checkbox. Worked explanation is an optional answer format.

## Interrupted runs

`ExamRun` stores the original safe settings, reviewed question snapshot, document hashes and a per-question answer map. Credentials are excluded. A stable saved-answer key prevents duplicate library items around a crash:

```python
key = f'exam-{run_id}-{question_index}'
```

Use **Saved runs & recovery → Resume saved run** after stopping, reloading or restarting the backend. Completed responses are replayed; failures are retried. Original settings are reused. A changed source/question-paper hash rejects resume and requires a new run. Responses needing information remain reviewable responses; their completion is not advertised as a correct solution. The API's `retry_numbers` accepts zero-based question indexes for deliberate reruns.

The run claim prevents concurrent execution within the single backend process. After restart, a new process identity can reclaim an interrupted run. This is not a distributed queue for multiple API workers.

## Feedback and export

Each saved answer offers **Report or correct this answer**. Interpretation, calculation, citation and missing-information feedback is stored locally as a separate item. It does not silently replace the generated answer or automatically retrain the model.

**Print / save answers as PDF** opens a locally rendered answer sheet with KaTeX, Persian fonts, source filenames and page numbers. Use the browser's Print / Save as PDF; Markdown export is also available. No hosted rendering service is involved.

## Complete workspace backup

**Download complete workspace ZIP** includes the original PDFs referenced by the workspace, its saved page text, annotations, study items and exam checkpoints. It excludes model files, provider credentials, executable settings and disposable indexes. This is a private archive; do not upload it to GitHub.

**Restore workspace ZIP** verifies members, checksums, PDF readability/page counts and size bounds, then creates a new workspace with remapped document/run IDs. Existing work is not overwritten. Search indexes rebuild from saved text on first use. Limits: 200 MB compressed, 500 MB expanded, 500 documents and 30 MB JSON metadata. The earlier JSON/database exports remain available but do not include original files.

## Offline transfer folder

After normal setup and a production frontend build, run on Windows x64:

```powershell
.\.venv\Scripts\python.exe scripts/build_offline_bundle.py --download-prerequisites
```

The output is `output/offline-bundle/`. It includes:

- Application source, built Next.js files and its installed dependencies.
- Local Node and Ollama binaries, the two required model manifests and verified blobs.
- Cached retrieval assets and exported backend/Qdrant container images.
- Launcher dependency wheels for the builder's Python minor version.
- Official Python, Docker Desktop and WSL installers with validated Windows signatures.
- A SHA-256 file manifest and `Install_Offline.cmd`.

Copy the **whole folder** to a permanent location on the destination Windows x64 computer. Run `Install_Offline.cmd`; complete vendor installation, virtualization/WSL and reboot prompts if required. The script verifies integrity, installs launcher wheels with `--no-index`, loads container images and writes local settings. Start `app/Start_DocuMind.bat`. Offline mode uses `docker-compose.offline.yml` with `pull_policy: never` and does not rebuild images at launch.

```powershell
# Verify a newly prepared transfer folder without installing it:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File output/offline-bundle/install-offline.ps1 -CheckOnly
```

The bundle is generated for Windows x64, not every operating system. Vendor licence terms still apply. Windows features, supported OS, virtualization and drivers remain prerequisites; an installer cannot enable firmware virtualization. File hashes establish integrity relative to the manifest, not an independent publisher signature. The bundle is intentionally excluded from Git and contains no user PDFs/database/live `.env`. Use `--refresh` only to rebuild an owned generated output bundle. `--refresh-code` updates its app/build/container code while retaining immutable runtime/model hashes; run `-CheckOnly` afterward to check every file again.

## Verification and security

`evaluation/exam_benchmark.py` supplies 50 generated bilingual regression cases over a 120-page source: opaque reference-code lookups, checked equations and deliberately missing information. The question paper is rendered as a real PDF and extracted before evaluation. It measures answer correctness, expected-page retrieval and language separately. These oracles are synthetic, **not teacher-reviewed curriculum accuracy**. Results and early failure diagnostics stay in ignored `output/exam-benchmark/`.

```powershell
.\pdf-summarizer-backend\venv_win\Scripts\python.exe pdf-summarizer-backend/evaluation/exam_benchmark.py
# Teacher-reviewed/custom cases with the same case schema:
.\pdf-summarizer-backend\venv_win\Scripts\python.exe pdf-summarizer-backend/evaluation/exam_benchmark.py --cases my-cases.json --source my-course.pdf
```

The GitHub workflow builds/tests the backend/frontend and scans reachable history with checksum-verified Gitleaks. Real local-model evaluation is separate from mocked CI tests. `.pre-commit-config.yaml` also supplies a local Gitleaks hook (`python -m pip install pre-commit`, then `python -m pre_commit install`). The first hook environment setup requires internet; normal installed application use does not.

GitHub secret scanning and push protection were enabled on the repository. No credential values are included in workflow files, archives or reports committed to Git.

## How the implementation fits together

The routes remain FastAPI, the durable state remains SQLite and the interface remains Next.js. These changes do not require a hosted API or another database. A **checkpoint** is a saved snapshot that lets a later request continue the same task. **Idempotency** means replaying completed work does not create duplicate saved answers.

| Feature and actual code | Inputs → outputs and failure handling | Practical check and tradeoff |
| --- | --- | --- |
| Direct exam orchestration: [exam_assistant.py](../pdf-summarizer-backend/app/services/exam_assistant.py), [exam-runner.tsx](../documind-web/components/exam-runner.tsx) | Source IDs + separate paper ID + reviewed questions → per-question answers/status/events. Source hashes reject resuming against changed evidence. | Upload the public PDFs below; direct mode should answer, not turn each response into a lesson. All pages are searchable, but only bounded relevant excerpts enter each prompt. |
| Question correction: [exam-review.tsx](../documind-web/components/exam-review.tsx), [study_assistant.py](../pdf-summarizer-backend/app/services/study_assistant.py) | Full detected text and page → editable run snapshot. Long text is preserved with an explicit split requirement; ambiguous notation stays reviewable. | Edit a question beside the original page, split it, then submit. Manual correction adds a review step but avoids silently answering damaged OCR. |
| Task routing and missing evidence: [study_assistant.py](../pdf-summarizer-backend/app/services/study_assistant.py), [exam_assistant.py](../pdf-summarizer-backend/app/services/exam_assistant.py) | Question category → calculator or grounded local-model answer. Structured sufficiency/missing-information fields yield `needs_information`; invalid output fails safely. | Ask the public source for the instructor's birth date. Classification routes work; it does not establish correctness of arbitrary proofs or diagrams. |
| Deep-source retrieval: [advanced_retrieval.py](../pdf-summarizer-backend/app/services/advanced_retrieval.py) | Question + every stored source page → hybrid hits, with exact numbered-heading matches first. | Ask for Topic 119. Exact-heading matching helps explicit references; abstract cross-language paraphrases still depend on embeddings and the model. |
| Resume: [exam_runs.py](../pdf-summarizer-backend/app/services/exam_runs.py), [study.py](../pdf-summarizer-backend/app/routers/study.py) | Run ID → saved responses plus generation for unfinished/failed questions. Concurrent claims return 409; cancellation checkpoints interruption. | Stop after the first answer, reload and resume. This is single-process recovery, not a distributed worker system. |
| Inspectable math: [math_engine.py](../pdf-summarizer-backend/app/services/math_engine.py), [exam-runner.tsx](../documind-web/components/exam-runner.tsx) | Parsed equation → bounded symbolic result, inputs, checks and assumptions. Unsupported/ambiguous input needs review. | Solve `x^2 - 5*x + 6 = 0`, inspect inputs and substitution checks. A valid calculation does not prove that OCR interpreted the original problem correctly. |
| Answer feedback: [answer-feedback.tsx](../documind-web/components/answer-feedback.tsx), [exam_runs.py](../pdf-summarizer-backend/app/services/exam_runs.py) | Reason + optional correction → separate local feedback item; save failure leaves the form retryable. | Report an incorrect citation, then confirm the original answer remains intact. Feedback is for review; it does not fine-tune the model. |
| Bilingual export: [print/page.tsx](../documind-web/app/study/print/page.tsx), [exam-export.ts](../documind-web/lib/exam-export.ts), [answer.tsx](../documind-web/components/answer.tsx) | Saved answers → local KaTeX/RTL print sheet or Markdown. Used citations and uncited retrieved pages have different labels. | Print the Persian demo; check reference-code character order and page numbers. PDF export uses the browser's print dialog. |
| Portable workspace: [workspace_archive.py](../pdf-summarizer-backend/app/services/workspace_archive.py), [study_state.py](../pdf-summarizer-backend/app/routers/study_state.py), [workspace-transfer.tsx](../documind-web/components/workspace-transfer.tsx) | ZIP with original PDFs/checkpoints → validated new workspace and remapped IDs. Bad hashes/PDFs/paths fail before import commits; staged files are cleaned. | Export, restore and resume in the new workspace. Indexes rebuild lazily; model files belong in the separate install bundle. |
| Offline deployment: [build_offline_bundle.py](../scripts/build_offline_bundle.py), [install-offline.ps1](../scripts/install-offline.ps1), [launcher.py](../launcher.py), [offline compose](../docker-compose.offline.yml) | Prepared runtimes/models/build/images → integrity-checked installation using local wheels and images. Missing Windows prerequisites produce actionable setup errors. | Run `-CheckOnly` first. The large folder avoids runtime downloads, but firmware/driver/vendor setup remains machine dependent. |
| Regression/security checks: [exam_benchmark.py](../pdf-summarizer-backend/evaluation/exam_benchmark.py), [checks.yml](../.github/workflows/checks.yml), [pre-commit config](../.pre-commit-config.yaml) | Public or reviewed cases → correctness/retrieval/citation/language metrics; Git history → redacted secret scan. | Run the commands below. Synthetic cases make failures repeatable; authentic curriculum cases are still required for broader accuracy claims. |

The durable-run snapshot deliberately excludes provider credentials:

```python
run = {
    'request': request.model_dump(exclude={'api_key', 'api_base_url', 'run_id', 'retry_numbers'}),
    'versions': versions, 'questions': questions, 'language': language, 'answers': {},
}
```

The input is the validated request; `versions` identifies its source text. The output is safe persistent task state. Resume compares those versions before generating anything, then replays saved responses:

```python
if previous and previous['status'] != 'failed' and index not in request.retry_numbers:
    yield event('question', **previous, reused=True)
```

This avoids repeated model work. Failed questions are tried again; a user can explicitly include a question's zero-based index in `retry_numbers` for a deliberate rerun. API-only clients must use the original run settings, just as the UI does.

For example, after `POST /summarizer/study/exams/jobs` returns `run_id`, inspect it with `GET /summarizer/study/exams/runs/{run_id}`. Send the original job request with `run_id` added to resume. Feedback uses `POST /summarizer/study/exams/runs/{run_id}/feedback`:

```json
{"question_index":0,"reason":"citation","correction":"Please check the cited page."}
```

The benchmark explicitly distinguishes a search hit from an actual answer citation:

```python
cited_pages = {s['page'] for s in row.get('sources', []) if s['id'] in cited}
```

`cited` comes from citation markers outside code examples. A correct answer with the expected page retrieved can still fail the expected-page citation check. This catches a different defect from wrong retrieval or wrong answer text; it does not prove every natural-language claim follows from its cited passage.

## Recorded local verification

- 232 backend tests, 66 frontend tests, seven browser tests and the production frontend build passed.
- The real-model 50-case bilingual synthetic run extracted all 50 questions from the generated PDF and searched a 120-page source. Result: 50/50 answer checks, 30/30 expected-page retrieval checks, 30/30 expected-page citation checks and 50/50 basic language checks. The 10 calculations were checked; 10 missing-information cases were flagged. Median question time was 2.155 seconds on this machine, not a hardware-independent promise. The language check detects script, not fluency.
- Each benchmark case ran as its own one-question job after PDF extraction, with an explicit language setting; the separate four-question Persian demo tested a multi-question run and checkpoint recovery. This is not a measured 50-question continuous batch.
- Complete ZIP restore preserved the demo's original source bytes and 120 saved pages, remapped document/run IDs, retained all four responses and replayed them without regeneration.
- Offline launcher dependencies resolved from the bundle wheel folder using `--no-index`. Clean Windows vendor installation and an OS-wide disconnected-machine test remain unverified.

Public demonstration files: [120-page source](examples/long-exam/source-120-pages.pdf) and [Persian question paper](examples/long-exam/exam-fa-120.pdf). Early diagnostics remain in ignored local output. Different diagnostic fixtures are not a controlled before/after speed comparison.

```powershell
cd pdf-summarizer-backend
python -m pytest tests -q --cov=app
cd ../documind-web
npm run test
npm run build
$env:DOCUMIND_TEST_URL='http://127.0.0.1:4400'
npm run test:e2e
```
