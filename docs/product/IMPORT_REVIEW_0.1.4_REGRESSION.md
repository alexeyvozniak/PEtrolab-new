# PetroLab 0.1.4 import-review regression

Observed on a real instrument workbook in Desktop 0.1.3:

- raw Excel preview exposed only a fixed small row window, so the user could not reach the actual analytical header from the block card;
- instrument service metadata (`Sample: ...`, `Type: ...`, `Processing option: ...`) could be surfaced as a logical block before the real `Spectrum / elements...` table.

0.1.4 acceptance:

1. Raw preview supports paging backward/forward and direct row jump across the worksheet used range.
2. Editing header/data row numbers recentres the preview without applying the recipe.
3. Preview navigation never mutates source data or creates a recipe revision.
4. Colon-style service metadata and standalone `All results in ...` context rows do not become import sections.
5. The actual analytical table remains available as the logical block.
6. Windows installer and architecture/test suites must pass before merge.
