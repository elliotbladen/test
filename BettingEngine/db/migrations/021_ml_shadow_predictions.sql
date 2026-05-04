-- migration 021: ml_shadow_predictions table
-- Stores per-game ML shadow predictions each round alongside rules-engine values.
-- Actuals and error columns are NULL until results are entered via ingest_actuals.py.

CREATE TABLE IF NOT EXISTS ml_shadow_predictions (
    prediction_id       INTEGER  PRIMARY KEY AUTOINCREMENT,
    match_id            INTEGER  NOT NULL,
    season              INTEGER  NOT NULL,
    round_number        INTEGER  NOT NULL,
    run_date            TEXT     NOT NULL,          -- YYYY-MM-DD the shadow was run
    model_version       TEXT     NOT NULL,          -- e.g. margin_model_v20260501
    stats_date          TEXT,                       -- as_of_date of team_stats used

    -- Tier 1 input
    elo_diff            REAL,

    -- ML raw outputs (before adjustments)
    ml_raw_margin       REAL,
    ml_raw_total        REAL,
    ml_raw_h2h_prob     REAL,

    -- Adjustments applied
    t2_hcap             REAL,
    t2_tot              REAL,
    t5_hcap             REAL,
    t5_tot              REAL,
    t7_hcap             REAL,
    t7_tot              REAL,

    -- ML final outputs (after adjustments)
    ml_adj_margin       REAL,
    ml_adj_total        REAL,
    ml_adj_h2h_prob     REAL,

    -- Rules engine outputs for comparison
    rules_margin        REAL,
    rules_total         REAL,
    rules_h2h_prob      REAL,

    -- Divergence metrics
    margin_diff         REAL,   -- ml_adj_margin - rules_margin
    total_diff          REAL,   -- ml_adj_total  - rules_total
    h2h_diff            REAL,   -- (ml_adj_h2h_prob - rules_h2h_prob) * 100
    agreement_flag      TEXT    CHECK (agreement_flag IN ('strong', 'direction', 'disagree')),

    -- Actuals — filled in via ingest_actuals.py after results are known
    actual_margin       INTEGER,    -- positive = home win
    actual_total        INTEGER,
    actual_home_win     INTEGER,    -- 1 = home won, 0 = away won

    -- Error metrics — computed once actuals are filled
    ml_margin_error     REAL,       -- ml_adj_margin - actual_margin
    ml_total_error      REAL,       -- ml_adj_total  - actual_total
    ml_h2h_correct      INTEGER,    -- 1 if ML picked correct winner, 0 otherwise

    rules_margin_error  REAL,       -- rules_margin - actual_margin
    rules_total_error   REAL,       -- rules_total  - actual_total
    rules_h2h_correct   INTEGER,    -- 1 if rules picked correct winner, 0 otherwise

    created_at          TEXT     NOT NULL DEFAULT (strftime('%Y-%m-%d', 'now')),

    -- One prediction row per match per run. OR REPLACE on re-runs replaces the row cleanly.
    UNIQUE (match_id, run_date),
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

CREATE INDEX IF NOT EXISTS idx_ml_shadow_season_round
    ON ml_shadow_predictions (season, round_number);
