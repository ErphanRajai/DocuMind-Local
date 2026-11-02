# Exam reliability extension supplement

## Overview

This is an ordinary Operate hardening extension of DocuMind's **Field-observation notes** system. `DESIGN.md` and `.impeccable/design.json` remain the authority and are preserved. No approved external composition, qualitycard, replacement identity, or new token system was supplied or required.

The primary path remains source PDFs → separate question paper → direct, source-linked answers in the paper language. Review, recovery, feedback, backup, and export support that path. Worked explanations remain an explicit alternative to the default direct-answer format.

Evidence checked: `PRODUCT.md`, `DESIGN.md`, the sidecar, `.impeccable/exam-reliability-brief.md`, the earlier study and multilingual supplements, and the requested `exam-runner`, `exam-review`, `answer-feedback`, `workspace-transfer`, `answer`, and `study-desk` components, print route, study stylesheet, and export helper under `documind-web`. Shared tokens, local font imports, and relevant archive/checkpoint service code were also read. The design files and `app/tokens.css` have no current diff.

All nine supplied `exam-*.png` captures in `.impeccable/review/` were inspected: desktop, full desktop, question review, print, tablet, the 1280px user viewport, phone setup, full phone, and phone answers. They use a public synthetic Persian paper and 120-page source. The refreshed full desktop, full phone, tablet, and question-review captures show the new reference guidance. The invalid-question and excessive-reference remedies were checked in current code; the supplied normal-run captures do not exercise those blocked states. This documentation pass ran no browser, service, build, test suite, or detector; the independent finish review and execution checks are separate evidence.

## Colors

No palette was added. White paper holds inputs and the original page, mineral canvas holds the answer region, and evidence teal with its wash carries links, citations, and selected controls. Fields and answer rows retain the shared control edges and quiet seams. The primary run action retains the dark ink treatment; blocked-run messages use the incumbent error color and explicit text.

The captures retain flat answer rows rather than introducing raised cards, gradients, ornamental scores, or a new accent family.

## Typography

Instrument Sans remains the primary interface family with locally bundled Vazirmatn serving Persian script. Existing KaTeX typesetting remains functional mathematical notation. Exam answers retain reading text (16px), line-height (1.9), and the shared reading measure. The modest headings, native field labels, and disclosure summaries fit the incumbent study hierarchy.

Question and answer prose use automatic direction. Equations and source/page chips remain isolated left-to-right. The added identifier transform wraps matching uppercase hyphenated or underscored identifiers as code; inline code is isolated left-to-right and can scroll within its own width. The Persian sample visibly preserves `REF-…` identifiers and page chips inside RTL prose. This is answer-language support; the main application controls remain English.

## Layout

The existing horizontal study header and four-tool navigation remain. Desktop keeps setup on white beside the mineral result column; the existing sticky, independently scrollable result region remains above (700px). Phone layout places setup before answers in one column, with two-by-two navigation below (420px). The full phone capture shows the complete setup, run summary, recovery disclosure, and all four answer states without visible horizontal page overflow.

Question correction adds a two-column editor/original-page comparison inside the existing disclosure. Its full text remains editable; the image keeps its original aspect ratio and has a full-size link. The comparison stacks below (600px). At the 1280 × 720 viewport, the final run action remains below the first viewport because the exam setup continues down the page; the full desktop capture establishes its place in the flow. **View answers** scrolls to and focuses the result heading.

The print route uses a bounded reading page (900px), ordinary document flow, and a compact controls row. Print media removes controls, allows long articles to break across pages, and uses page margins (18mm). The supplied print capture establishes the rendered Persian content and source lists; it is not a paginated PDF verification.

## Elevation & Depth

The extension adds no shadows or staged motion. White and mineral surfaces, selected washes, borders, and disclosure spacing retain the incumbent tonal hierarchy. Shared focus, press, and reduced-motion rules remain in force; this pass read their implementation rather than exercising keyboard or assistive-technology behavior.

## Shapes

Inputs and buttons reuse the established control corners (8px) and thin rules (1px). Review, checks, recovery, and feedback use native disclosures within the form, not a new container silhouette. Original-page imagery remains proportional and uncropped. Citation chips retain their compact evidence treatment.

## Components

- **References and answer format:** the exam document is excluded from evidence choices. Guidance states the 1–3 PDF bound and current selection count; the first three eligible references are initially selected. More than three selections shows an explicit instruction to uncheck a reference and disables the run action. Direct answers are selected initially; worked explanation is optional.
- **Question correction:** users can inspect the full extracted text beside its original page, edit question number and page, add subquestions, or remove a question. Text beyond 8,000 characters is retained and blocks the run until split. The current code surfaces the first invalid question outside the collapsed editor, explains the reason, and provides an action that opens the disclosure, selects that question, and focuses its textarea. Empty text, invalid numbers/pages, no questions, and more than 100 questions also have explicit guidance.
- **Results and checks:** each answer retains its question, textual state, sources, and applicable interpreted calculator inputs. Calculation checks and assumptions are disclosed separately. The sample includes answers linked to pages 119 and 66, a typeset quadratic result, and a fourth answer labeled **More information needed**. Retrieved pages without inline citations are explicitly labeled for review. Neither a citation nor a passed check is presented as verification of every generated sentence.
- **Recovery:** saved runs are listed for the selected paper with state and completed-response count. Resume loads the stored request; the interface explains reuse of completed responses and retry of failed questions. Stop messages distinguish retained completed answers from interrupted work. These branches were read in code rather than re-executed by this documentation pass.
- **Local feedback:** each persisted answer offers an issue selector and correction note, a local save action, and status text for success or failure. Success states that the original answer is retained. Feedback controls are unavailable during relevant work.
- **Workspace transfer:** the separate complete-ZIP controls identify the archive as containing original PDFs and saved answers. Restore exposes validating/restoring status and errors, then opens the restored workspace. Supporting service code includes page text, study data, and exam checkpoints and creates new IDs rather than overwriting existing work; this pass did not perform an archive round trip.
- **Print and export:** the saved run supplies the print view. Persian headings/status labels and RTL direction are supported; other languages retain the English interface labels. Print and Markdown both retain question/answer text and source/page lists. The shared export helper recognizes Latin, Persian, and Arabic citation digits, excludes code spans, and distinguishes cited pages from retrieved-only pages. Original local PDF links remain available from citations.

## Do's and Don'ts

- Do retain incumbent tokens, local fonts, flat surfaces, and the visible separation of question paper and reference evidence.
- Do preserve full editable text, explicit blocked-state remedies, textual answer states, and inspectable calculation inputs.
- Do treat the synthetic 120-page example as bounded evidence of the demonstrated workflow, not universal OCR, translation, retrieval, or answer correctness.
- Don't promote this surface's geometry or export format into a replacement global visual system.
- Don't equate resumed, answer-ready, source-linked, or calculator-checked output with independently verified answers.

Preserved pre-existing drift: `DESIGN.md` and the sidecar primarily describe the conversation shell; they do not enumerate the study shell, its breakpoints, or the already-added Vazirmatn fallback. The earlier supplements record that scope. The phone capture still shows **PDF conversations** because the existing `.study-header a` rule overrides the narrower `.study-back` hiding intent. Neither issue was repaired here.

Scoped implementation note: the new print article seam currently references `var(--line)`, while the established token is `--color-line`; that border declaration therefore lacks the intended token binding. This documentation pass records the discrepancy without changing application code. No unrelated application or design-system file was changed or certified.
