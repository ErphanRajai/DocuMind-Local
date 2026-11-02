# Collapsible PDF panel implementation supplement

## Overview

This Operate pass extends the existing conversation workbench so the reader can hide the right PDF contents panel and regain conversation width. It preserves DocuMind's **Field-observation notes** system. `DESIGN.md` and `.impeccable/design.json` remain the authority; neither was regenerated or edited. No new identity, token, dependency, backend behavior, or model work was introduced.

Basis: `PRODUCT.md`, `DESIGN.md`, `.impeccable/pdf-panel-brief.md`, `documind-web/app/page.tsx`, `documind-web/app/globals.css`, the relevant browser tests, and all six final captures below. The separate `docs/pdf-panel.md` explains the user flow and code mechanics.

## Layout

Above (900px), the header's PDF toggle and the close action beside **Source material** hide the evidence region. The workbench becomes one flexible conversation column, releasing the former evidence width while retaining the established answer reading measure. Reopening restores the incumbent two-column layout. The rail, conversation toolbar, composer, and independent scrolling regions retain their existing roles.

At widths up to (900px), the existing **Conversation** and **PDF & evidence** buttons remain the pane switch. Closing evidence returns to Conversation; its tab reopens the retained source context. The extra desktop toggle is hidden on phones.

## Components

- **Desktop opener:** existing icon-button treatment with Lucide panel-open/panel-close icons. Its accessible label and title change between “Show PDF panel” and “Hide PDF panel”; `aria-expanded` and `aria-controls` expose its state and target.
- **Panel close:** the existing control vocabulary and X icon sit beside the PDF count. Closing returns focus to the desktop header opener or the phone's PDF & evidence button.
- **Retained source:** the viewer stays mounted while hidden. Selected document, PDF page, page-search input, and citation context remain available when reopened. Hidden controls leave keyboard navigation and the accessibility tree through `display: none`.
- **Citation navigation:** activating a citation reopens evidence, selects its document/page, and focuses the source heading. On phones it also selects PDF & evidence. The original PDF image and extracted excerpt remain distinct.

## System preservation

The extension reuses Instrument Sans, mineral-green evidence surfaces, white conversation/paper, teal evidence states, thin seams, established radii, focus outlines, and button feedback. It adds no decorative treatment or motion. Source rendering, retry controls, generation states, uploads, settings, and the classic-interface fallback remain outside this change.

Existing design documentation and unrelated drift were preserved. Panel visibility is local page state; a browser reload restores its default rather than saving a visibility preference. Keeping the viewer mounted preserves reading context rather than unloading its resources.

## Evidence and validation

All six final captures were opened and visually inspected in this documentation pass. They use a controlled public synthetic answer and the rendered original page (119 of 120) from `source-120-pages.pdf`; no private document content appears.

| Viewport | Open evidence | Closed evidence |
| --- | --- | --- |
| Desktop (1440 × 900) | [Open](review/pdf-panel-desktop-open.png) | [Closed](review/pdf-panel-desktop-closed.png) |
| Compact desktop (1280 × 720) | [Open](review/pdf-panel-1280-open.png) | [Closed](review/pdf-panel-1280-closed.png) |
| Phone (390 × 844) | [Open](review/pdf-panel-mobile-open.png) | [Closed](review/pdf-panel-mobile-closed.png) |

The pairs show evidence alongside the answer when open, expanded conversation space on desktop when closed, and the existing single-pane phone flow. The PDF page and extracted evidence remain legible within their respective regions.

The implementation pass reported a passing production build and eight browser tests, covering width expansion, retained page, citation reopening, mobile return/focus, and existing conversation flows. The detector ran once on `page.tsx` and returned `[]`. The fresh independent finish reviewer returned all five contract sections with disposition **ship** and no material fixes. This documentation pass did not rerun those checks; screenshot evidence does not establish model accuracy or universal PDF/OCR correctness.
