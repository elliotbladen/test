-- migration 009: add unique constraint to injury_reports for (match_id, team_id, player_name)
-- This allows ON CONFLICT DO UPDATE upserts from load_injury_round.py

-- SQLite does not support ADD CONSTRAINT, so we rebuild the table.
-- Existing data is preserved.

-- Guard: drop temp table if a previous failed attempt left it behind.
DROP TABLE IF EXISTS injury_reports_new;

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

    absence_type        TEXT     NOT NULL DEFAULT 'injury'
                            CHECK (absence_type IN ('injury', 'suspension')),

    UNIQUE (match_id, team_id, player_name),
    FOREIGN KEY (match_id) REFERENCES matches(match_id),
    FOREIGN KEY (team_id)  REFERENCES teams(team_id)
);

-- Use explicit column list so this INSERT works whether or not
-- injury_reports already has absence_type (added later by migration 015).
-- absence_type defaults to 'injury' for all rows being copied.
INSERT INTO injury_reports_new
    (injury_report_id, match_id, team_id, player_name, player_role,
     importance_tier, status, notes, source_url, captured_at, created_at)
    SELECT
        injury_report_id, match_id, team_id, player_name, player_role,
        importance_tier, status, notes, source_url, captured_at, created_at
    FROM injury_reports;

DROP TABLE injury_reports;
ALTER TABLE injury_reports_new RENAME TO injury_reports;

CREATE INDEX idx_injury_reports_match_team ON injury_reports(match_id, team_id);
