---
name: DocuMind
description: A quiet local workspace for reading, questioning, and checking PDFs.
colors:
  ground: "oklch(100% 0 0)"
  paper: "oklch(100% 0 0)"
  canvas: "oklch(96.5% 0.009 150)"
  panel: "oklch(97.8% 0.004 150)"
  active: "oklch(92% 0.017 150)"
  ink: "oklch(25% 0.025 160)"
  muted: "oklch(47% 0.016 160)"
  accent: "oklch(40% 0.075 165)"
  accent-soft: "oklch(92% 0.03 165)"
  line: "oklch(89% 0.01 150)"
  control: "oklch(70% 0.015 150)"
  danger: "oklch(44% 0.14 30)"
  danger-bg: "oklch(96% 0.016 30)"
  warning: "oklch(43% 0.08 70)"
  backdrop: "oklch(20% 0.02 160 / 0.32)"
typography:
  display:
    fontFamily: '"Instrument Sans", sans-serif'
    fontSize: "clamp(24px, 2.5vw, 36px)"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "-0.035em"
  title:
    fontFamily: '"Instrument Sans", sans-serif'
    fontSize: "18px"
    fontWeight: 500
    lineHeight: 1.5
  reading:
    fontFamily: '"Instrument Sans", sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.75
  body:
    fontFamily: '"Instrument Sans", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: '"Instrument Sans", sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
  code:
    fontFamily: "ui-monospace, monospace"
    fontSize: "0.86em"
rounded:
  control: "8px"
  panel: "20px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  2xl: "48px"
  3xl: "64px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.paper}"
  button-ghost:
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  button-ghost-hover:
    backgroundColor: "{colors.active}"
  button-send:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.paper}"
    rounded: "50%"
    width: "34px"
  button-send-disabled:
    backgroundColor: "{colors.active}"
    textColor: "{colors.muted}"
  input-settings:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
    width: "100%"
  nav-workspace:
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px"
    width: "100%"
  nav-workspace-active:
    backgroundColor: "{colors.active}"
  citation:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    rounded: "5px"
    padding: "4px 6px"
  citation-hover:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.paper}"
  document:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px"
    width: "100%"
  question-card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "{spacing.md}"
  composer:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "12px"
  excerpt:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "{spacing.lg}"
---

# Design System: DocuMind

## Overview

**Creative North Star: "Field-observation notes"**

DocuMind keeps reading and checking close together. White conversation and original-page surfaces sit within a pale mineral-green evidence workspace; the neutral navigation stays quiet. Instrument Sans, modest headings, and thin seams make the interface feel like working notes with a source open beside them.

The distinctive interaction is a small teal citation that selects the original PDF page and its extracted excerpt. Color marks evidence and state while the answer remains readable. This document records the implemented Next.js workspace; the classic Streamlit interface is a separate fallback. The source tokens are in `documind-web/app/tokens.css`, with applied styles in `documind-web/app/globals.css`.

**Key Characteristics:**

- White reading surfaces against a pale mineral-green evidence canvas.
- Deep teal reserved for evidence, focus, links, and action states.
- Quiet navigation, compact controls, and a readable answer measure.
- Conversation and original-page inspection retain separate scrolling.
- Explicit working, failed, stopped, and completed answer states.

## Colors

The palette uses one deep teal accent with green-tinted neutrals. The frontmatter preserves the source OKLCH values; use the matching CSS custom properties rather than substituting approximate hex colors.

### Primary

- **Evidence teal** (`accent`): citation text, source indexes, links, send action, focus outlines, and selected-document borders.
- **Evidence wash** (`accent-soft`): inline citation backgrounds, extracted evidence, and text selection.

### Neutral

