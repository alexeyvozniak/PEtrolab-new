CREATE TABLE table_view (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    definition_json TEXT NOT NULL
);
