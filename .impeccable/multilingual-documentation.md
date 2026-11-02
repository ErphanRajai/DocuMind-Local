# Multilingual study extension supplement

## Overview

This is an ordinary Operate extension of DocuMind's **Field-observation notes** system. `DESIGN.md` and `.impeccable/design.json` remain the design authority; this pass preserves both files. The multilingual brief and the existing study supplement describe this surface. There is no supplied Figma frame, approved external composition, or replacement identity.

The extension makes the study-reference → separate question-paper → per-question answer sequence explicit. It retains English interface labels while allowing requested answers to match the question or use a selected language. Persian prose and mathematical notation share the same evidence workflow; the script fallback and math fonts serve reading rather than a new visual direction.

Evidence checked: `PRODUCT.md`, `DESIGN.md`, `.impeccable/design.json`, `.impeccable/multilingual-brief.md`, the existing study brief/documentation/finish review, `components/exam-runner.tsx`, `components/study-desk.tsx`, `components/answer.tsx`, `components/language-select.tsx`, `app/study.css`, and `app/layout.tsx` under `documind-web`. Supporting token and shared component rules were read in `app/tokens.css` and `app/globals.css`.

All nine final `multilingual*.png` captures in `.impeccable/review/` were inspected: desktop, full desktop, math, missing information, tablet, the 1280px user viewport, and three phone states. After the missing-information status correction, the overwritten missing-information, full-desktop, and math captures were reopened for this documentation recheck. The correction preserves the identity and layout. Earlier `multilingual-round1-*` images are superseded and are not the basis of this supplement. This documentation pass ran no service, browser, build, test suite, or detector. It records the supplied build and captures; the independent finish review is separate.

## Colors

The implementation adds no palette. White paper holds study inputs; the mineral canvas holds exam answers. Quiet panel, reading ink, muted supporting text, control edges, and thin seams retain their established roles. Evidence teal and its wash mark the selected tool, source chips, links, and notices. The primary exam action reuses the dark primary button. Alerts retain the incumbent error color.

In the final desktop and phone images, question answers remain directly on the mineral surface, separated by rules. They do not gain raised cards, gradients, ornamental scores, or a new navigation accent.

## Typography

Instrument Sans remains first in the interface and answer stacks. `layout.tsx` imports its existing local weights (400, 500, 600) and adds the same weights of locally bundled Vazirmatn. Vazirmatn is a functional Persian-script fallback; it does not replace the Latin type system. Shared body/display token families now include that fallback, and the answer rule states the same order explicitly.

The existing study hierarchy remains: modest study title and section headings, shared interface labels, and answers bounded by the shared reading measure (70ch). Exam answers use reading text (16px) with line-height (1.9). The screenshots show Persian paragraphs, headings, and lists with the same quiet hierarchy as the incumbent study output.

`Answer` uses `dir="auto"` with plaintext bidi handling. Exam question paragraphs also use automatic direction. KaTeX equations and citation chips are isolated left-to-right so their notation and source/page identifiers remain ordered inside Persian prose. The interface shell remains left-to-right with `<html lang="en">`; this is answer-language support rather than full interface localization.

KaTeX remains functional mathematical typesetting with its local stylesheet. Markdown supports dollar delimiters and normalizes `\(...\)` / `\[...\]` delimiters outside code before rendering. Existing currency protection is retained. The renderer emits HTML plus MathML, disables trusted commands, and bounds expansion and size. Display equations have a bounded horizontally scrollable region; inline notation retains its isolated direction. The captured Persian quadratic result visibly renders the solution set and mathematical steps rather than exposing those answer equations as raw delimiter syntax.

## Layout

The existing study shell, workspace selector, four-tool navigation, and input/result topology remain. Desktop exam setup stays left of the mineral result region; the established sticky, independently scrollable result region applies above (700px). The complete desktop capture shows that a long result region remains bounded while the input column continues in document flow. Answer rows use seams and readable spacing.

The supplied capture sizes and visible states are:

| Capture | Size | Evidence visible |
| --- | --- | --- |
| `multilingual-desktop.png` | 1440 × 900 | Separate exam setup and Persian answer column, first two citations |
| `multilingual-full-desktop.png` | 1440 × 1305 | References, language choice, calculation approval, run summary, and answers |
| `multilingual-math.png` | 1440 × 900 | Persian calculation result, notation, checks, and source chip |
| `multilingual-missing.png` | 1440 × 900 | Unsupported laboratory-name question with “More information needed” heading and an explicit information gap |
| `multilingual-user-1280.png` | 1280 × 720 | Compact desktop spacing and the top of the same two-column workflow |
| `multilingual-tablet.png` | 768 × 1024 | Equal-width study columns with wrapping Persian questions |
| `multilingual-mobile.png` | 390 × 844 | Wrapped header, two-by-two navigation, and stacked exam setup |
| `multilingual-mobile-answers.png` | 390 × 844 | Stacked Persian answers and compact source chips |
| `multilingual-mobile-math.png` | 390 × 844 | Persian mathematical solution and lists within the phone result width |

