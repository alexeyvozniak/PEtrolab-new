CREATE TABLE media_import_draft (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    fingerprint TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    saved_at TEXT NOT NULL
);
