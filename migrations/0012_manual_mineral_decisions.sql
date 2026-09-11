-- SQLite CHECK constraints need a table rebuild. Preserve every historical row
-- and its ordering. executescript needs an explicit transaction for the rebuild.
BEGIN IMMEDIATE;
CREATE TABLE mineral_assignment_decision_next (
    decision_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis(analysis_id),
    decision_kind TEXT NOT NULL CHECK (decision_kind IN ('accept_suggestion', 'keep_reported', 'clear', 'manual_assignment')),
    target TEXT,
    input_fingerprint_sha256 TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK ((decision_kind = 'clear' AND target IS NULL) OR (decision_kind != 'clear' AND target IS NOT NULL))
);
INSERT INTO mineral_assignment_decision_next
    SELECT * FROM mineral_assignment_decision ORDER BY rowid;
DROP TABLE mineral_assignment_decision;
ALTER TABLE mineral_assignment_decision_next RENAME TO mineral_assignment_decision;
CREATE INDEX idx_mineral_assignment_decision_analysis
    ON mineral_assignment_decision(analysis_id, created_at);
COMMIT;
