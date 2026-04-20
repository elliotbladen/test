-- db/migrations/004_tier2_performance.sql
-- Tracks per-game Tier 2 prediction vs actual outcome for signal evaluation.
-- Pricing-time fields are written at model run time.
-- Error metrics are filled in after results are loaded.

CREATE TABLE IF NOT EXISTS tier2_performance (
    perf_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id          INTEGER NOT NULL REFERENCES matches(match_id),
    model_version     TEXT    NOT NULL,
    recorded_at       TEXT    NOT NULL,

    -- Match context
    season            INTEGER NOT NULL,
    round_number      INTEGER NOT NULL,
    match_date        TEXT    NOT NULL,
    home_team_id      INTEGER NOT NULL,
    away_team_id      INTEGER NOT NULL,

    -- Tier 1 output
    t1_home_pts       REAL    NOT NULL,
    t1_away_pts       REAL    NOT NULL,
    t1_margin         REAL    NOT NULL,

    -- Tier 2 family deltas (home perspective, post-combined-cap)
    t2a_home_delta    REAL    NOT NULL DEFAULT 0.0,
    t2b_home_delta    REAL    NOT NULL DEFAULT 0.0,
    t2c_home_delta    REAL    NOT NULL DEFAULT 0.0,
    t2_raw_total      REAL    NOT NULL DEFAULT 0.0,
    t2_capped_total   REAL    NOT NULL DEFAULT 0.0,
    t2_scale_applied  REAL,

    -- Signal labels for strength stratification
    t2a_label_h       TEXT,
    t2a_label_a       TEXT,
    t2b_label_h       TEXT,
    t2b_label_a       TEXT,
    t2c_label_h       TEXT,
    t2c_label_a       TEXT,

    -- Which families fired (comma-separated, e.g. 'A,C' or 'A,B,C' or '')
    fired_families    TEXT    NOT NULL DEFAULT '',

    -- Final model output (after Tier 2 applied)
    final_margin      REAL    NOT NULL,
    final_home_pts    REAL    NOT NULL,
    final_away_pts    REAL    NOT NULL,

    -- Actual result (NULL until result is known)
    actual_margin     REAL,
    actual_home_score INTEGER,
    actual_away_score INTEGER,
    actual_winner     TEXT,

    -- Error metrics (NULL until result is known)
    t1_abs_error          REAL,
    t12_abs_error         REAL,
    abs_improvement       REAL,
    t2_direction_correct  INTEGER,
    t1_winner_correct     INTEGER,
    final_winner_correct  INTEGER,

    UNIQUE(match_id, model_version)
);

CREATE INDEX IF NOT EXISTS idx_t2perf_season_round ON tier2_performance(season, round_number);
CREATE INDEX IF NOT EXISTS idx_t2perf_fired        ON tier2_performance(fired_families);
