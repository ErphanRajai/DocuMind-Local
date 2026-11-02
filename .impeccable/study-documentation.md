# Study desk implementation supplement

## Overview

This is an ordinary extension of DocuMind's **Field-observation notes** system. `DESIGN.md` and `.impeccable/design.json` remain the incumbent authority and were retained without edits. The study brief supplies the surface contract; no Figma frame or approved external composition was supplied. This supplement records implemented study patterns rather than replacing the visual system or introducing another token source.

The study desk extends reading and checking into an inspectable sequence: question, interpreted inputs, calculation, listed checks, source excerpt, and saved recall. A calculation verifies its supplied inputs; the interface explicitly asks the reader to check whether those inputs represent the question. Model explanations, calculator output, and retrieved evidence retain separate labels.

Observed basis: `PRODUCT.md`, `DESIGN.md`, `.impeccable/design.json`, `.impeccable/study-brief.md`; the six requested implementation files (`components/study-desk.tsx`, `app/study.css`, `components/answer.tsx`, `components/pdf-page.tsx`, `lib/study.ts`, `app/layout.tsx` under `documind-web`); supporting `app/tokens.css`, relevant `app/globals.css` rules, `package.json`, and installed KaTeX stylesheet/font assets. Existing replacement captures inspected: `study-user-1280.png`, `study-mobile.png`, `study-mobile-result.png`, `study-paper-mobile.png`, and `study-review.png` in `.impeccable/review/`.

The parent reported the independent finish review's disposition as **ship** for the three scored corrections (primary action visibility, paper wrapping, and practice math), with no material fix-induced regression visible. This documentation pass ran no browser, build, test suite, or detector. It does not establish universal OCR, optional vision-model, or Docling verification.

## Colors

The extension uses the incumbent CSS properties without adding a palette. White `paper` holds input and calculated work; mineral `canvas` holds the result region; quiet `panel` holds the calculator, checks, and question previews. `ink` and `muted` retain primary and supporting text roles. `accent` and `accent-soft` mark the selected study tool, citations, evidence, and notices. `control`, `line`, `danger`, and `danger-bg` retain field, seam, and failure roles.

Primary study actions reuse the dark primary button. Their disabled state uses the active/muted pair at full opacity within the study surface. Selection and check messages also retain textual labels.

## Typography

Instrument Sans remains the UI and prose family, served through the existing local font imports at weights 400, 500, and 600. Answers retain the shared reading measure (70ch). Study solutions use reading text (16px) with line-height (1.8); the study title is (32px), reducing to (28px) on phones, and study section headings are (22px).

KaTeX is functional mathematical typesetting, not a decorative display family. `layout.tsx` imports `katex/dist/katex.min.css`; the installed package includes its referenced local WOFF2, WOFF, and TTF assets, including Main, Math, AMS, and size families. `Answer` combines Markdown, math parsing, and KaTeX HTML plus MathML, with trusted commands disabled and bounded expansion/size options. Display equations scroll horizontally inside their region when required. Obvious currency amounts are escaped before inline-math parsing while code and display equations are preserved.

Generated calculator practice is typeset from its saved structured input through the same renderer, with a short operation heading such as “Solve.” This path is limited to practice items carrying the exact generated-exercise origin and a supported solve/differentiate/integrate input. Other saved questions and extracted paper previews remain their stored text.

## Layout

The study surface has its own horizontal header, workspace selector, and four-tool navigation. It does not replace the conversation workspace's rail or phone pane switch. Desktop input/result columns use a (0.9:1.1) ratio; the input minimum is (320px), and the result column can shrink without imposing a content-width minimum. Above (700px), the result region is sticky at the top, bounded to the viewport height, and independently scrollable. At (1600px), the study grid and title/navigation are capped at (1500px).

At widths up to (1000px), padding tightens and columns become equal with a (290px) input minimum. At widths up to (700px), input precedes output in a single document flow; collections use the same phone padding (24px 20px). At widths up to (420px), all four tool labels form two rows of two buttons with minimum height (40px), as visible in the phone capture.

For desktop widths above (1000px) and height up to (800px), title, navigation, alert, and section spacing tighten. The main question action precedes model and advanced-working controls; it is visible in the inspected (1280 × 720) capture. The calculator remains further down the input flow. When a calculation appears or answer text first arrives, the result heading scrolls into view immediately and receives programmatic focus. Phone result captures therefore begin at the working-space heading rather than requiring a manual search through the input form.

## Elevation & Depth

The extension retains flat tonal separation and adds no shadows. The result sheet is white within the mineral canvas; the calculator and checks use quiet panel fill. Existing button feedback and reduced-motion rules are inherited. Result navigation uses immediate scrolling rather than staged motion.

## Shapes

The incumbent control radius (8px), panel radius (20px), and thin rule (1px) recur in fields, previews, calculator, result sheet, and notices. The extension does not round or replace original PDF imagery. Shared control spacing and semantic surface tokens remain reusable; study-specific padding and type sizes are recorded here without promoting them into global tokens.

## Components

- **Question and calculator forms:** visible labels, editable text, operation/domain controls, and optional working are followed by explicit actions. Extra rubric and working fields are disclosed in place. Equation input and rendered preview remain separate representations.
- **Interpretation review:** model-derived math inputs appear for confirmation before calculation. Editing the question disables approval until it is resubmitted. The result sheet repeats the inputs actually used and limits “passed” language to listed calculation checks.
- **Sources:** study citations open an extracted excerpt with filename/page, a link to the original PDF, bookmarking, and linked annotation. The excerpt is bounded (260px) and scrollable. The shared PDF page component retains the original page image, coordinate-based highlights and selectable text layer, page search, and disclosed extracted text. Those extracted representations do not certify the image or generated explanation.
- **Paper questions:** source text remains plain and editable. List previews stop at (240 characters), use a three-line clamp, wrap within the button, and preserve page, detected marks, status, and selected fill. Selecting a row puts its full stored text into the selected-question textarea; the original paper remains linked. Detection is explicitly heuristic.
- **Review and library:** flat rows use shared seams rather than raised cards. Answers are disclosed after attempting; recall actions are “Needs another look” and “Recalled correctly.” The due-count comes from saved due items. Library rows retain item kind, saved work, source links, and stale-extraction notices. Formula math and generated practice reuse `Answer` rather than displaying raw calculator syntax as the mathematical prompt.
- **Progress and failure:** phase text has status semantics, errors use an alert, and work can be stopped. Failed/stopped draft phases remain explicit. Timing and verification details stay disclosed rather than becoming confidence metrics.

## Do's and Don'ts

- Do retain the incumbent tokens, local prose fonts, flat surfaces, and established control feedback when extending study tools.
- Do keep calculation inputs, listed tool checks, generated explanations, and source evidence distinguishable in labels and layout.
- Do preserve bounded previews, full editable question text, original-page links, and the result-focus behavior.
- Don't treat a successful tool check or a citation as certification of the original word problem or every generated sentence.
- Don't generalize the study shell's breakpoints or result-sheet container into a replacement for the conversation workspace.

Preserved drift: the incumbent design files continue to document the conversation shell, so their rail, breakpoints, and component snippets do not enumerate the study surface; this scoped supplement records the extension. In the phone capture, “PDF conversations” remains visible even though `.study-back` declares hiding below (1000px): the more-specific `.study-header a` display rule wins. That existing selector behavior was observed and left untouched. No unrelated application, backend, fallback-interface, or documentation changes were repaired in this pass.