- **White ground / paper** (`ground`, `paper`): conversation, controls, and original-page backing. They currently share a value but retain separate semantic roles.
- **Mineral canvas** (`canvas`): the evidence workspace.
- **Quiet panel** (`panel`): sidebar, question bubbles, review action, code blocks, and settings notes.
- **Selected leaf** (`active`): selected workspace and phone view, ordinary button hover, and disabled send background.
- **Reading ink** (`ink`): main text and the dark primary action.
- **Secondary ink** (`muted`): metadata, placeholders, help, and secondary actions.
- **Quiet seam** (`line`): panel divisions, document frames, and table rules.
- **Control edge** (`control`): input and composer boundaries, drawer edge, and scrollbars.
- **Dialog veil** (`backdrop`): translucent settings backdrop.

### State colors

- **Error clay / error wash** (`danger`, `danger-bg`): error and notice foreground/background pairs.
- **Caution ochre** (`warning`): pending service state and answer-detail warnings.

**The Evidence Pair Rule.** Keep citation and evidence foregrounds paired with their established washes; selected sources also carry a border or source index. Preserve text labels alongside service dots, draft states, and warnings so color does not carry their meaning alone.

## Typography

**Display and body font:** Instrument Sans, with a sans-serif fallback. The app serves the installed `@fontsource/instrument-sans` assets locally at weights 400, 500, and 600.
**Code font:** the platform monospace stack.

The same sans family carries headings, reading, and controls. Weight and space create hierarchy; the greeting stays proportionate to an application rather than becoming a promotional headline.

### Hierarchy

- **Display:** the empty-conversation heading uses the frontmatter's fluid size; at phone widths it is (30px). It introduces the next useful action.
- **Title:** the workspace title uses the title role; the phone header reduces it to the body size. Answer subheadings use the same section size with weight (600).
- **Reading:** answers use the reading role, a maximum measure of (70ch), and paragraph spacing from `md`. Question bubbles share the reading size.
- **Body:** controls, extracted excerpts, and general interface text use the body role. Excerpts use line-height (1.7).
- **Label:** navigation labels, status, source counts, and supporting actions use the label role. Small citation and helper text can be (11px); constrained composer metadata reaches (10px).
- **Code:** code inside answers uses the code role, with horizontally scrollable blocks.

**The Reading Measure Rule.** Keep answer text within its established measure and let tables, code, and long filenames overflow or wrap inside their own region.

## Layout

The desktop shell fills the viewport height. A navigation rail (232px) sits beside the working area; its header is (86px) high. The working area places conversation and evidence side by side, with a default column ratio of (1.25:1) and minimums of (360px / 320px). The rail can collapse without removing the current workspace.

Use the frontmatter spacing scale for repeated gaps and padding. Thin rules establish the shell; internal messages use generous paragraph spacing without a card around each answer. The conversation toolbar and composer remain outside the scrolling message list. The evidence pane, PDF image region, and bounded excerpt can scroll without moving the conversation.

At widths up to (1150px), the rail narrows to (200px), workbench minimums become (320px / 280px), and controls tighten. At widths up to (900px), show one working pane at a time through Conversation and PDF & evidence buttons. The header becomes (70px); the rail becomes a fixed drawer (260px) below it. Selecting a citation switches to PDF & evidence while retaining the conversation.

At widths up to (420px), constrain the header title and model pill, tighten the page toolbar, and reduce excerpt side spacing and padding to `md`. Ordinary phone buttons have a minimum height of (40px); primary actions and workspace rows retain their larger minimums, the send action stays (34px), and inline citations remain compact at (26px). At widths from (1700px), cap the workbench at (1550px) and use equal columns. The settings dialog is bounded by (480px) width and (90dvh) height.

## Elevation & Depth

The implemented workspace uses no box shadows. White paper, mineral canvas, selected fills, borders, and the translucent settings veil provide depth. Keep the page image flat: it is original user content, not a decorative card.

**The Tonal Depth Rule.** Separate working regions with the established surface tones and thin seams rather than introducing shadow stacks or gradients.

