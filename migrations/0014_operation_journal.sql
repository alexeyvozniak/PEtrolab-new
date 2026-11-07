PRAGMA foreign_keys = ON;

CREATE TABLE operation_journal_entry (
    operation_id TEXT PRIMARY KEY,
    action_kind TEXT NOT NULL,
    actor TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_ids_json TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('applied', 'undone')),
    inverse_action_kind TEXT,
    inverse_payload_json TEXT,
    undone_by_operation_id TEXT REFERENCES operation_journal_entry(operation_id),
    created_at TEXT NOT NULL
);

CREATE TABLE analytical_point_retraction (
    analytical_point_id TEXT PRIMARY KEY REFERENCES analytical_point(analytical_point_id),
    operation_id TEXT NOT NULL UNIQUE REFERENCES operation_journal_entry(operation_id),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_operation_journal_entity ON operation_journal_entry(entity_type, created_at);
CREATE INDEX idx_operation_journal_action ON operation_journal_entry(action_kind, created_at);
