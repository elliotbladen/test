-- =============================================================================
-- 018_afl_drop_umpire.sql
-- Remove AFL umpire tier (Tier 6 not applicable in AFL).
-- Rationale: 3 rotating field umpires, no reliable public tracking data,
-- effect size too small relative to AFL's 170-190pt scoring environment.
-- AFL tier flow: T1(ML) → T2 → T3 → T4 → T5 → T7 → T8
-- =============================================================================

-- Drop umpire stats table entirely
DROP TABLE IF EXISTS afl_umpire_stats;

-- SQLite does not support DROP COLUMN directly in older versions.
-- Rebuild afl_match_context without umpire columns.
CREATE TABLE IF NOT EXISTS afl_match_context_new (
    context_id              INTEGER  PRIMARY KEY AUTOINCREMENT,
    match_id                INTEGER  NOT NULL UNIQUE,

    -- Tier 3: Rest / Travel
    home_rest_days          INTEGER,
    away_rest_days          INTEGER,
    home_travel_km          REAL,
    away_travel_km          REAL,

    -- Tier 4: Venue context
    is_neutral_venue        BOOLEAN  DEFAULT 0,

    -- Tier 5: Injuries
    home_injury_pts         REAL     DEFAULT 0.0,
    away_injury_pts         REAL     DEFAULT 0.0,

    -- Tier 7: Emotional
    has_emotional_flags     BOOLEAN  DEFAULT 0,

    -- Tier 8: Weather
    precipitation_mm        REAL,
    wind_kmh                REAL,
    temp_c                  REAL,
    weather_condition       TEXT,

    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

-- Copy any existing rows (table is likely empty at this stage)
INSERT INTO afl_match_context_new
    (context_id, match_id, home_rest_days, away_rest_days,
     home_travel_km, away_travel_km, is_neutral_venue,
     home_injury_pts, away_injury_pts, has_emotional_flags,
     precipitation_mm, wind_kmh, temp_c, weather_condition,
     created_at, updated_at)
SELECT context_id, match_id, home_rest_days, away_rest_days,
       home_travel_km, away_travel_km, is_neutral_venue,
       home_injury_pts, away_injury_pts, has_emotional_flags,
       precipitation_mm, wind_kmh, temp_c, weather_condition,
       created_at, updated_at
FROM afl_match_context;

DROP TABLE afl_match_context;
ALTER TABLE afl_match_context_new RENAME TO afl_match_context;

-- Migration record
INSERT OR IGNORE INTO schema_migrations (migration_name, applied_at)
VALUES ('018_afl_drop_umpire', CURRENT_TIMESTAMP);
