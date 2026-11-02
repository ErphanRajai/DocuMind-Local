# Study and Solve: using and understanding the upgrade

The new workspace is at **http://127.0.0.1:4317/study**. PDF conversations remain at `/`. The visual system is the existing mineral-green / white / teal workbench, extended with mathematical typography. No Figma frame was supplied or claimed as a visual reference.

This is a local study application. Its calculator supports a defined expression language; it is not a universal proof checker. Images and model interpretations remain editable and unverified. Institutional accounts and shared courses retain the earlier condition that a deployment and identity design are needed first.

## A practical first session

1. Open Study desk and select a workspace, or add PDFs under Exam paper / Study library.
2. In Equation calculator, run `x^2 - 5*x + 6 = 0`. Inspect both roots and substitution checks.
3. Change to Differentiate and enter `x^3`. The result is rendered as mathematics; copy its LaTeX or export the solution as Markdown.
4. For a word problem, enter the question and choose Work this question. **Review the interpreted inputs before calculating.** Edit them if they misrepresent the question, then calculate the approved inputs.
5. Choose Explain from notes for sourced explanations, Compare documents for differing accounts, or Consolidate findings to review every readable segment before a final summary.
6. On a source card, open the original page, bookmark it, or save an annotation. The PDF conversation viewer also has searchable, selectable native PDF text and region highlights.
7. Save difficult problems, formulas or generated practice. Use Review queue to reveal answers and record actual recall outcomes.
8. Export a workspace backup from the header. Study library also offers a database backup; retain original PDF files separately.

The demo is explicitly synthetic. `evaluation/seed_study_demo.py` generates public notes, a short paper and a diagram, uploads the PDF through the real API, creates checked exercises, and saves a separate workspace. It never reads private PDFs. Its IDs are written to `output/study-demo.json`.

## How a question moves through the system

```mermaid
flowchart LR
  Q[Question or corrected image text] --> R[Bounded PDF search]
  R --> P[Operation-specific model interpretation]
  P --> U[Review or edit the inputs]
  U --> C[Bounded SymPy or Pint process]
  C --> V[Substitution, equivalence or dimensional checks]
  V --> A[Mathematical answer and linked evidence]
  A --> S[Saved attempts and revision queue]
```

Direct calculator input skips model interpretation. Models explain and interpret; mathematical tools calculate. A successful calculation checks its supplied inputs, not the meaning of a word problem.

## Mathematical display and input

**Problem:** ordinary Markdown cannot typeset fractions, roots, matrices or aligned equations properly.

**Files:** `documind-web/components/answer.tsx`, `lib/study.ts`, `app/layout.tsx`, `app/study.css`.

The existing Markdown renderer now uses:

```tsx
remarkPlugins={[remarkGfm, remarkMath, citationPlugin(sources)]}
rehypePlugins={[[rehypeKatex, {
  trust: false, throwOnError: false, maxExpand: 100, maxSize: 20,
  output: "htmlAndMathml"
}]]}
```

`remark-math` recognizes notation; KaTeX produces visual HTML and accessible MathML. Font files are bundled locally. Raw HTML is not enabled. Citations remain metadata-backed buttons outside mathematical nodes. `mathMarkdown` escapes clear currency amounts while preserving code and display equations. Wide equations scroll within their own container; unfinished streamed notation does not crash the answer.

**Try:** `$x^2$`, `$$\frac{1}{2}$$`, a matrix, a citation next to an equation, and `Budget: $240 and $480`. The calculator accepts `x^2`, `2*x`, `sqrt(x)`, Unicode squared/cubed, and a limited subset of LaTeX such as `\frac{x}{2}`. It does not pretend to parse arbitrary TeX programs. The preview shows notation; the backend still validates the expression.

**Tradeoff:** KaTeX supports a useful mathematical subset, not every LaTeX package. MathML availability is not a substitute for testing a specific screen reader.

## The calculator and its checks

**Problem:** a language model can confidently predict the wrong arithmetic or algebra.

**Files:** `pdf-summarizer-backend/app/services/math_engine.py`, `app/routers/study.py`, `documind-web/components/study-desk.tsx`.

The input is a validated `MathRequest`. Operations include solve, simplify, factor, differentiate, integrate, numeric evaluation, matrices, expression checking and unit conversion. `parse_expression` walks Python's syntax tree but constructs SymPy objects itself:

```python
if isinstance(node.op, ast.Div):
    if right == 0:
        raise ValueError('Division by zero is undefined.')
    if denominators is not None:
        denominators.append(right)
    return s.Mul(left, s.Pow(right, -1, evaluate=False), evaluate=False)
```

