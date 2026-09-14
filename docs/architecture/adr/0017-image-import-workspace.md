# ADR 0017 — Image import workspace boundary

Status: accepted and implemented through manual placement on 2026-09-08.

## Context

The media backend already validates PNG/JPEG/TIFF/BMP headers, dimensions,
fingerprints, assignments and source-pixel geometry. It can atomically create
Media Assets, Spatial Annotations and Analytical Point links, but the desktop
application did not expose that contract. A useful first UI slice must not
duplicate scientific validation in React or silently turn filename tokens into
project metadata.

## Decision

Tauri exposes a narrow multi-file picker filtered to the supported raster
extensions and a folder picker. Folder selection recursively enumerates only
supported regular files, skips filesystem links, sorts the resulting paths and
rejects collections above 5,000 files. It returns only paths inside the selected
tree. Python remains responsible for reading each image header and SHA-256.

`media.inspect_sources` now adds conservative filename suggestions to its
read-only projection. A modality token must be a separate `BSE`, `PPL` or `XPL`
token. Sample and Thin Section proposals come only from the prefix before that
token. The source display name and fingerprint remain unchanged.

React keeps suggestions and confirmed assignments separate. The batch cannot
reach `media.import.plan` until every row is explicitly confirmed. Duplicate
fingerprints block planning. Editing a confirmed field invalidates the reviewed
plan. Adding files or another folder extends the existing queue. Removing rows
only removes those draft entries, never source files. Retained assignments and
placements survive reinspection only when both path and SHA-256 are unchanged;
changed sources require fresh confirmation and placement. A late preview from
an earlier inspection cannot replace the current preview.

The image workspace stays mounted while a batch exists so navigation to Analyses
or Import preserves its assignments, placement draft and review phase. This is
in-session UI state, not a persistent draft across application restarts.

Bulk Sample/Thin Section and bulk media type are separate explicit operations.
Sample/Thin Section changes preserve per-image BSE/PPL/XPL/custom modality and
ownership mode. Each field group must have been reviewed before the combined
assignment becomes confirmed. A single-image confirmation accepts all displayed
fields. Selecting filename suggestions resets any previous custom-type editor.

The workspace may explicitly apply a valid plan with no placements; the backend
records `UNPLACED_MEDIA` warnings and the approved final review permits
completion without unplaced points.

Python exposes a read-only `analytical_point.list` projection and generates a
bounded PNG preview on demand. The preview preserves source-pixel axes and does
not apply EXIF rotation, so viewport clicks can be converted to the exact image
coordinates validated by `media.import.plan`. The full-resolution source never
crosses into React.

Point, Rectangle and Square placement remains a UI draft until the user presses
the explicit save action. Same-Sample filtering is the default. Choosing a Point
from another Sample requires a structured reason before the draft can enter the
plan. The final review shows image, assignment, placement and exception totals
before the single atomic apply.

## Consequences

- There is no second image parser in Rust or React.
- A clean BSE/PPL/XPL series can be confirmed in one batch action.
- Ambiguous filenames require manual fields but do not block other files.
- Importing without points is honest and reversible at the association layer;
  it is never presented as automatic point placement.
- Preview generation adds Pillow to the packaged Python service; Rust remains a
  file-dialog/process boundary and receives no media-domain rules.
