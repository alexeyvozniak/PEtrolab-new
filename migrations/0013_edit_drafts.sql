CREATE TABLE edit_draft (
    id TEXT PRIMARY KEY,
    measurement_id TEXT NOT NULL REFERENCES measurement(measurement_id),
    definition_json TEXT NOT NULL
);
