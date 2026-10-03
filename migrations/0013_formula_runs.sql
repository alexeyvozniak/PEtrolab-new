BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS formula_project (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    project_id TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS formula_run (
    run_id TEXT PRIMARY KEY,
    input_fingerprint TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS formula_derived_value (
    derived_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES formula_run(run_id),
    analysis_id TEXT NOT NULL REFERENCES analysis(analysis_id),
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_formula_value_analysis ON formula_derived_value(analysis_id, run_id);
CREATE INDEX IF NOT EXISTS idx_formula_value_run ON formula_derived_value(run_id);
COMMIT;
