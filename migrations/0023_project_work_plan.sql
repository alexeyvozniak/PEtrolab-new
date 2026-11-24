CREATE TABLE project_work_plan_task (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    completed INTEGER NOT NULL CHECK (completed IN (0, 1)),
    revision INTEGER NOT NULL CHECK (revision > 0)
);
