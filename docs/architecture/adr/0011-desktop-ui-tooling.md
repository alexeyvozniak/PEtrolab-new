# ADR-0011: UI tooling for the first Desktop v2 slices

- **Status:** Accepted
- **Date:** 2026-08-30

## Decision

Desktop v2 uses TypeScript, React and Tauri 2. The approved desktop views are composed from Radix UI primitives and local PetroLab components; Radix is not a scientific or persistence dependency.

- **Table:** TanStack Table owns column definitions, server-side filtering/sorting and row identity. React Virtuoso renders the virtualized body. `analysis_id` is the only row key.
- **UI state:** Zustand stores only transient UI state: open panels, viewport, local drafts and the synchronized Selection projection. It does not store Measurements, Calculation Runs, Work Groups or project truth.
- **Plots:** React SVG plus narrow D3 modules (`d3-scale`, `d3-shape`, `d3-array`) own axes, transforms and hit-testing. The same plot specification drives the on-screen SVG and export renderer. Plotly, canvas-first charts and SVG `clipPath`, `mask`, `foreignObject` are excluded from publication export.
- **Layout and interaction:** CSS Grid controls the workspace; `dnd-kit` controls only explicit panel/layer reordering. It never determines scientific order or membership.

## Consequences

The import core and SQLite service can be developed and tested before any React dependency is installed. UI choices cannot alter NDJSON commands, JSON schemas, scientific methods or SQLite entity identities. Any replacement of this stack requires an ADR and a proof that Corel-safe SVG and large-table accessibility remain intact.