There is **no** `eval`, string `sympify`, `parse_expr`, generated Python, arbitrary import, filesystem command or network tool. The accepted syntax has length, node-count, number and exponent limits. Original denominators are retained so cancellation cannot quietly turn `x/x=1` into a claim that `x=0` is valid.

`solve_bounded` allows two calculations concurrently. `isolated_calculate` starts a separate child process, waits up to eight seconds, and reaps it on completion/error/timeout. Cancellation waits for that bounded child to be reaped before releasing its slot. This contains runaway symbolic work; it is not an operating-system memory sandbox for hostile multitenant workloads.

Outputs include a textual result, LaTeX, inputs, assumptions, explanatory steps, check results and an explicit `verified` flag. Finite roots are substituted into the original equation. Antiderivatives are differentiated. Simplification checks the difference between expressions. Inverses are multiplied by the original matrix. Pint checks dimensional compatibility for supported unit conversions. These checks have different strengths; their labels say what was actually checked. A returned empty/infinite solution set is not advertised as an independently proven finite-root check.

```powershell
$body = @{operation='solve'; expression='x^2-5*x+6=0'; domain='real'} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8888/summarizer/study/solve -Method Post -ContentType application/json -Body $body
```

**Try:** real vs complex `x^2+1=0`; a two-equation system; `36 km/h` to `m/s`; a 2×2 inverse; and `x^2=4` followed by working `x=2`. The final example changes the solution set and loses a root. Use the calculator's separate algebraic-working field for equations, and the student-working field for prose reviewed by the model.

**Tradeoff:** power rules and polynomial factorization have useful worked steps. Arbitrary theorem proofs, every integration technique, ambiguous notation and arbitrary mathematics are outside the verified scope. Trigonometric arguments use radians. Real logarithms, roots and original denominators have domain restrictions.

## Interpreting questions and offering study modes

**Problem:** calculation tools can correctly solve a badly translated word problem.

**Files:** `app/services/study_assistant.py`, `app/routers/study.py`, `documind-web/components/study-desk.tsx`.

The model uses an operation-specific schema rather than a single object containing every calculator field. For example:

```python
class EquationPlan(ToolPlan):
    operation: Literal['solve']
    equations: list[str] = Field(min_length=1, max_length=4)
    variables: list[str] = Field(min_length=1, max_length=4)
    domain: Literal['real', 'complex'] = 'real'
```

Calculus, expression operations, units and matrices have their own schemas. Extra fields are rejected. `ProblemPlan.calculator()` normalizes the chosen plan to a `MathRequest`; it never accepts invented student working from the model. The JSON schema is supplied to Ollama and included in the prompt. The same 8,192-token context and warm-model controls are retained.

Default behavior is an input-review checkpoint:

```python
if interpretation.math and not interpretation.missing and not request.approve_calculation:
    yield event('done', metrics={'awaiting_interpretation': True, ...})
    return
```

The UI renders the interpreted equations, units or matrix, and lets the user calculate those inputs or edit them. If the question changes, the old approval button is disabled. The explicit calculator requires no model round trip. Diagnostic benchmarks explicitly opt into automatic calculation so they can measure interpretation errors; that is not the UI default.

Questions explicitly saying data is not supplied receive a clarification instead of an invented numeric value. Symbolic/general-formula requests are exempt from that narrow guard. General missing-data detection still depends on interpretation. The first unseen test set exposed wrong word-problem translations in both tested models, which is why review is a product behavior rather than a hidden warning.

Answer and explanation modes show calculated results/checks. Hint and quiz modes withhold calculator results. Notes explanations, document comparisons and generated practice use bounded model output, page citations and quote checks. Student-working/rubric review is a model review: any proposed marks remain provisional. Actual equivalent-expression/solution-set checking belongs to the calculator.

**Tradeoff:** local automatic interpretation currently uses Ollama. Hosted compatible providers remain available in PDF conversations; direct calculator tools do not need a model or API key. A more capable model may improve interpretation, but no model is certified as a universal exam solver.

## Finding better evidence and following a problem

**Files:** `app/services/advanced_retrieval.py`, `retrieval_context.py`, `pdf_processor.py`, `vector_db.py`.

The existing dense + BM25 hybrid search remains. Thorough study search adds up to three subqueries, up to 36 candidate pages, a small CPU cross-encoder reranker, per-document coverage, and selected neighboring pages. The final answering prompt is still budgeted to fit 8,192 tokens. Raw search/reranking scores are not confidence probabilities.