At widths up to (700px), the existing column stack places input before results. Up to (420px), navigation uses two rows with (40px) minimum button height. Question preview rows retain their existing bounded, wrapped presentation; exam question paragraphs can wrap long content. The phone images show Persian prose wrapping inside the result width. Some inline equation expressions occupy more than one line in surrounding prose; these captures do not establish handling of every possible long expression or filename.

The explicit **View answers** action scrolls to the results heading and focuses it. Results stay separate from setup rather than being duplicated below the form. The captured (1280 × 720) exam setup continues below the viewport; unlike the earlier single-problem solve action, this capture does not establish first-viewport visibility of the final **Answer this paper** button.

## Elevation & Depth

Flat surfaces, tonal changes, and thin rules continue to provide depth. This extension introduces no shadows or staged motion. Existing control press/hover feedback, visible focus outlines, and reduced-motion rules remain in the shared stylesheet. Keyboard and assistive-technology behavior were read in code rather than exercised during this pass.

## Shapes

Inputs and actions reuse the established control corners and border vocabulary. Inline citations retain their compact shape and evidence pair; the result list uses separators. The extension adds no decorative imagery, alternate card silhouette, or treatment that changes the proportions of original PDFs.

## Components

- **Answer language:** a labeled native select offers “Match question / exam” and named languages, including Persian. It is reused by the solver and exam runner and disabled while their relevant work is busy. The screenshots show automatic matching selected; other choices are code evidence only.
- **Exam setup:** the question paper is selected or uploaded separately. Its document is excluded from the study-reference checklist. References, language, and optional automatic calculation appear before the run action. The interface states the (20) numbered-question bound and disables the run action without a paper or with zero or more than three selected references.
- **Calculation review:** automatic calculation requires a labeled checkbox acknowledging model-interpreted inputs and checks. It is unchecked initially. Each applicable answer discloses the interpreted inputs and can open them in the solver for review. The final sample shows automatic calculation enabled and the disclosure collapsed; the initial review-first state is established by code.
- **Per-question answers:** each row retains question number, textual state, question, answer, and its own sources. Code distinguishes input review, missing information, failure, and answer-ready headings. The corrected information-gap capture shows Question 4 labeled **More information needed**, consistent with its Persian body stating that the laboratory name is absent. The parent reports that typed grounded-answer status now propagates `needs_information` into the exam event; the status is not inferred separately from the prose.
- **Sources:** the shared citation renderer recognizes known source IDs with Latin, Persian, or Arabic digits and normalizes them to the supplied source list. It keeps compact LTR source/page chips within RTL prose. In exam answers, the implementation requests the original document at its page in a separate tab through `window.open`. The parent reports that a spy confirmed the correct local file/page URL and that the PDF response was (200); the harness did not confirm a new-popup event. This differs from the solver's in-page extracted-source inspection and does not replace it.
- **Progress and persistence:** the runner exposes real phase text through status semantics and errors through alerts. Stop controls are present while busy, and messages distinguish saved completed questions from interrupted work. The corrected full-desktop and math captures show **4 questions processed · 0 failed · 1 need review or more information**, consistent with the missing-information row. Cancellation, failure, reconnection, and saved-library revisits were not visually re-exercised here.

## Do's and Don'ts

- Do retain incumbent semantic tokens, Instrument Sans as the primary UI family, locally served script fallback, and flat surfaces.
- Do retain automatic prose direction and isolate equations and source identifiers within it.
- Do keep exam text separate from reference evidence and keep interpreted calculator inputs inspectable.
- Do describe the Persian sample as a bounded observed workflow; these images do not establish universal translation, OCR, model correctness, or mathematical interpretation accuracy.
- Don't equate an answer-ready heading, successful calculation check, or source chip with independent verification of every generated sentence.
- Don't promote this study surface's geometry, script fallback, or native language options into a new identity or a replacement conversation shell.

Preserved pre-existing drift: the incumbent `DESIGN.md` and sidecar primarily describe the conversation shell; their rail, pane-switch breakpoints, and snippets do not enumerate the study shell already recorded in `.impeccable/study-documentation.md`. That supplement also records a selector-specific mismatch: “PDF conversations” remains visible on phones because `.study-header a` wins over the `.study-back` hiding rule. The final phone capture still shows it. Neither issue is repaired or redefined by this documentation pass. No installer behavior, backend correctness, unrelated application surface, or design-system file was changed or certified here.
