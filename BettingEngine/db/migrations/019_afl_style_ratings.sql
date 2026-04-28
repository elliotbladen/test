-- =============================================================================
-- 019_afl_style_ratings.sql
-- AFL Tier 2 style rating tables.
--
-- Tables:
--   afl_team_style_ratings   — rolling per-team style ratings (updated weekly)
--   afl_key_position_ratings — per-team key forward / key defender ratings
--   afl_t2_matchup_log       — logged T2 adjustments per match (audit trail)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- afl_team_style_ratings
-- One row per team per season per round.
-- Raw stats normalised to ratings in range [-1.0, +1.0] relative to league avg.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS afl_team_style_ratings (
    rating_id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    team_id             INTEGER  NOT NULL,
    season              INTEGER  NOT NULL,
    as_of_round         INTEGER  NOT NULL,   -- ratings valid entering this round

    -- Raw stats (per game averages over rolling window)
    contested_poss_pg   REAL,    -- contested possessions per game
    clearances_pg       REAL,    -- total clearances per game
    inside_50s_pg       REAL,    -- inside 50s per game
    marks_inside_50_pg  REAL,    -- marks inside 50 per game
    scoring_shots_pg    REAL,    -- scoring shots per game (goals + behinds)
    goal_conv_pct       REAL,    -- goals / scoring shots
    rebound_50s_pg      REAL,    -- rebound 50s per game
    intercept_poss_pg   REAL,    -- intercept possessions per game
    hitouts_pg          REAL,    -- total hitouts per game
    hitouts_adv_pg      REAL,    -- hitouts to advantage per game

    -- Normalised ratings (-1.0 = well below avg, 0 = avg, +1.0 = elite)
    -- Computed by: (team_stat - league_avg) / league_std, clipped to [-1,+1]
    cp_rating           REAL,    -- contested possession family
    clearance_rating    REAL,    -- clearance component
    forward_entry_rating REAL,   -- inside 50s / scoring shot volume
    scoring_eff_rating  REAL,    -- goal conversion efficiency
    defensive_reb_rating REAL,   -- rebound 50s + intercept possessions
    ruck_rating         REAL,    -- hitouts to advantage

    -- Sample
    games_in_window     INTEGER  DEFAULT 0,
    data_source         TEXT,    -- footywire | afl_tables | manual

    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (team_id) REFERENCES teams(team_id),
    UNIQUE (team_id, season, as_of_round)
);

-- ---------------------------------------------------------------------------
-- afl_key_position_ratings
-- Season-level key forward and key defender ratings per team.
-- Updated when team selection changes (injury, form drop).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS afl_key_position_ratings (
    kp_id               INTEGER  PRIMARY KEY AUTOINCREMENT,
    team_id             INTEGER  NOT NULL,
    season              INTEGER  NOT NULL,
    as_of_round         INTEGER  NOT NULL,

    -- Key forward
    kf_player_name      TEXT,    -- primary key forward
    kf_rating           REAL,    -- 0-10 scale (10 = elite: Cameron, Hawkins, Lynch)
    kf_games_played     INTEGER,
    kf_goals_pg         REAL,    -- goals per game this season
    kf_avg_impact       REAL,    -- derived: goals_pg * 6 + behinds_pg (pts contribution)

    -- Key defender
    kd_player_name      TEXT,
    kd_rating           REAL,    -- 0-10 scale (10 = elite: Andrews, Weitering, Laird)

    -- Second key forward / back (for teams with two quality key players)
    kf2_player_name     TEXT,
    kf2_rating          REAL,
    kd2_player_name     TEXT,
    kd2_rating          REAL,

    -- Ruck
    ruck_player_name    TEXT,
    ruck_rating         REAL,    -- 0-10 scale (10 = Gawn, Grundy tier)

    data_source         TEXT,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (team_id) REFERENCES teams(team_id),
    UNIQUE (team_id, season, as_of_round)
);

-- ---------------------------------------------------------------------------
-- afl_t2_matchup_log
-- Audit log of every T2 calculation — one row per match.
-- Mirrors NRL model_adjustments table for AFL T2.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS afl_t2_matchup_log (
    log_id              INTEGER  PRIMARY KEY AUTOINCREMENT,
    match_id            INTEGER  NOT NULL UNIQUE,
    season              INTEGER  NOT NULL,
    round_number        INTEGER  NOT NULL,

    -- Family 1: Contested Possession
    f1_home_cp_rating   REAL,
    f1_away_cp_rating   REAL,
    f1_differential     REAL,    -- home - away (normalised)
    f1_pts_delta        REAL,    -- final point adjustment from this family

    -- Family 2: Forward Pressure
    f2_home_fp_rating   REAL,
    f2_away_fp_rating   REAL,
    f2_differential     REAL,
    f2_pts_delta        REAL,

    -- Family 3: Defensive Rebound
    f3_home_dr_rating   REAL,
    f3_away_dr_rating   REAL,
    f3_differential     REAL,
    f3_pts_delta        REAL,

    -- Family 4: Key Position Matchup
    f4_home_kf_rating   REAL,
    f4_away_kf_rating   REAL,
    f4_home_kd_rating   REAL,
    f4_away_kd_rating   REAL,
    f4_matchup_delta    REAL,    -- (home_kf - away_kd) - (away_kf - home_kd)
    f4_pts_delta        REAL,

    -- Totals
    t2_handicap_delta   REAL,    -- total T2 margin adjustment (home perspective)
    t2_totals_delta     REAL,    -- total T2 totals adjustment

    -- Applied flags
    f1_applied          BOOLEAN  DEFAULT 0,
    f2_applied          BOOLEAN  DEFAULT 0,
    f3_applied          BOOLEAN  DEFAULT 0,
    f4_applied          BOOLEAN  DEFAULT 0,

    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_afl_style_team_season
    ON afl_team_style_ratings (team_id, season);

CREATE INDEX IF NOT EXISTS idx_afl_kp_team_season
    ON afl_key_position_ratings (team_id, season);

CREATE INDEX IF NOT EXISTS idx_afl_t2_log_match
    ON afl_t2_matchup_log (match_id);

-- Migration record
INSERT OR IGNORE INTO schema_migrations (migration_name, applied_at)
VALUES ('019_afl_style_ratings', CURRENT_TIMESTAMP);
