# Mineral review workspace v1

The dedicated `Минералы` screen is the post-import expert review queue.
It complements the mineral step inside table import and uses the same
classifier contract.

## Main flow

1. Open `Минералы`; unresolved analyses appear first.
2. Filter by attention, all, resolved or an exact status.
3. Select a row and compare the reported source label, the classifier
   suggestion and the accepted interpretation.
4. Inspect ranked candidates, rule points, evidence, constraints and ruleset.
5. Accept the current suggestion, keep the recognized source interpretation,
   or clear the latest decision.

The screen never edits source text, measurements or the import recipe.
Accepted interpretations are project decisions with their own history.

## Product constraints

- Conflict and insufficient-input states remain visible until resolved.
- Candidate scores are rule points, not probabilities.
- High and medium suggestions may be accepted; ambiguous suggestions cannot.
- An unknown source label cannot be promoted to a controlled target implicitly.
- Every write is checked against the current input fingerprint and ruleset.
- Clearing a decision returns the Analysis to review and preserves audit history.
- The full chemical table remains available in `Анализы`; the review queue does
  not duplicate dozens of measurement columns.
