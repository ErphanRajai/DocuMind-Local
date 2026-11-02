# Workbench verification — 2026-10-31

| Check | Actual result |
| --- | --- |
| Backend suite | 128 passed; 84.05% application line coverage; 80% coverage floor passed |
| Frontend unit/component/proxy suite | 32 passed; 84.29% statement, 78.81% branch, 81.20% function and 85.12% line coverage |
| Production build | `npm run build` passed, including TypeScript checking |
| Browser suite | 4 passed in Microsoft Edge against the production server |
| Real Ollama evaluation | 6/6 synthetic cases passed with `llama3.2:3b` |
| Live complete review | Both readable pages completed; repeat reused both cached segments |
| Live cancellation | Job returned `cancelled` |
| Services at handoff | New frontend HTTP 200 on 3100; backend reports Ollama/Qdrant healthy |
| Production layout inspector | 0 failures at 1440, 768, 390; one justified reserved-empty-viewer warning |
| Impeccable detector | Ran once on new UI sources; no findings |
| Fresh UI fix review | All three listed corrections resolved; scoped disposition `ship` |
| Design documentation | DESIGN.md and schemaVersion 2 sidecar checked against actual source tokens |

Tests cover extraction warnings, PDF pages, safe file access, upload rollback/cancellation, request bounds, prompt budgeting, provider stream errors, metrics, hybrid source metadata, follow-up context, review segmentation/caching/local-to-global source mapping, quote matching, job replay/cancellation, frontend persistence, fragmented UTF-8 streaming, proxy failures, React UI workflows, model settings and keyboard citation navigation.

The browser suite uses synthetic API responses for reproducibility. Separate manual browser/API checks use real local services and public synthetic PDFs. Model evaluation uses five synthetic pages and deterministic fact/page/quote checks; six passing cases are not a general factual accuracy estimate. Quote checking is not entailment checking. Complete reviews are page-by-page findings, not a final global synthesis. See `workbench-upgrade.md` for failure handling, storage and deployment limits.

Warnings: one existing Starlette/httpx TestClient deprecation warning in Python; Playwright prints a harmless terminal color-environment warning. No test failures remain.

Detailed generated reports are kept locally in `output/backend-coverage.json`, `output/quality.json`, `output/live-jobs.json`, and `documind-web/coverage/`. They are intentionally ignored by Git. Screenshot evidence is under `.impeccable/review/`.
