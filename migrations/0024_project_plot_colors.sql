CREATE TABLE project_plot_colors (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    definition_json TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0)
);