```python
groups = await asyncio.gather(
    *(search_page_sources(pdf_ids, query, per_document=6) for query in queries)
)
```

The reranker is loaded lazily and cached. If unavailable, telemetry explicitly says hybrid ranking was retained. This adds relevance checking, not a guarantee of better results on every document. Indexing now tries to keep paragraphs, question starts, definitions, theorems and examples together instead of always cutting at a character offset. Very long blocks retain bounded fallback splitting.

The last submitted user problem and explicit calculator input/result are stored as active problem context. They help requests such as “differentiate that expression.” Earlier generated assistant claims are not treated as primary PDF evidence. Ambiguous references can still need clarification.

**Try:** use a compound question spanning the algebra and units pages of the synthetic notes, then inspect search-query count, reranker status and actual source pages. Reindex an existing document to use the new chunk boundaries.

## Complete reviews and consolidated findings

**Files:** `app/services/complete_review.py`, `synthesis.py`, `app/routers/summarizer.py`.

Complete review still visits every readable segment and caches completed results. Consolidate findings now consumes that complete review and reduces its notes in bounded groups instead of sampling a few pages for the final overview. Source markers travel through the reduction. Empty, truncated and invalid-citation reductions fail explicitly; retry can reuse completed page reviews.

```python
async for line in review_events(review, records, event):
    value = json.loads(line)
    if value['type'] == 'text':
        notes.append(value['content'])
```

The interface shows real review/reduction progress. At most 600 initial segments and ten reduction levels are allowed. A reduction that does not shrink fails rather than looping indefinitely.

**Tradeoff:** a summary necessarily compresses details. Processing all readable segments does not prove every fact was understood, every contradiction resolved, or every final paraphrase supported. Citation IDs and explicit quotes are checkable; full semantic entailment and arbitrary proofs remain unverified.

## Papers, practice, marking and revision

**Files:** `study_assistant.py:paper_questions`, `app/routers/study.py:checked_practice`, `study_store.py:review_item`, `components/study-desk.tsx`.

The paper navigator detects numbered questions, subparts, marks and page links from saved text. Questions remain editable because detection is heuristic. Attempted/checked states are durable study items; the user can reopen a selected question in the solver and attach a supplied rubric.

Generated calculator practice stores the original structured inputs beside its checked answer. `generatedPracticePrompt` typesets those known inputs in the review queue. It only applies to recognized generated exercises; arbitrary saved question wording remains intact. Long paper previews wrap and use a three-line bound; selecting the question exposes the editable full text.

Generated calculator practice supports linear/quadratic equations and polynomial derivatives/integrals. Each exercise is calculated and checked before being saved, with its answer kept behind Reveal saved answer. These are generated exercises, not claims about a PDF's contents. Document-based model practice has a suggested key requiring review, not an invented official marking scheme.

Mistakes, formulas and practice items enter a due queue. A miss schedules tomorrow; a correct recall doubles the previous interval, up to 90 days. These are actual user outcomes, not inferred mastery percentages:

```python
interval = min(90, max(1, previous_interval * 2)) if correct else 1
```

The library supports search, formula/LaTeX notes, mistakes, attempts, topics, bookmarks and linked annotations. Saved items can be reopened, exported and removed. Review dates use UTC timestamps and the browser's current time.

**Tradeoff:** this is a simple, explainable scheduler, not an adaptive learning model or an official exam grader. Question recognition and generated non-calculator keys need human review.

## PDF inspection, images and diagrams

**Files:** `components/pdf-page.tsx`, `app/routers/document_viewer.py`, `PDFProcessorService.page_geometry`, `app/routers/study.py`.

Native PDF word boxes and search rectangles are normalized to page dimensions. The original rendered page remains the visual truth; selectable text and highlights are overlaid. A separate extracted-text view supports copying and reading. Source cards can save a page bookmark or an annotation tied to the PDF ID/page. Saved linked notes open the original PDF.

Scans may have no native word boxes; the viewer says so rather than inventing coordinates. The existing OCR excerpt is still available. Image uploads accept PNG/JPEG up to 8 MB and 16 megapixels. Tesseract transcription uses the bounded document process executor and a 30-second OCR timeout. Vision transcription checks that the chosen local model actually supports images, then requests question/equation/diagram-label transcription rather than a claimed verified solution.

Both outputs are editable before submitting a problem. A vision reader is chosen separately from the main text model. The installed `qwen3-vl:2b-instruct` reader correctly transcribed both dimensions in our public rectangle fixture. Tesseract returned text but missed a dimension label in that fixture. These are narrow checks; arbitrary handwriting and diagram interpretation are not guaranteed correct.

