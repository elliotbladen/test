-- =============================================================================
-- schema.sql
-- NRL Pricing Engine V1 - Relational Schema
-- Target: SQLite (designed to scale to PostgreSQL)
-- =============================================================================
--
-- Design rules (from docs/schema.md):
--
--   Rule 1: Each match has one canonical match_id.
--   Rule 2: market_snapshots are append-only. New rows only, no overwrites.
--   Rule 3: Every model_run stores model_version.
--   Rule 4: Every signal traces back to: match + market_snapshot + model_run.
--   Rule 5: Every actual bet traces back to a signal.
--   Rule 6: Both baseline outputs and tier adjustment outputs are stored.
--
-- Traceability chain:
--
--   matches
--     -> market_snapshots   (append-only price history)
--     -> results            (final score, one per match)
--     -> match_context      (contextual variables for Tiers 3-7, one per match)
--     -> model_runs         (one full pricing run per match execution)
--          -> model_adjustments  (one row per tier adjustment per run)
--          -> signals            (one row per market/bookmaker opportunity per run)
--               -> bets          (actual user action, separate from recommendation)
--
--   bankroll_log            (append-only bankroll state history)
--
-- =============================================================================

PRAGMA foreign_keys = ON;

-- =============================================================================
-- 1. teams
--    Canonical team identities. All match and stats rows reference this table.
-- =============================================================================
CREATE TABLE IF NOT EXISTS teams (
    team_id         INTEGER  PRIMARY KEY AUTOINCREMENT,
    team_name       TEXT     NOT NULL,                   -- full canonical name
    team_short_name TEXT,                                -- abbreviation, e.g. "SYD"
    league          TEXT     NOT NULL,                   -- e.g. "NRL"
    active_flag     BOOLEAN  NOT NULL DEFAULT 1,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 2. venues
--    Canonical venue identities.
--    home_team_id is the team that uses this as their primary ground (nullable).
-- =============================================================================
CREATE TABLE IF NOT EXISTS venues (
    venue_id        INTEGER  PRIMARY KEY AUTOINCREMENT,
    venue_name      TEXT     NOT NULL,
    city            TEXT,
    state           TEXT,
    country         TEXT,
    home_team_id    INTEGER,                             -- nullable: neutral venues have no home team
    surface_type    TEXT,                                -- e.g. "grass" | "synthetic"
    venue_notes     TEXT,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (home_team_id) REFERENCES teams(team_id)
);

-- =============================================================================
-- 3. referees
--    Canonical referee identities. Used by Tier 6 adjustment logic.
-- =============================================================================
CREATE TABLE IF NOT EXISTS referees (
    referee_id      INTEGER  PRIMARY KEY AUTOINCREMENT,
    referee_name    TEXT     NOT NULL,
    active_flag     BOOLEAN  NOT NULL DEFAULT 1,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 4. matches
--    One canonical row per match. All other tables key off match_id.
--
--    status allowed values: scheduled | completed | postponed | cancelled
--
--    source_match_key: the external identifier used for idempotent ingestion.
--    A partial unique index prevents the same external match being imported twice.
-- =============================================================================
CREATE TABLE IF NOT EXISTS matches (
    match_id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    sport               TEXT     NOT NULL,               -- e.g. "NRL"
    competition         TEXT     NOT NULL,               -- e.g. "NRL Premiership"
    season              INTEGER  NOT NULL,
    round_number        INTEGER,                         -- nullable for finals rounds
    match_date          DATE     NOT NULL,
    kickoff_datetime    DATETIME NOT NULL,
    home_team_id        INTEGER  NOT NULL,
    away_team_id        INTEGER  NOT NULL,
    venue_id            INTEGER  NOT NULL,
    status              TEXT     NOT NULL
                            CHECK (status IN ('scheduled','completed','postponed','cancelled')),
    referee_id          INTEGER,                         -- nullable until assigned
    source_match_key    TEXT,                            -- external id for idempotent ingestion

    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (venue_id)     REFERENCES venues(venue_id),
    FOREIGN KEY (referee_id)   REFERENCES referees(referee_id)
);

-- Core query patterns: fetch by season, by date
CREATE INDEX IF NOT EXISTS idx_matches_season     ON matches(season);
CREATE INDEX IF NOT EXISTS idx_matches_match_date ON matches(match_date);

-- Prevent duplicate ingestion of the same external match.
-- Partial index: only enforce uniqueness when source_match_key is populated.
CREATE UNIQUE INDEX IF NOT EXISTS uidx_matches_source_key
    ON matches(source_match_key)
    WHERE source_match_key IS NOT NULL;

-- =============================================================================
-- 5. bookmakers
--    Canonical bookmaker identities.
--    bookmaker_code is the stable internal identifier (e.g. "pinnacle", "bet365").
--    priority_rank: lower number = higher priority (1 = sharpest benchmark).
-- =============================================================================
CREATE TABLE IF NOT EXISTS bookmakers (
    bookmaker_id    INTEGER  PRIMARY KEY AUTOINCREMENT,
    bookmaker_name  TEXT     NOT NULL,
    bookmaker_code  TEXT     NOT NULL UNIQUE,            -- stable internal code
    priority_rank   INTEGER,                             -- 1 = highest priority
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 6. market_snapshots  [APPEND-ONLY]
--    Stores bookmaker market prices at a specific point in time.
--    Rows are never updated or deleted. New snapshots are always new rows.
--
--    market_type allowed values:  h2h | handicap | total
--    selection_name allowed values: home | away | over | under
--    source_method allowed values:  manual | scrape | api
--
--    is_opening: true if this is the first known price for this market.
--    is_closing: true if this is the price at market close.
--    line_value: the handicap or total line (NULL for h2h markets).
-- =============================================================================
CREATE TABLE IF NOT EXISTS market_snapshots (
    snapshot_id     INTEGER  PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER  NOT NULL,
    bookmaker_id    INTEGER  NOT NULL,
    captured_at     DATETIME NOT NULL,
    market_type     TEXT     NOT NULL
                        CHECK (market_type IN ('h2h','handicap','total')),
    selection_name  TEXT     NOT NULL
                        CHECK (selection_name IN ('home','away','over','under')),
    line_value      REAL,                                -- NULL for h2h; set for handicap/total
    odds_decimal    REAL     NOT NULL
                        CHECK (odds_decimal >= 1.01),   -- decimal odds must be >= 1.01
    is_opening      BOOLEAN  NOT NULL DEFAULT 0,
    is_closing      BOOLEAN  NOT NULL DEFAULT 0,
    source_url      TEXT,
    source_method   TEXT     NOT NULL
                        CHECK (source_method IN ('manual','scrape','api')),
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id)     REFERENCES matches(match_id),
    FOREIGN KEY (bookmaker_id) REFERENCES bookmakers(bookmaker_id)
);

-- Core query patterns from docs/schema.md Required Indexing Priorities
CREATE INDEX IF NOT EXISTS idx_snapshots_match_id    ON market_snapshots(match_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_bookmaker   ON market_snapshots(bookmaker_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_captured_at ON market_snapshots(captured_at);

-- Composite index for the most common lookup: all prices for a match by bookmaker and market
CREATE INDEX IF NOT EXISTS idx_snapshots_match_book_market
    ON market_snapshots(match_id, bookmaker_id, market_type);

-- =============================================================================
-- 7. results
--    Final match outcomes. One row per match (enforced by UNIQUE on match_id).
--
--    margin convention: positive = home team won by that many points.
--    winning_team_id: NULL for draws (no draws in NRL; retained for completeness).
--    result_status allowed values: final | forfeit | void
-- =============================================================================
CREATE TABLE IF NOT EXISTS results (
    result_id       INTEGER  PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER  NOT NULL UNIQUE,            -- one result per match
    home_score      INTEGER  NOT NULL,
    away_score      INTEGER  NOT NULL,
    total_score     INTEGER  NOT NULL,
    margin          INTEGER  NOT NULL,                   -- positive = home win
    winning_team_id INTEGER,                             -- NULL for draws
    result_status   TEXT     NOT NULL
                        CHECK (result_status IN ('final','forfeit','void')),
    captured_at     DATETIME,                            -- when the result was recorded
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id)        REFERENCES matches(match_id),
    FOREIGN KEY (winning_team_id) REFERENCES teams(team_id)
);

-- =============================================================================
-- 8. team_stats
--    Derived team-level stats for Tier 1 baseline pricing.
--    One row per (team, season, as_of_date) — unique constraint prevents duplicates.
--    Stats are point-in-time snapshots, not live values.
-- =============================================================================
CREATE TABLE IF NOT EXISTS team_stats (
    team_stat_id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    team_id                 INTEGER  NOT NULL,
    season                  INTEGER  NOT NULL,
    as_of_date              DATE     NOT NULL,
    games_played            INTEGER,
    wins                    INTEGER,                     -- total wins in the season window
    losses                  INTEGER,                     -- total losses in the season window
    win_pct                 REAL,                        -- wins / games_played (0.0–1.0)
    ladder_position         INTEGER,                     -- ladder rank as of as_of_date (1 = top); nullable
    points_for_avg          REAL,                        -- season avg points scored per game
    points_against_avg      REAL,                        -- season avg points conceded per game
    home_points_for_avg     REAL,
    home_points_against_avg REAL,
    away_points_for_avg     REAL,
    away_points_against_avg REAL,
    elo_rating              REAL,
    attack_rating           REAL,
    defence_rating          REAL,
    recent_form_rating      REAL,

    -- -----------------------------------------------------------------------
    -- Tier 2 yardage bucket fields
    -- All nullable REAL. NULL until populated by the team stats importer.
    -- The Tier 2 signals return 0.0 (neutral) for any NULL field gracefully.
    -- -----------------------------------------------------------------------
    -- Signal 1: run metres / post-contact metres
    run_metres_pg           REAL,   -- avg run metres per game this season
    post_contact_metres_pg  REAL,   -- avg post-contact metres per game (optional; falls back gracefully)
    -- Signal 2: completion / errors / discipline
    completion_rate         REAL,   -- set completion rate as decimal (0.0–1.0)
    errors_pg               REAL,   -- unforced errors per game
    penalties_pg            REAL,   -- penalties conceded per game
    -- Signal 3: kick metres
    kick_metres_pg          REAL,   -- avg kick metres per game
    -- Signal 4: ruck speed (placeholder; stays NULL until a data source is onboarded)
    ruck_speed_score        REAL,   -- composite ruck speed / PTB proxy score

    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (team_id, season, as_of_date),                -- no duplicate stat snapshots

    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

-- Commonly queried by team and season
CREATE INDEX IF NOT EXISTS idx_team_stats_team_season ON team_stats(team_id, season);

-- =============================================================================
-- 8b. team_style_stats
--     Tier 2 style stats — kept separate from team_stats so Tier 1 data
--     is never cluttered by Tier 2 fields as more style families are added.
--     One row per (team, season, as_of_date). Upsert-safe.
--
--     Stage 1 — Family B: Creation / Attacking Shape (LB, TB, MT, LBC)
--     Future  — Family A and D columns are commented in below; uncomment
--               when those families are approved and data is sourced.
-- =============================================================================
CREATE TABLE IF NOT EXISTS team_style_stats (
    style_stat_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id         INTEGER NOT NULL REFERENCES teams(team_id),
    season          INTEGER NOT NULL,
    as_of_date      TEXT    NOT NULL,

    -- -----------------------------------------------------------------------
    -- Family B: Creation / Attacking Shape  [Stage 1 — live]
    -- -----------------------------------------------------------------------
    lb_pg           REAL,   -- linebreaks per game (style)
    tb_pg           REAL,   -- tackle busts per game (style)
    mt_pg           REAL,   -- missed tackles per game (vulnerability)
    lbc_pg          REAL,   -- linebreaks conceded per game (vulnerability)

    -- -----------------------------------------------------------------------
    -- Family A: Territory / Control  [live — approved 2026-04-04]
    -- -----------------------------------------------------------------------
    completion_rate  REAL,   -- set completion rate as decimal (0.0–1.0)  [style]
    kick_metres_pg   REAL,   -- avg kick metres per game                  [style]
    errors_pg        REAL,   -- unforced errors per game                  [style inverted + vulnerability; shared with Family C style inverted]
    penalties_pg     REAL,   -- penalties conceded per game               [style inverted + vulnerability]

    -- -----------------------------------------------------------------------
    -- Family C: Physical Carry & Forward Dominance  [live — approved 2026-04-04]
    -- -----------------------------------------------------------------------
    run_metres_pg    REAL,   -- avg run metres per game                   [style; mt_pg from Family B used as vulnerability]

    -- -----------------------------------------------------------------------
    -- Family D: Territorial Kicking Pressure  [future — uncomment when approved]
    -- -----------------------------------------------------------------------
    -- ak_pg         REAL,   -- attacking kicks per game
    -- fdo_pg        REAL,   -- forced dropouts per game
    -- (shares err_pg, pc_pg, rm_pg from Family A above — no duplication)

    source_note     TEXT,   -- audit trail: data source, date pulled, etc.

    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(team_id, season, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_team_style_stats_team_season
    ON team_style_stats(team_id, season);

-- =============================================================================
-- 9. match_context
--    Contextual variables consumed by Tiers 3–7.
--    One row per match (enforced by UNIQUE on match_id).
--
--    Tier 3: rest_days, off_bye flags
--    Tier 4: travel_km, venue_fortress_flag_home
--    Tier 5: injury count summaries (detail is in injury_reports)
--    Tier 6: populated via referee table
--    Tier 7A: weather fields
--    Tier 7B: lunar phase flags (experimental — see tiers.yaml)
-- =============================================================================
CREATE TABLE IF NOT EXISTS match_context (
    context_id                      INTEGER  PRIMARY KEY AUTOINCREMENT,
    match_id                        INTEGER  NOT NULL UNIQUE,   -- one context row per match

    -- Tier 3: Situational
    home_rest_days                  INTEGER,
    away_rest_days                  INTEGER,
    home_off_bye                    BOOLEAN  NOT NULL DEFAULT 0,
    away_off_bye                    BOOLEAN  NOT NULL DEFAULT 0,

    -- Tier 4: Venue / travel
    home_travel_km                  REAL,
    away_travel_km                  REAL,
    venue_fortress_flag_home        BOOLEAN,

    -- Tier 5: Injury summary counts (detail rows are in injury_reports)
    home_key_injuries_count         INTEGER,
    away_key_injuries_count         INTEGER,
    home_spine_injuries_count       INTEGER,
    away_spine_injuries_count       INTEGER,

    -- Tier 7A: Weather
    weather_rain_flag               BOOLEAN  NOT NULL DEFAULT 0,
    weather_wind_kph                REAL,
    weather_temp_c                  REAL,
    weather_humidity_pct            REAL,
    weather_summary                 TEXT,

    -- Tier 7B: Lunar phase (experimental — controlled by tiers.yaml lunar.enabled)
    full_moon_flag                  BOOLEAN  NOT NULL DEFAULT 0,
    new_moon_flag                   BOOLEAN  NOT NULL DEFAULT 0,
    moon_window_plus_minus_one_day  BOOLEAN  NOT NULL DEFAULT 0,

    created_at                      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

-- Always looked up by match
CREATE INDEX IF NOT EXISTS idx_match_context_match_id ON match_context(match_id);

-- =============================================================================
-- 10. injury_reports
--     Granular player-level injury entries for Tier 5.
--     Multiple rows per match and team are expected (one per injured player).
--
--     player_role allowed values:  fullback | halfback | five_eighth | hooker | pack | other
--     importance_tier allowed values: elite | key | rotation
--     status allowed values: out | doubtful | managed | available
-- =============================================================================
CREATE TABLE IF NOT EXISTS injury_reports (
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

    FOREIGN KEY (match_id) REFERENCES matches(match_id),
    FOREIGN KEY (team_id)  REFERENCES teams(team_id)
);

-- Tier 5 always queries by match and team
CREATE INDEX IF NOT EXISTS idx_injury_reports_match_team ON injury_reports(match_id, team_id);

-- =============================================================================
-- 11. model_runs
--     One row per full pricing execution for one match.
--     Stores both baseline (Tier 1) outputs and final (post-all-tiers) outputs.
--     model_version must be stored to enable comparison across engine versions.
--
--     run_status allowed values: success | failed | partial
-- =============================================================================
CREATE TABLE IF NOT EXISTS model_runs (
    model_run_id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    match_id                INTEGER  NOT NULL,
    run_timestamp           DATETIME NOT NULL,
    model_version           TEXT     NOT NULL,           -- e.g. "1.0.0"

    -- Tier 1 baseline outputs (stored separately for full auditability — Rule 6)
    baseline_home_points    REAL     NOT NULL,
    baseline_away_points    REAL     NOT NULL,
    baseline_margin         REAL     NOT NULL,
    baseline_total          REAL     NOT NULL,

    -- Final outputs after all tiers applied
    final_home_points       REAL     NOT NULL,
    final_away_points       REAL     NOT NULL,
    final_margin            REAL     NOT NULL,
    final_total             REAL     NOT NULL,

    -- Derived fair prices
    home_win_probability    REAL     NOT NULL
                                CHECK (home_win_probability > 0 AND home_win_probability < 1),
    away_win_probability    REAL     NOT NULL
                                CHECK (away_win_probability > 0 AND away_win_probability < 1),
    fair_home_odds          REAL     NOT NULL
                                CHECK (fair_home_odds >= 1.01),
    fair_away_odds          REAL     NOT NULL
                                CHECK (fair_away_odds >= 1.01),
    fair_handicap_line      REAL     NOT NULL,
    fair_total_line         REAL     NOT NULL,

    run_status              TEXT     NOT NULL
                                CHECK (run_status IN ('success','failed','partial')),
    notes                   TEXT,
    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

-- Core query: fetch all runs for a match
CREATE INDEX IF NOT EXISTS idx_model_runs_match_id ON model_runs(match_id);

-- =============================================================================
-- 12. model_adjustments
--     One row per tier adjustment applied during a model run.
--     Stores the full name, code, description, and numeric deltas for every
--     adjustment so the pricing output is fully reproducible.
--
--     tier_number: 1–7 matching the pricing tier definitions.
--     applied_flag: 0 means the adjustment was evaluated but not applied
--                   (e.g. tier disabled in config).
-- =============================================================================
CREATE TABLE IF NOT EXISTS model_adjustments (
    adjustment_id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    model_run_id            INTEGER  NOT NULL,
    tier_number             INTEGER  NOT NULL
                                CHECK (tier_number BETWEEN 1 AND 7),
    tier_name               TEXT     NOT NULL,           -- e.g. "venue", "injury", "lunar"
    adjustment_code         TEXT     NOT NULL,           -- machine-readable key, e.g. "bye_factor"
    adjustment_description  TEXT     NOT NULL,           -- human-readable explanation
    home_points_delta       REAL     NOT NULL DEFAULT 0,
    away_points_delta       REAL     NOT NULL DEFAULT 0,
    margin_delta            REAL     NOT NULL DEFAULT 0,
    total_delta             REAL     NOT NULL DEFAULT 0,
    applied_flag            BOOLEAN  NOT NULL DEFAULT 1,
    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (model_run_id) REFERENCES model_runs(model_run_id)
);

-- Adjustments are always fetched by model run
CREATE INDEX IF NOT EXISTS idx_model_adjustments_run_id ON model_adjustments(model_run_id);

-- =============================================================================
-- 13. signals
--     One row per market/bookmaker opportunity identified in a model run.
--     Traceability: model_run_id + match_id + snapshot_id (Rule 4).
--
--     snapshot_id: the specific market snapshot this signal was priced against.
--     This is required by Design Rule 4.
--
--     market_type allowed values:   h2h | handicap | total
--     confidence_level allowed values: low | medium | high
--     signal_label allowed values:
--       no_bet | pass | watch | recommend_small | recommend_medium | recommend_strong
-- =============================================================================
CREATE TABLE IF NOT EXISTS signals (
    signal_id                INTEGER  PRIMARY KEY AUTOINCREMENT,
    model_run_id             INTEGER  NOT NULL,
    match_id                 INTEGER  NOT NULL,
    snapshot_id              INTEGER  NOT NULL,           -- the snapshot this signal is priced against (Rule 4)
    bookmaker_id             INTEGER  NOT NULL,
    market_type              TEXT     NOT NULL
                                 CHECK (market_type IN ('h2h','handicap','total')),
    selection_name           TEXT     NOT NULL
                                 CHECK (selection_name IN ('home','away','over','under')),
    line_value               REAL,                        -- NULL for h2h
    market_odds              REAL     NOT NULL
                                 CHECK (market_odds >= 1.01),
    model_odds               REAL,                        -- NULL if model cannot price this market
    model_probability        REAL     NOT NULL
                                 CHECK (model_probability > 0 AND model_probability <= 1),
    ev_value                 REAL     NOT NULL,           -- e.g. 0.25 = +25% EV
    ev_percent               REAL     NOT NULL,           -- ev_value * 100
    raw_kelly_fraction       REAL     NOT NULL,
    applied_kelly_fraction   REAL     NOT NULL,           -- raw_kelly * 0.25 (quarter Kelly)
    capped_stake_fraction    REAL     NOT NULL,           -- after hard cap applied
    recommended_stake_amount REAL     NOT NULL,           -- in base currency
    confidence_level         TEXT     NOT NULL
                                 CHECK (confidence_level IN ('low','medium','high')),
    signal_label             TEXT     NOT NULL
                                 CHECK (signal_label IN (
                                     'no_bet','pass','watch',
                                     'recommend_small','recommend_medium','recommend_strong'
                                 )),
    veto_flag                BOOLEAN  NOT NULL DEFAULT 0,
    veto_reason              TEXT,                        -- populated when veto_flag = 1

    created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (model_run_id) REFERENCES model_runs(model_run_id),
    FOREIGN KEY (match_id)     REFERENCES matches(match_id),
    FOREIGN KEY (snapshot_id)  REFERENCES market_snapshots(snapshot_id),
    FOREIGN KEY (bookmaker_id) REFERENCES bookmakers(bookmaker_id)
);

-- Core query patterns from docs/schema.md Required Indexing Priorities
CREATE INDEX IF NOT EXISTS idx_signals_match_id    ON signals(match_id);
CREATE INDEX IF NOT EXISTS idx_signals_bookmaker   ON signals(bookmaker_id);

-- Signals are commonly fetched by model run (e.g. to display all signals for a run)
CREATE INDEX IF NOT EXISTS idx_signals_model_run   ON signals(model_run_id);

-- =============================================================================
-- 14. bets
--     Actual user actions. Separate from recommendations (signals).
--     A bet row is written only when the user decides to act on a signal.
--     placed_flag = 0 means the row was created but the bet was not submitted.
--
--     result allowed values: win | loss | void | pending
-- =============================================================================
CREATE TABLE IF NOT EXISTS bets (
    bet_id              INTEGER  PRIMARY KEY AUTOINCREMENT,
    signal_id           INTEGER  NOT NULL,
    placed_flag         BOOLEAN  NOT NULL DEFAULT 0,
    placed_timestamp    DATETIME,                        -- NULL until placed
    bookmaker_id        INTEGER  NOT NULL,
    stake_amount        REAL     NOT NULL
                            CHECK (stake_amount > 0),
    odds_taken          REAL     NOT NULL
                            CHECK (odds_taken >= 1.01),
    line_taken          REAL,                            -- handicap or total line taken
    result              TEXT
                            CHECK (result IN ('win','loss','void','pending')),
    pnl_amount          REAL,                            -- NULL until settled
    closing_odds        REAL,                            -- for CLV calculation
    clv_value           REAL,                            -- closing line value
    notes               TEXT,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (signal_id)    REFERENCES signals(signal_id),
    FOREIGN KEY (bookmaker_id) REFERENCES bookmakers(bookmaker_id)
);

-- Core query from docs/schema.md Required Indexing Priorities
CREATE INDEX IF NOT EXISTS idx_bets_signal_id ON bets(signal_id);

-- =============================================================================
-- 15. bankroll_log  [APPEND-ONLY]
--     Point-in-time bankroll state. Never updated, only appended.
--     Used for tracking performance over time and stake sizing.
-- =============================================================================
CREATE TABLE IF NOT EXISTS bankroll_log (
    bankroll_log_id   INTEGER  PRIMARY KEY AUTOINCREMENT,
    log_timestamp     DATETIME NOT NULL,
    starting_bankroll REAL     NOT NULL
                          CHECK (starting_bankroll >= 0),
    ending_bankroll   REAL     NOT NULL
                          CHECK (ending_bankroll >= 0),
    open_exposure     REAL     NOT NULL DEFAULT 0
                          CHECK (open_exposure >= 0),   -- total at risk in unsettled bets
    closed_pnl        REAL     NOT NULL DEFAULT 0,       -- realised PnL in this period
    notes             TEXT,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
