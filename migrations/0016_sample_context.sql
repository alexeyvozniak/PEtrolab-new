CREATE TABLE sample_context (
    sample_id TEXT PRIMARY KEY REFERENCES sample(sample_id),
    locality TEXT NOT NULL,
    storage TEXT NOT NULL,
    collection_position TEXT NOT NULL,
    collector TEXT NOT NULL,
    collection_date TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0)
);

CREATE TABLE sample_note (
    note_id TEXT PRIMARY KEY,
    sample_id TEXT NOT NULL REFERENCES sample(sample_id),
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX sample_note_by_sample ON sample_note(sample_id, created_at);
