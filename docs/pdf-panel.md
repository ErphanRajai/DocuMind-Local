# Open and close PDF contents

The conversation workbench has a PDF-panel toggle in the top-right header and a close button beside **Source material**. Closing the panel gives the conversation the available width. Reopening it preserves the selected PDF, page, search and citation context. On phones, close returns to **Conversation**; **PDF & evidence** reopens the panel. Clicking an answer citation also opens the panel automatically.

## How it works

[app/page.tsx](../documind-web/app/page.tsx) owns one additional React state value:

```tsx
const [evidenceOpen, setEvidenceOpen] = useState(true);
```

State is a value React remembers while the page is open. The header control switches it and exposes `aria-expanded` plus `aria-controls="pdf-evidence"` so assistive technology can identify the controlled panel. The panel's close action also returns keyboard focus to the visible reopening control:

```tsx
function closeEvidence() {
  setEvidenceOpen(false);
  setMobileView("chat");
  (window.innerWidth <= 900 ? evidenceTab : evidenceToggle).current?.focus();
}
```

The desktop grid in [globals.css](../documind-web/app/globals.css) uses the state to switch to one conversation column:

```css
@media (min-width: 901px) {
  .workbench[data-evidence-open="false"] {
    grid-template-columns: minmax(0, 1fr);
  }
  .workbench[data-evidence-open="false"] .evidence {
    display: none;
  }
}
```

`display: none` removes the panel's controls from keyboard navigation and the accessibility tree. The component stays mounted, so its document/page/search state remains available on reopening. The existing phone tabs determine which pane is visible below the desktop breakpoint. The citation handler sets `evidenceOpen` to `true` before selecting the cited page and focusing its heading.

The input is a user action, and the output is a local layout change; no backend request or model generation is needed to toggle the panel. PDF loading/retry behavior stays with the existing viewer. The tradeoff is that hiding does not unload the viewer or remember the preference after a browser reload; it preserves the current reading context with minimal new state.

## Try it

1. Open a PDF in the conversation workbench and navigate to another page.
2. Close **Source material** with its × button. The conversation widens.
3. Use **Show PDF panel** in the header, including by keyboard. The same page returns.
4. Hide it again and click an answer citation. Its original page opens automatically.
5. At phone width, use **PDF & evidence**, close it, and reopen from that tab.

The production build and eight browser tests passed. [workbench.spec.ts](../documind-web/e2e/workbench.spec.ts) checks width expansion, retained page, citation reopening, mobile return/focus and existing conversation flows. Browser captures checked 1440px, 1280px and 390px widths using a public synthetic source. No backend change or new dependency is involved.
