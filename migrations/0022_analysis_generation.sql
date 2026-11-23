CREATE TABLE generation (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE analysis_generation (
    analysis_id TEXT PRIMARY KEY REFERENCES analysis(analysis_id),
    generation_id TEXT NOT NULL REFERENCES generation(id),
    assignment_id TEXT NOT NULL REFERENCES operation_journal(id),
    revision INTEGER NOT NULL CHECK (revision >= 1)
);
