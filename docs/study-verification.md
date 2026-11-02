# Study upgrade verification — 1 November 2026

## Running configuration

Next production UI: http://127.0.0.1:4317/. Study desk: `/study?workspace=study-demo-3c99a876`. FastAPI Docker backend: `127.0.0.1:8888`; Qdrant: `127.0.0.1:6333`; project Ollama: `127.0.0.1:21434`. Backend health reports healthy, Qdrant connected and Ollama connected. Main text default remains `llama3.2:3b`. `qwen3-vl:2b-instruct` is installed for separately selected image transcription. No main-model switch was inferred from small benchmarks.

## Automated checks

| Check | Actual result | Scope |
| --- | --- | --- |
| Backend pytest + coverage | 197 passed; 85.26% application line coverage | Validation, calculation, process bounds, retrieval, persistence, jobs, API and failure paths |
| Frontend Vitest + coverage | 55 passed; 85.71% statements, 74.15% branches, 79.33% functions, 87.11% lines | Math rendering, generated practice notation, workspaces, browser/server merge, Study and conversation controls |
| Production Next build | Passed, including TypeScript | `/`, `/study`, streaming API proxy |
| Edge Playwright | 6 passed | Upload/answer/source, persistence, mobile overflow, keyboard source focus, settings, calculator, interpretation review |
| Fixed-answer mathematical tool evaluation | 50/50 | Known symbolic answers and invalid-input rejection; not language-model accuracy |
| Real document-answer evaluation | 6/6 with llama3.2:3b | Fixture facts, follow-up, missing evidence, conflict, quotations and document instructions |
| Real problem regression cases | 8/8 with each of llama3.2:3b and qwen2.5-coder:7b | Small known pipeline regression set; validation can handle missing-data cases without calling a model |
| First unseen word-problem set | llama3.2:3b 8/9; qwen2.5-coder:7b 7/9 | Both misinterpreted the rectangle case. This set is now consumed; scores are retained without relabeling it unseen |
| Dependency audit | Zero npm vulnerabilities after KaTeX override | Snapshot of installed dependency audit, not a security certification |
| Whitespace/diff check | Passed | `git -c core.safecrlf=false diff --check` |

Backend checks emit one upstream Starlette TestClient/httpx deprecation warning. Browser checks emit environment color warnings; neither is a test failure. Production type checking is part of the build.

## Real running-service checks

`evaluation/verify_study_live.py` used the public synthetic three-page PDF and rectangle diagram, not private documents. It verified native PDF word geometry and a search highlight; four detected paper questions with marks; actual cross-encoder reranking and three retrieval queries; cited study notes; complete synthesis covering all three readable pages; cancellation after first answer text; and the default review checkpoint before calculating AI-interpreted inputs.

Tesseract returned editable text but missed a dimension label. The separately selected qwen3-vl reader transcribed both 10 m and 5 m correctly. This single fixture does not establish arbitrary OCR, handwriting or diagram accuracy. Generated transcriptions remain editable and unverified.

Reports are local ignored artifacts in `output/`: `study-live.json`, `math-quality.json`, `problem-quality.json`, `problem-holdout.json`, `quality.json`, `study-backend-coverage.json`, and `study-demo.json`. Evaluation scripts are retained under `pdf-summarizer-backend/evaluation/`.

## Browser and design evidence

Actual result captures in `.impeccable/review/`: `study-desktop.png` (1440 × 900), `study-user-1280.png` (1280 × 720), `study-tablet.png` (768 × 1024), `study-mobile.png` and `study-mobile-result.png` (390 × 844), plus paper, review and library states. The captures were opened and reviewed; measured horizontal overflow is zero at these widths. The displayed result is an actual calculated quadratic with substitution checks and real retrieved PDF references.

The bounded two-pass self-inspection is recorded in `.taste-skill/study-critique.md`. The final inspector permits only `headline-lines`, because the detector mistakes stacked fractions for multi-line headings. Its three warnings concern mathematical italics, hidden MathML's generic `math` font and a reserved empty-state area. Visible bundled KaTeX fonts passed browser loading checks. A single Impeccable detector run returned no findings. Independent finish review and design documentation are recorded separately in `.impeccable/`.

The independent reviewer initially requested three fixes: primary-action visibility at 720px height, wrapping exam previews, and typesetting generated practice. After one correction batch and replacement captures, it scored all three resolved with **disposition: ship** at that correction-list scope. Final frontend tests/build/browser checks were rerun after the batch. The design documenter preserves the incumbent system and records this ordinary extension separately.

## Deliberate limits

- A calculation checks its supplied inputs; it does not prove that a model understood a word problem. Review AI-derived inputs before calculation. General proof checking is unavailable.
- Formula/table extraction through Docling is optional, not installed in the standard image, and unbenchmarked here. Missing optional support returns an availability error before reindexing.
- Generated rubric feedback is provisional. Practice generation covers supported algebra/calculus families, not arbitrary exam subjects or independently validated marking schemes.
- Native PDF text selection/highlighting depends on native word boxes. Scans may have no boxes; no fabricated coordinates are shown.
- Local SQLite revision checks and job journaling are not a distributed job queue or institutional identity/permissions. A backend restart fails interrupted computations for explicit retry; it does not resume GPU computation.
- Database backups exclude original PDFs; retain those separately. Workspace imports reference the local PDF library. Port-3100 browser history requires export/import to the current port.

## Reproduce

From `pdf-summarizer-backend`, run `venv_win\Scripts\python.exe -m pytest -q --cov=app --cov-fail-under=80` and the evaluation commands in `docs/study-and-solve.md`. From `documind-web`, run `npm run test:coverage`, `npm run build`, then `npm run test:e2e` against the production server on 4317. The seed script creates a separate public demo; existing PDF data is preserved.
