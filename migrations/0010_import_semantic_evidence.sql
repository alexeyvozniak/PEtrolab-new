-- Additive evidence; existing analyses and sample entities are not reinterpreted.
CREATE TABLE analysis_import_semantics (
    analysis_id TEXT PRIMARY KEY REFERENCES analysis(analysis_id),
    sample_association_json TEXT NOT NULL,
    reported_mineral_json TEXT,
    mineral_assignment_json TEXT,
    mineral_verification_json TEXT,
    analytical_method_json TEXT
);

CREATE TABLE project_analyte_alias (
    normalized_header TEXT PRIMARY KEY,
    alias_json TEXT NOT NULL,
    confirmed_at TEXT NOT NULL
);
