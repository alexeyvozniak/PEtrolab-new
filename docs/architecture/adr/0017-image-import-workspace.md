# ADR 0017 — Image import workspace boundary

Status: accepted for the first UI slice requested on 2026-09-07.

## Context

The media backend already validates PNG/JPEG/TIFF/BMP headers, dimensions,
fingerprints, assignments and source-pixel geometry. It can atomically create
Media Assets, Spatial Annotations and Analytical Point links, but the desktop
application did not expose that contract. A useful first UI slice must not
duplicate scientific validation in React or silently turn filename tokens into
project metadata.

## Decision

Tauri exposes a narrow multi-file picker filtered to the supported raster
extensions. It returns only the paths explicitly chosen by the user. Python
remains responsible for reading each image header and SHA-256.

`media.inspect_sources` now adds conservative filename suggestions to its
read-only projection. A modality token must be a separate `BSE`, `PPL` or `XPL`
token. Sample and Thin Section proposals come only from the prefix before that
token. The source display name and fingerprint remain unchanged.

React keeps suggestions and confirmed assignments separate. The batch cannot
reach `media.import.plan` until every row is explicitly confirmed. Duplicate
fingerprints block planning. Editing a confirmed field invalidates the reviewed
plan.

The first vertical slice may explicitly apply a valid plan with no placements;
the backend already records `UNPLACED_MEDIA` warnings and the approved final
review permits completion without unplaced points. The next slice adds the
manual Point/Rectangle/Square screen without changing this assignment contract.

## Consequences

- There is no second image parser in Rust or React.
- A clean BSE/PPL/XPL series can be confirmed in one batch action.
- Ambiguous filenames require manual fields but do not block other files.
- Importing without points is honest and reversible at the association layer;
  it is never presented as automatic point placement.
- The point-placement PR work can consume the same reviewed assignments and
  append source-pixel geometry before the atomic apply.

