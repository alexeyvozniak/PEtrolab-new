# Mineral review audit — 2026-09-07

Surface: PR #17 head before this slice, desktop viewport 1348 × 926.
Dataset: realistic EPMA fixture with consistent, conflict, missing and verified
states. The fixture is presentation-only; scientific behavior is separately
covered by Python tests.

## Observed current flow

1. `Анализы` overview — functional but the mineral status competes with a wide
   table. Important mineral columns leave the viewport behind horizontal scroll.
2. Conflict filter — status filtering works and keeps the source coordinate.
3. Evidence expansion — source, suggestion and accepted values are separated,
   but reasons are raw internal/English strings, scores lack units and there is
   no post-import decision action.

## Changes required by the audit

- Provide a dedicated task queue with unresolved items first.
- Keep reported, suggested and accepted values together in the review pane.
- Label candidate scores as rule points, not confidence percentages.
- Translate stable diagnostic codes and show the ruleset version.
- Add explicit stale-safe accept/keep/clear actions.
- Keep the wide, lossless chemistry table in `Анализы` instead of reproducing it.

## Accessibility risks checked

Buttons, search and queues use native controls and explicit accessible labels.
Status does not rely on color alone. Keyboard activation is covered by native
button/select semantics. Screenshot review cannot establish full contrast,
screen-reader order or Windows scaling behavior; native CI remains required.

## Post-change flow verification

1. Dedicated queue — healthy. Attention, all, resolved and exact-status queues
   show counts and retain Analysis/Sample context without horizontal scrolling.
2. Conflict review — healthy. Reported text, suggestion and accepted
   interpretation stay visible together; rule scores have units and stable
   diagnostic codes are presented as readable text.
3. Explicit acceptance — healthy. Accepting a suggestion removes the row from
   the attention queue and makes it available in the resolved queue.
4. Decision inspection — healthy. The resolved row shows the accepted target,
   keeps the conflicting source label intact and exposes a clear action.
5. Persistence boundary — healthy in automated service tests. Accept, keep and
   clear append decision events; stale fingerprints are rejected, and a clear
   event also suppresses an assignment accepted during import without deleting
   either historical record.

The after-change pass used the same 1348 × 926 viewport and fixture as the
baseline. The layout was additionally tightened for the application's supported
1180 × 800 minimum; the native Windows gate remains the authority for WebView
scaling and packaging.

## Verdict

Accepted for the post-import mineral review slice. The dedicated workflow is
usable and scientifically explicit; the remaining evidence limits are Windows
font scaling, assistive-technology reading order and very large real-project
performance, which belong in native CI and later field validation.
