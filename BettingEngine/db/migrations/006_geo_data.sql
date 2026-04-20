-- =============================================================================
-- Migration 006 — Geographic data for Tier 3 travel calculations
-- =============================================================================
-- Adds lat/lng coordinates to venues and creates team_home_bases table.
-- These are static, one-time entries used by get_situational_context()
-- to compute haversine travel distances per game.
-- =============================================================================

-- Add coordinate columns to venues (no-op if already present in older SQLite)
ALTER TABLE venues ADD COLUMN lat REAL;
ALTER TABLE venues ADD COLUMN lng REAL;

-- Team home base coordinates.
-- One row per team — their primary geographic base for travel calculation.
-- Lat/lng are the team's home stadium or training base (whichever is used as
-- the origin for travel distance).
CREATE TABLE IF NOT EXISTS team_home_bases (
    home_base_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id       INTEGER NOT NULL UNIQUE REFERENCES teams(team_id),
    city          TEXT    NOT NULL,
    lat           REAL    NOT NULL,
    lng           REAL    NOT NULL,
    notes         TEXT,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_team_home_bases_team_id ON team_home_bases(team_id);
