-- 007_referee_tables.sql
-- Tier 6 referee layer tables.
-- Adds referee profiling, team bucket edge stats, and weekly assignment tracking.

CREATE TABLE IF NOT EXISTS referee_profiles (
    referee_id        INTEGER PRIMARY KEY REFERENCES referees(referee_id),
    bucket            TEXT    NOT NULL CHECK (bucket IN ('whistle_heavy','flow_heavy','neutral')),
    games_in_sample   INTEGER NOT NULL DEFAULT 0,
    notes             TEXT,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS team_ref_bucket_stats (
    stat_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id     INTEGER NOT NULL REFERENCES teams(team_id),
    bucket      TEXT    NOT NULL CHECK (bucket IN ('whistle_heavy','flow_heavy','neutral')),
    season      INTEGER NOT NULL,
    games       INTEGER NOT NULL DEFAULT 0,
    bucket_edge REAL    NOT NULL DEFAULT 0.0,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (team_id, bucket, season)
);

CREATE TABLE IF NOT EXISTS weekly_ref_assignments (
    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id      INTEGER NOT NULL REFERENCES matches(match_id),
    referee_id    INTEGER NOT NULL REFERENCES referees(referee_id),
    season        INTEGER NOT NULL,
    round_number  INTEGER NOT NULL,
    source        TEXT    NOT NULL DEFAULT 'manual',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (match_id)
);
