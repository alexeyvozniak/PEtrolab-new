# ADR 0013: Clean Table fast import and raw-source preparation split

**Status:** Accepted for implementation
**Date:** 2026-09-01

## Context

The general import review must support messy real workbooks: instrument preambles, multiple blocks, repeated headers, transposed tables, mixed methods, literature compilations and unknown fields. That flexibility is necessary, but it makes routine imports unnecessarily expensive when the user has already prepared a normalized table.

Trying to make one screen simultaneously optimal for both clean tables and arbitrary workbooks creates UI complexity and encourages over-aggressive recognition.

## Decision

### 1. Two explicit import modes

Python classifies the inspected source into one of two presentation modes:

- `clean_table_fast` — strict Clean Table contract is satisfied;
- `raw_review` — any ambiguity or unsupported structure remains.

React renders the mode returned by Python. React does not decide whether a workbook is clean.

### 2. Fast mode reuses the same immutable Import Recipe and Import Plan

Fast mode is not a second persistence path. It uses the same recipe validation, plan creation, duplicate detection, provenance and atomic apply implementation as raw review.

The only difference is presentation: structural/mapping editors are omitted when Python has already proven that no review decision is needed.

This prevents fast import from bypassing scientific rules.

### 3. Classification is strict and one-way safe

A false negative is acceptable: a valid Clean Table may fall back to raw review.

A false positive is not acceptable: an ambiguous workbook must never be silently treated as clean.

`clean_table_fast` therefore requires positive evidence for every imported section:

- row 1 is the header;
- rows are analyses;
- at least one explicit Analysis identity mapping;
- at least one Measurement mapping;
- every populated source field is recognized and has a non-empty unique header;
- every Measurement has an explicit unit from its own header;
- no unresolved import warnings;
- no duplicate candidate groups;
- no repeated-header/block ambiguity.

File/sheet/instrument names are not evidence.

### 4. Standard metadata aliases are lossless source metadata

`Rock`, `Source`, `DOI`, `Method`, `Measurement set` and `Comment` may be recognized as source metadata for Clean Table. They are not automatically promoted to controlled domain entities or used to mutate Measurement semantics unless a later explicit model supports that transformation.

### 5. Raw review becomes preparation UX

The existing block/orientation/mapping workflow remains available and is presented as source preparation. Its goal is to create an explicit normalized recipe from the immutable raw workbook.

Future raw adapters may pre-populate preparation decisions, but they must always degrade to the same review model when confidence is insufficient.

### 6. Classification result is inspectable

Python returns a compact classification object containing:

- `mode`;
- `reasons` when raw review is required;
- section summaries;
- recognized identity/metadata/measurement fields;
- planned counts after plan creation.

This makes the mode regression-testable and diagnosable.

## Consequences

- routine Clean Table imports require only one confirmation screen;
- raw import remains powerful without defining the normal daily UX;
- scientific validation and SQLite persistence are not duplicated;
- future raw-file automation can grow independently of the fast path;
- regression tests must prove that ambiguous files fall back rather than fast-importing.

## Rejected alternatives

### Make the user choose “clean” vs “raw” before selecting a file

Rejected because the user should not need to know whether a workbook satisfies implementation details. PetroLab can classify conservatively after inspection and still allow the user to open detailed review.

### Auto-clean the workbook and save a modified Excel file

Rejected as the primary path because it breaks source immutability and can obscure provenance. Any exported cleaned workbook is a derived convenience artifact, not the provenance root.

### Maintain a separate fast-import database writer

Rejected because it would duplicate validation, provenance and atomicity rules and eventually diverge from reviewed import behavior.