An optional Docling adapter preserves per-page exports and enables table/formula enrichment. It is **not installed in the standard image** and has not been claimed as the superior parser. `requirements-docling.txt` and `evaluation/compare_extraction.py --docling` provide a separate installation/comparison path. Standard extraction remains available. This avoids silently replacing the fast parser with a heavier unmeasured pipeline.

## Durable work and recovery

**Files:** `app/models.py`, `study_store.py`, `job_journal.py`, `jobs.py`, `app/routers/study_state.py`, `lib/persistence.ts`.

Workspaces and study items are now saved in SQLite. Existing browser-only workspaces merge with server workspaces; different content under the same ID is preserved as a separate browser copy. Deleted workspace IDs are remembered so an older tab cannot recreate them. A browser copy remains a fallback. Server saves carry a revision number; a stale tab receives 409 instead of overwriting another tab. Workspace data has shape/size validation and rejects credential fields. Main-chat saves use a bounded interval while tokens stream, rather than waiting indefinitely for a quiet gap.

Browser storage belongs to an exact origin. History under the former port 3100 cannot be read automatically from port 4317. Its storage and classic app files remain intact; export/import moves those workspaces to the current origin.

```python
UPDATE workspaces
SET payload = ..., revision = revision + 1
WHERE id = ... AND revision = ...
```

Jobs checkpoint output events approximately once a second and at completion. Browser reload can reconnect to its job. A backend restart marks interrupted jobs failed with an explicit retry message; it does not falsely resume an in-flight GPU computation. Cached complete-review segments survive. Journals retain up to 100 terminal jobs and prune old records; in-memory tasks remain bounded and single-process.

Workspace JSON backups include study items, but reference PDF IDs in the same local library. The database backup uses SQLite's online backup API. It contains database records/text, not the original PDF files. No automatic destructive restore is offered; keep the PDFs and restore a database only with the app stopped and a separate safety copy.

**Tradeoff:** browser reconnect markers require browser session storage. Storage errors are surfaced, and completed work can still be saved on the server. This is not a distributed multi-worker queue or an institutional identity/permission system.

## Document lifecycle and local operation

Uploads now hash PDF bytes. Re-uploading a ready document can reuse its document ID and index; duplicate files within one batch are rejected. Display names can be changed, existing local PDFs reused in another workspace, and documents reindexed. Removing a document from a workspace preserves the original for other workspaces and historical citations. Original files are not silently deleted.

Saved answer metadata records a hash of extracted document text. The study library flags evidence whose extracted version changed. Legacy answers without version metadata cannot be certified retroactively.

Review caching is capped at 2,000 entries with deterministic eviction, and the library exposes cache size/trim/clear controls. It is not an LRU policy. Clearing review cache retains PDFs and saved answers.

The normal stack remains Docker + Qdrant + Ollama + Next. `run_local.py` also offers a Docker-free backend using the canonical SQLite/PDF library and a **separate** embedded Qdrant index. Selected saved page text can rebuild that index. It never opens Docker's incompatible search storage directly. The normal Docker stack is running at handoff; the fallback was used while Docker was unavailable.

## Verification and model comparison

Run from `pdf-summarizer-backend`:

```powershell
.\venv_win\Scripts\python.exe -m pytest -q --cov=app --cov-report=term --cov-fail-under=80
.\venv_win\Scripts\python.exe evaluation/run_math_quality.py --output ../output/math-quality.json
.\venv_win\Scripts\python.exe evaluation/run_problem_quality.py --models llama3.2:3b qwen2.5-coder:7b --output ../output/problem-quality.json
```

The fixed-answer calculator benchmark contains 50 cases including invalid-input rejection. Real-model regressions test operation translation and tool results. A separate first unseen set was evaluated and retained as `output/problem-holdout.json`; it exposed word-problem interpretation errors. It is now a consumed test set, not an endlessly retuned “unseen accuracy” claim. Reports include actual timing and Ollama metrics where available. Infrastructure failures are not reported as model accuracy. Missing-data validation may handle some pipeline cases without a model call.

Run from `documind-web`:

```powershell
npm run test:coverage
npm run typecheck
npm run build
npm run test:e2e
```

The tests cover calculator operations, restricted syntax, process timeouts, schema interpretation, source retrieval, reductions, cache behavior, workspace revisions, secret rejection, backups, PDF geometry, paper parsing, review scheduling, UI workflows, math rendering, mobile navigation and streaming. Mocked UI boundaries and real local-model checks are separate kinds of evidence. See the final verification record for counts, failures/limits and browser results.
