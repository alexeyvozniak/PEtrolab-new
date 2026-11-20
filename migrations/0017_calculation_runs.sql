CREATE TABLE calculation_run (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project_identity(project_id),
    created_at TEXT NOT NULL,
    definition_json TEXT NOT NULL
);

CREATE TABLE work_group_calculation_origin (
    work_group_id TEXT PRIMARY KEY REFERENCES work_group(id),
    calculation_run_id TEXT NOT NULL REFERENCES calculation_run(id),
    cluster INTEGER NOT NULL CHECK (cluster >= 0)
);
