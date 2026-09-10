# Image import workspace v1

The image-import workspace implements the approved Sample/Thin Section
assignment, manual point-placement and final-review states.

## Main flow

1. Select multiple PNG, JPEG, TIFF or BMP files in one native dialog, or select
   a folder and collect supported images from its nested folders as one batch.
2. Inspect format, dimensions, SHA-256 and physical duplicates before any
   project write.
3. Review conservative Sample, Thin Section and BSE/PPL/XPL suggestions parsed
   from the filename.
4. Confirm each file explicitly or confirm the filename suggestions for checked
   rows. Bulk Sample/Thin Section and bulk image type are separate actions so a
   BSE/PPL/XPL series keeps its modalities. Custom image types are supported.
5. Open a bounded preview of each real image and show same-Sample Analytical
   Points first, with not-yet-placed points above placed points.
6. Choose Point, Rectangle or Square and place it manually. The viewport turns
   the gesture into source-pixel coordinates; coordinates are not typed by the
   user and remain a draft until explicitly saved.
7. Open Points from another Sample only through the separate scope. A reason is
   mandatory before such a placement can be saved.
8. Validate the entire batch with the Python planner and review every image,
   placement, exception and unplaced-image warning before one atomic apply.
9. Finish without unplaced points when that omission is intentional. No
   Analysis, Sample or source file changes because a point is omitted.

## Product constraints

- Filename parsing creates suggestions, never accepted scientific metadata.
- The user sees the original display name at every step.
- Duplicate physical images block the plan instead of creating two assets.
- Managed copy is the safe default; linked external storage remains explicit.
- Batch confirmation affects only checked rows.
- Focusing or placing a Point does not change the global Selection.
- Zoom changes only the viewport; persisted geometry remains in source pixels.
- Cross-Sample placement preserves both Sample assignments and records the
  explicit exception reason.
- Source files are never renamed, edited or deleted.
- Folder enumeration is deterministic, does not follow filesystem links and is
  capped at 5,000 supported images before Python inspection begins.
- Executable `.bat` files are not images and never appear in the picker.
- Add files or folders to the current queue without losing reviewed assignments
  or saved placements on unchanged sources; remove checked entries to resolve
  duplicate blocking. Show source paths to distinguish equal filenames.
- Navigation between Images, Import and Analyses preserves the current image
  draft in memory. Application-restart persistence is not part of this slice.
- A source whose fingerprint changed loses its former confirmation and spatial
  placements and must be reviewed again. Cancelled/empty folder selection leaves
  the current queue intact.
