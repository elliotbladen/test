-- migration 009: add unique constraint to injury_reports for (match_id, team_id, player_name)
-- This allows ON CONFLICT DO UPDATE upserts from load_injury_round.py

-- SQLite does not support ADD CONSTRAINT, so we rebuild the table.
-- Existing data is preserved.

CREATE TABLE injury_reports_new (
    injury_report_id    INTEGER  PRIMARY KEY AUTOINCREMENT,
    match_id            INTEGER  NOT NULL,
    team_id             INTEGER  NOT NULL,
    player_name         TEXT     NOT NULL,
    player_role         TEXT
                            CHECK (player_role IN ('fullback','halfback','five_eighth','hooker','pack','other')),
    importance_tier     TEXT
                            CHECK (importance_tier IN ('elite','key','rotation')),
    status              TEXT     NOT NULL
                            CHECK (status IN ('out','doubtful','managed','available')),
    notes               TEXT,
    source_url          TEXT,
    captured_at         DATETIME,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (match_id, team_id, player_name),
    FOREIGN KEY (match_id) REFERENCES matches(match_id),
    FOREIGN KEY (team_id)  REFERENCES teams(team_id)
);

INSERT INTO injury_reports_new
    SELECT * FROM injury_reports;

DROP TABLE injury_reports;
ALTER TABLE injury_reports_new RENAME TO injury_reports;

CREATE INDEX idx_injury_reports_match_team ON injury_reports(match_id, team_id);
