-- 008_venue_tables.sql
-- Tier 4 venue layer tables.
-- Adds per-team venue performance stats and overall venue scoring profiles.

CREATE TABLE IF NOT EXISTS team_venue_stats (
    team_id         INTEGER NOT NULL REFERENCES teams(team_id),
    venue_id        INTEGER NOT NULL REFERENCES venues(venue_id),
    games           INTEGER NOT NULL DEFAULT 0,
    avg_margin      REAL    NOT NULL DEFAULT 0.0,
    overall_margin  REAL    NOT NULL DEFAULT 0.0,
    venue_edge      REAL    NOT NULL DEFAULT 0.0,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, venue_id)
);

CREATE TABLE IF NOT EXISTS venue_profiles (
    venue_id         INTEGER PRIMARY KEY REFERENCES venues(venue_id),
    venue_name       TEXT,
    avg_total_score  REAL    NOT NULL DEFAULT 0.0,
    league_avg_total REAL    NOT NULL DEFAULT 0.0,
    total_edge       REAL    NOT NULL DEFAULT 0.0,
    games_in_sample  INTEGER NOT NULL DEFAULT 0,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
