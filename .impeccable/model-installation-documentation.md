# Model installation: documentation handoff

Recorded 2026-11-03. Scope: an ordinary, narrow **Operate** extension to the existing conversation settings and exam desk. The direction contract is `.impeccable/model-installation-brief.md`. This work extends the incumbent “Field-observation notes” system; it does not establish a new visual world or an approved change to the durable design system.

## Evidence checked

Compared `PRODUCT.md`, the token-bearing `DESIGN.md`, and `.impeccable/design.json` with:

- `documind-web/components/model-library.tsx`: shared form, selection behavior, review, installation and job states.
- `documind-web/app/page.tsx`: the local Ollama form inside the existing model preferences dialog.
- `documind-web/components/study-desk.tsx`: the same form inside the inline “Manage models” disclosure, disabled during answer/exam work.
- `documind-web/app/globals.css` and `documind-web/app/tokens.css`: applied field, action, status, focus, spacing and responsive treatments.

Opened all eleven supplied PNG captures. The screenshots show synthetic fixture states; their model-file sizes and free-space numbers are examples, not product or hardware claims.

| Captures in `.impeccable/review/` | Evidence |
| --- | --- |
| `model-desktop-review.png`, `model-desktop-confirm.png` | Settings form and its lower review/action region at 1440 × 900. |
| `model-1280-review.png`, `model-1280-confirm.png` | The same settings content and internal scrolling at 1280 × 720. |
| `model-mobile-review.png`, `model-mobile-confirm.png` | Form labels, destination and explicit install action at 390 × 844. Long content remains inside the dialog. |
| `model-relocation.png` | Existing-library copy size, destination, preservation message and restart requirement before installation. |
| `model-mobile-progress.png` | Current-file progress, byte counts, disabled editing, persistent status and cancellation action. |
| `model-mobile-failed.png` | Interrupted-download status and instructions to review again and resume. |
| `model-installer-unavailable.png` | Installer connection guidance/retry while the installed model remains available. |
| `model-study-manager.png` | Shared form and review embedded in the exam desk disclosure. |

The build handoff supplied the fresh finish review disposition **ship**, with all eleven captures valid and no material fixes requested. This document records the design comparison and state patterns; it does not replace that review or claim a new backend/console test run. Cancellation, verified completion, and restart-pending selection behavior below were checked in the component source; the supplied screenshots do not depict those completed states.

## Form patterns and states

| State | Implemented behavior |
| --- | --- |
| Installed model | Native select options identify installation status. Selecting an installed model updates the answer-model choice. A separate “Answer model” line makes the active choice visible. |
| Missing model | Selection changes the candidate and may request a size/folder review. It leaves the current answer model intact and does not start a weight download. Supporting text states this explicitly. |
| Review/checking | The review action names size and folder. Its checking label announces the work; relevant controls disable while the request is pending. Changing the candidate or destination clears an earlier preview. |
| Installation review | A flat section presents model files, maximum download, free space and destination. The copy size appears when changing libraries. File-size help distinguishes disk downloads from RAM/VRAM requirements. The dark primary action explicitly opens Command Prompt. |
| Changed folder | Help beside the editable destination explains copying, preserved originals and restart before confirmation. The review repeats the restart requirement before the installation action. |
| Starting/running | Opening status precedes job status. A native progress element shows determinate current-file progress when a total exists and indeterminate progress otherwise. The form keeps editing disabled, shows cancellation, and explains that settings can be reopened to inspect progress. |
| Failed/cancelled | Terminal job text remains visible. Retry requires a fresh review; the form explains that downloaded parts can resume. Request errors stay local with alert semantics. A failed cancellation confirmation gives an action in the installation window. |
| Completed | Completion refreshes installed-model information. “Use installed model” appears only when completion needs no restart and the refreshed installed list includes that model. Installation itself does not silently switch the active answer model. |
| Restart pending | The catalogue labels installed models that still require a DocuMind restart. A changed-folder job does not expose the immediate-use action. |
| Installer/Ollama unavailable | Installer connection status offers retry and retains the fallback installed list. An unavailable Ollama service explicitly makes installed status uncertain and asks for refresh. The form gives platform/launcher guidance where applicable. |

The same component serves both settings and the exam desk, keeping state vocabulary and controls consistent. Visible labels, associated destination help, live status, alert semantics and native controls retain the existing accessible interaction approach. Model identifiers and destinations use left-to-right text. Supporting text and destinations can wrap within their region.

## Relationship to the incumbent system

The extension uses existing paper, ink, muted, control-edge, quiet-seam and accent tokens. Inputs retain the white paper background, control border, control corners and established padding. Review and progress use thin horizontal rules and spacing rather than a new card treatment. The primary install action inherits the existing ink/paper button treatment; ordinary refresh, review and cancel actions retain quiet button styling. Native progress uses the existing teal accent. Shared focus outlines, disabled treatment, button feedback and reduced-motion handling remain in force.

The settings dialog retains its existing shell and bounded internal scroll. The exam desk uses an ordinary disclosure with a bounded form width. The local phone rule raises input/select text to 16px and reduces exam-desk side margins; it does not redefine the global responsive system. The inspected phone captures keep the review values and primary action within the form width.

`DESIGN.md` and `.impeccable/design.json` remain unchanged because the completed feature applies established primitives to a local workflow. It introduces no approved palette, type, elevation, motion or component-system change requiring regeneration. Task-specific review fields and installation states belong in this handoff rather than becoming global design rules.

An existing documentation mismatch was observed: `tokens.css` includes `Vazirmatn` in the body-font fallback stack, while the incumbent design prose/frontmatter describe Instrument Sans with a generic sans-serif fallback. This is recorded without repairing or refreshing the design files. No unrelated drift was audited or changed.

Write boundary for this handoff: `.impeccable/model-installation-documentation.md` only.
