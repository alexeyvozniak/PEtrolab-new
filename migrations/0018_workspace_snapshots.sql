CREATE TABLE workspace_snapshot (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    definition_json TEXT NOT NULL
);

CREATE TABLE analysis_template (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    definition_json TEXT NOT NULL
);
