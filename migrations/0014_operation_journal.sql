CREATE TABLE operation_journal (
    id TEXT PRIMARY KEY,
    edit_draft_id TEXT UNIQUE REFERENCES edit_draft(id),
    entry_json TEXT NOT NULL
);
