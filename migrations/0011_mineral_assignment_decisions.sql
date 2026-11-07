-- Post-import mineral decisions are append-only interpretations. They never
-- replace the reported mineral, imported semantic evidence, or measurements.
CREATE TABLE mineral_assignment_decision (
    decision_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis(analysis_id),
    decision_kind TEXT NOT NULL CHECK (decision_kind IN ('accept_suggestion', 'keep_reported', 'clear')),
    target TEXT,
    input_fingerprint_sha256 TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK ((decision_kind = 'clear' AND target IS NULL) OR (decision_kind != 'clear' AND target IS NOT NULL))
);

CREATE INDEX idx_mineral_assignment_decision_analysis
    ON mineral_assignment_decision(analysis_id, created_at);
