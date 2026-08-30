# ADR-0010: Legacy scientific methods and workspace persistence

- **Status:** Accepted
- **Date:** 2026-08-30

## Context

Аудит Streamlit v1 показал проверенные механизмы, отсутствовавшие в Desktop v2 specification: versioned formula/mineral/statistics methods, input fingerprints, safe edit drafts, saved table views, exact workspace recovery and portable project archives. Копирование Streamlit pages or session-state architecture нарушило бы границы Desktop v2.

## Decision

Scientific Method Definition становится единственным контрактом для формул, classification suggestions, statistics, thermobarometry and partition models. Derived Value and Calculation Run store method version, inputs, assumptions and fingerprints.

Import Recipe, Edit Draft, Table View, Workspace Snapshot, Analysis Template and Operation Journal Entry are separate domain entities. Snapshot contains concrete research state; Template contains no concrete Analysis IDs. Portable archives have explicit inclusion levels and validated restore semantics.

Streamlit UI, wrappers, compatibility routes and session keys are not migrated. Legacy implementations are evidence and test input, not a code dependency.

## Consequences

Desktop v2 preserves scientific safety and small productivity mechanisms without reproducing the old page architecture. Additional persistence entities require schemas and migrations, but they remove the need for parallel UI state managers and prevent silent loss of research context.
