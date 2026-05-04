-- =============================================================================
-- 020_market_intelligence_storage.sql
-- Persist Betmate automation context and market-intelligence research outputs.
-- =============================================================================

CREATE TABLE IF NOT EXISTS betmate_import_runs (
    import_run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    season             INTEGER NOT NULL,
    round_number       INTEGER NOT NULL,
    source_round_dir   TEXT,
    stage_dir          TEXT,
    imported_at        TEXT NOT NULL,
    status             TEXT NOT NULL,
    injuries_count     INTEGER NOT NULL DEFAULT 0,
    referees_count     INTEGER NOT NULL DEFAULT 0,
    emotional_count    INTEGER NOT NULL DEFAULT 0,
    manifest_json      TEXT NOT NULL,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_betmate_import_runs_round
    ON betmate_import_runs(season, round_number, imported_at);

CREATE TABLE IF NOT EXISTS betmate_preflight_checks (
    preflight_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    season             INTEGER NOT NULL,
    round_number       INTEGER NOT NULL,
    run_date           TEXT NOT NULL,
    checked_at         TEXT NOT NULL,
    ok                 INTEGER NOT NULL,
    errors_json        TEXT NOT NULL,
    warnings_json      TEXT NOT NULL,
    details_json       TEXT NOT NULL,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_betmate_preflight_round
    ON betmate_preflight_checks(season, round_number, checked_at);

CREATE TABLE IF NOT EXISTS market_intel_profiles (
    profile_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sport              TEXT NOT NULL,
    market_type        TEXT NOT NULL,  -- h2h | total | handicap
    profile_name       TEXT NOT NULL,
    team_name          TEXT,
    era                TEXT NOT NULL,
    move_direction     TEXT NOT NULL,  -- firm | drift_up | drift_down
    bet_selection      TEXT NOT NULL,  -- home/away/team | over | under
    sample_start       TEXT,
    sample_end         TEXT,
    bets               INTEGER NOT NULL,
    wins               INTEGER NOT NULL,
    losses             INTEGER NOT NULL,
    pushes             INTEGER NOT NULL DEFAULT 0,
    hit_rate           REAL NOT NULL,
    avg_odds           REAL,
    breakeven_rate     REAL,
    edge_pp            REAL,
    profit_1u          REAL NOT NULL,
    roi                REAL NOT NULL,
    avg_move           REAL,
    notes              TEXT,
    source_file        TEXT,
    calculated_at      TEXT NOT NULL,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (sport, market_type, profile_name, team_name, era, move_direction, bet_selection)
);

CREATE INDEX IF NOT EXISTS idx_market_intel_profiles_lookup
    ON market_intel_profiles(sport, market_type, team_name, era, move_direction);

CREATE TABLE IF NOT EXISTS market_intel_signals (
    signal_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id           INTEGER,
    sport              TEXT NOT NULL,
    season             INTEGER,
    round_number       INTEGER,
    market_type        TEXT NOT NULL,
    team_name          TEXT,
    direction          TEXT NOT NULL,
    signal_label       TEXT NOT NULL,
    strength           TEXT,
    confidence         REAL,
    model_agrees       INTEGER,
    current_move       REAL,
    profile_roi        REAL,
    notes              TEXT,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

CREATE INDEX IF NOT EXISTS idx_market_intel_signals_round
    ON market_intel_signals(sport, season, round_number, market_type);

