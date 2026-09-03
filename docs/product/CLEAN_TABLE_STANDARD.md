# PetroLab Clean Table v1

## Purpose

Clean Table is the stable, human-editable tabular interchange format for routine PetroLab imports. It is deliberately simpler than arbitrary laboratory or literature workbooks.

A file that satisfies the Clean Table contract uses the fast import path. A file that does not satisfy it remains fully supported through the raw-source preparation/review path; PetroLab never silently rewrites or discards source data to force a file into Clean Table.

## Core table contract

For every Clean Table data sheet:

1. Physical row 1 is the only header row.
2. One physical row after the header represents one Analysis.
3. Every populated physical column has a non-empty, unique header.
4. There are no merged header cells and no repeated header rows inside the data range.
5. At least one column maps explicitly to `Analysis`.
6. At least one column maps to a Measurement.
7. Every Measurement carries an explicit unit in its own header, for example `SiO2 [wt.%]`, `Li [ppm]`, `Si [at.%]`, `87Sr/86Sr [ratio]`.
8. Reported Fe forms are preserved as reported (`FeO`, `FeOt`, `Fe2O3`, etc.); Clean Table preparation never silently converts one form into another.
9. Censored source tokens such as `<0.5` remain unchanged.
10. Source-derived/calculated data are not silently presented as measured data. They should be separated into a Derived sheet or given explicit derived semantics in a later reviewed workflow.

## Standard roles

### Identity

- `Analysis` — required for the fast path.
- `Sample` — optional.
- `Point` — optional; use the same value across methods when records represent the same physical analytical point.

### Source metadata

The following headers are preserved as source metadata when present:

- `Mineral`
- `Generation`
- `Rock`
- `Source`
- `DOI`
- `Method`
- `Measurement set`
- `Comment`

Free-text source metadata is not automatically promoted to controlled PetroLab domain entities.

### Measurements

Canonical examples:

- `SiO2 [wt.%]`
- `FeO [wt.%]`
- `Li [ppm]`
- `Sr [ppb]`
- `Si [at.%]`
- `Fe3+ [apfu]`
- `87Sr/86Sr [ratio]`

`at.%` and `mol%` are distinct units.

## Fast-path acceptance

PetroLab may classify a workbook as `clean_table_fast` only from positive structural evidence. File names, sheet names, instrument names and prior user habits are not sufficient evidence.

The fast path is available only when all proposed imported sections are ordinary row-oriented Clean Table sections and no semantic warning remains unresolved. If duplicate candidate groups are found, an unknown unit is present, a populated field is unrecognized, a header is blank/duplicated, the table is transposed, or block boundaries are ambiguous, the file falls back to `raw_review`.

The fast confirmation screen must still show:

- imported sheet names;
- planned Analysis count;
- planned Measurement count;
- recognized identity/source-metadata fields;
- Measurement fields with units;
- any ignored non-data sheets when such ignoring is part of an explicit PetroLab template contract.

No data are written before user confirmation.

## Raw-source preparation

Raw workbooks remain immutable. PetroLab preparation is a reviewed transformation of interpretation, not a rewrite of the source. Preparation may identify logical blocks, orientation, header/data boundaries, units, roles, duplicate/subset relationships and media anchors. The resulting Import Recipe points back to exact source cells.

The long-term target is:

`Raw Source -> reviewed preparation recipe -> Clean Table logical representation -> Import Plan -> Project`

The physical raw workbook remains the provenance root.

## Initial raw scenarios

The preparation workflow is designed to grow by regression-tested adapters for these recurring scenarios:

1. instrument preamble before a table;
2. separate wt.% and at.% blocks;
3. repeated headers/sections;
4. transposed tables;
5. populated unknown or blank-header fields;
6. wide literature compilations;
7. mixed EPMA/SIMS/LA-ICP-MS method groups;
8. `<DL`, `bdl`, `n.d.` and similar tokens;
9. formula/derived columns;
10. legacy `.xls`;
11. workbooks with embedded images;
12. subset/duplicate sheets.

Each adapter must preserve exact physical source provenance and must degrade to manual review when confidence is insufficient.