Motion is limited to interaction feedback: button color and press feedback use the fast duration (140ms) with `ease-out`; source excerpts enter over the panel duration (200ms) from a (6px) vertical offset and partial opacity. The working dot breathes between opacity (0.35) and (1) over (1s). Reduced-motion preference disables animations and transitions and restores automatic scroll behavior.

## Shapes

Controls, document rows, notes, and excerpts use the control radius; question bubbles, the composer, and settings use the panel radius. Model selection uses the pill radius. The send action is circular. Inline citations have compact corners (5px), and source indexes are small squares with corners (4px). Borders use the shared thin rule (1px). Do not round or crop the original PDF page into the surrounding control vocabulary.

## Components

### Buttons

Primary actions use white paper text on reading ink, with the primary frontmatter padding and a minimum height of (42px). New workspace uses the same dark treatment at a minimum of (40px). Their pointer hover becomes evidence teal. Ordinary actions stay transparent until hover; their background becomes the active fill. The circular send control is teal, hovers to ink, and becomes the active/muted pair while disabled. Stop uses ink.

Enabled buttons press to scale (0.97). Disabled buttons lose opacity (0.6), use muted text, and show a disabled cursor. Fine-pointer hover rules do not apply to touch. Focus-visible controls receive an accent outline (2px) offset by (3px); focused buttons suppress transition and do not scale while keyboard-activated.

### Inputs / Fields

Settings fields use white paper, control edges, the control radius, and the frontmatter padding. Placeholders and secondary help use muted ink. The composer uses a larger panel radius and a control border, which becomes teal when focus is inside it; its textarea has no separate outline. Keep the attach, length, and send/stop controls within the composer. Page-number inputs use tabular numerals.

### Navigation

Workspace rows are full-width, left-aligned, with a secondary count beneath the name. The selected row uses the active fill. Search uses a quiet bottom rule. The sidebar itself remains neutral. Phone view buttons use the same active fill and expose their pressed state; the hidden working pane does not compete for width.

### Cards / Containers

Question bubbles use quiet panel fill and the panel radius; answers sit directly on the conversation surface. Document rows use white paper with a quiet border and control corners; the selected document border becomes teal. The settings dialog uses white paper and the panel radius over the dialog veil. Do not add a shared raised-card treatment.

### Citations and evidence

Citation chips show a source index and PDF page number with tabular numerals. Their wash becomes solid teal with white text on fine-pointer hover. Activating one selects its document and page, displays the rendered original page, and reveals the exact extracted excerpt below it. On phone widths this also selects the evidence view and focuses its heading, whose accessible label identifies the file and PDF page. That heading uses the shared accent focus outline.

The excerpt uses evidence wash, a solid teal numbered source index, a page label, and the OCR comparison note. Its text is bounded and scrollable. The latest-answer source strip uses white bordered chips; the selected chip gains teal border and text. Preserve the distinction between the original PDF image and extracted text.

### Progress, results, and failure

Show the actual phase in the working area with a textual status and working dot. A generating message is marked Working; stopped and failed messages retain their draft labels. Completed answers expose copy, source count, and expandable evidence/response details. Keep Quick overview and Complete review as separately labeled actions. Errors use the error color pair with available retry and dismissal actions. A PDF rendering failure keeps a visible retry control in the source region.

## Do's and Don'ts

### Do:

- Do reuse the source CSS custom properties and the frontmatter's semantic token names.
- Do keep original pages and extracted excerpts visibly distinct.
- Do preserve the separate message and evidence scroll regions and the phone view switch.
- Do keep source indexes, page labels, status text, and keyboard focus visible.
- Do label synthetic examples and preserve the original proportions of rendered PDF pages.

### Don't:

- Don't turn the workspace into a promotional hero or add ornamental metrics.
- Don't add another accent family for ordinary navigation.
- Don't replace the flat tonal hierarchy with gradients, glass, or shadow stacks.
- Don't substitute an illustration or decorative raster for original source content.
- Don't present stopped or failed drafts as completed answers.

