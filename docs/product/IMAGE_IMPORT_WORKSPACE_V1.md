# Image import workspace v1

The first image-import slice implements the approved Sample/Thin Section
assignment screen and keeps the later point-placement contract intact.

## Main flow

1. Select multiple PNG, JPEG, TIFF or BMP files in one native dialog.
2. Inspect format, dimensions, SHA-256 and physical duplicates before any
   project write.
3. Review conservative Sample, Thin Section and BSE/PPL/XPL suggestions parsed
   from the filename.
4. Confirm each file explicitly or apply one checked assignment to selected
   rows in bulk.
5. Validate the whole batch with the Python media planner.
6. Import the reviewed files without points when that is intentional. The plan
   records an `UNPLACED_MEDIA` warning for every such image.

Point placement remains the next screen in this same product flow. An image
imported without points can be linked later; no Analysis or source file is
changed by that omission.

## Product constraints

- Filename parsing creates suggestions, never accepted scientific metadata.
- The user sees the original display name at every step.
- Duplicate physical images block the plan instead of creating two assets.
- Managed copy is the safe default; linked external storage remains explicit.
- Batch confirmation affects only checked rows.
- Source files are never renamed, edited or deleted.
- Executable `.bat` files are not images and never appear in the picker.

