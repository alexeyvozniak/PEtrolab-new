CREATE TABLE project_identity (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    project_id TEXT NOT NULL UNIQUE
);

INSERT INTO project_identity (singleton, project_id)
VALUES (1, lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) ||
                 '-4' || substr(hex(randomblob(2)), 2) ||
                 '-8' || substr(hex(randomblob(2)), 2) || '-' || hex(randomblob(6))));

CREATE TABLE work_group (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project_identity(project_id),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE work_group_analysis (
    work_group_id TEXT NOT NULL REFERENCES work_group(id),
    analysis_id TEXT NOT NULL REFERENCES analysis(analysis_id),
    position INTEGER NOT NULL,
    PRIMARY KEY (work_group_id, analysis_id),
    UNIQUE (work_group_id, position)
);
