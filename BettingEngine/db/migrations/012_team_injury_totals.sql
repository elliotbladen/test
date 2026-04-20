-- migration 012: add team_injury_totals for pre-aggregated injury burden per team per match

CREATE TABLE IF NOT EXISTS team_injury_totals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id    INTEGER NOT NULL REFERENCES matches(match_id),
    team_id     INTEGER NOT NULL REFERENCES teams(team_id),
    total_injury_pts REAL NOT NULL DEFAULT 0.0,
    source      TEXT,          -- e.g. 'spreadsheet', 'manual', 'auto'
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, team_id)
);
