# Design QA — Import columns and blocks

## Evidence

- Source visual truth: `../docs/design/reference/screens/import-columns-and-blocks-v1.png`.
- Intended implementation route: import columns and blocks, step 2 of 4.
- Intended viewport: desktop reference, 1480 × 1060 px.
- Build evidence: `npm run build` completed; `npm run test:sites` passed 4/4 on 2026-08-30.
- Browser-rendered implementation screenshot: unavailable.

## Primary interactions implemented

- selecting a worksheet changes the preview title and selected list item;
- changing header row, first data row, and mapping selects updates their controlled state;
- expanding visible rows updates the table count;
- the next-step action displays a local saved-draft confirmation.

## Findings

- [P0] Browser-rendered comparison is blocked.
  Location: cloud-browser preview.
  Evidence: both the Vite server and a static server on `0.0.0.0:4173` were unreachable from the cloud browser with `net::ERR_CONNECTION_REFUSED`.
  Impact: the implementation cannot be compared to the approved reference at the same viewport; fonts, spacing, colors, asset fidelity, copy wrapping and overflow remain unverified.
  Fix: run the existing `npm run dev -- --host 0.0.0.0 --port 4173 --strictPort` in a preview environment visible to the cloud browser, capture the route, then perform the required full-view and focused-region comparison.

## Required fidelity surfaces

- Fonts and typography: blocked pending rendered evidence.
- Spacing and layout rhythm: blocked pending rendered evidence.
- Colors and visual tokens: blocked pending rendered evidence.
- Image quality and asset fidelity: blocked pending rendered evidence. Icons use `@phosphor-icons/react`; no hand-drawn SVG icons or placeholder imagery were added.
- Copy and content: implemented from the approved Russian reference, but wrapping is blocked pending rendered evidence.

## Implementation checklist

1. Restore a browser-visible local preview.
2. Capture the desktop import screen in the reference state.
3. Test worksheet selection, header/data-row selects, mapping select, visible-row toggle and save-draft confirmation in the browser.
4. Inspect console errors and compare the capture with the reference.
5. Correct P0/P1/P2 differences and update this report with final evidence.

final result: blocked
