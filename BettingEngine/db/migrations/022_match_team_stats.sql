-- migration 022: match_team_stats
-- Per-match, per-team stats fetched from Fox Sports Stats API.
-- Source: statsapi.foxsports.com.au/3.0/api/sports/league/matches/{id}/teamstats.json
-- Coverage: NRL 2022+
-- Match ID format: NRL{year}{round:02d}{match:02d}  e.g. NRL20220801

CREATE TABLE IF NOT EXISTS match_team_stats (
    stat_id                         INTEGER  PRIMARY KEY AUTOINCREMENT,
    fox_match_id                    TEXT     NOT NULL,  -- e.g. NRL20220101
    match_id                        INTEGER,            -- FK to matches if resolved
    season                          INTEGER  NOT NULL,
    round_number                    INTEGER  NOT NULL,
    match_number                    INTEGER  NOT NULL,  -- within round
    team_side                       TEXT     NOT NULL CHECK (team_side IN ('home','away')),
    team_fox_id                     INTEGER,
    team_name                       TEXT,
    team_code                       TEXT,

    -- Attack
    runs                            INTEGER,
    run_metres                      INTEGER,
    post_contact_metres             INTEGER,
    one_pass_runs                   INTEGER,
    dummy_half_runs                 INTEGER,
    line_breaks                     INTEGER,
    line_break_assists              INTEGER,
    line_break_causes               INTEGER,
    tackle_busts                    INTEGER,
    off_loads                       INTEGER,
    effective_offloads              INTEGER,
    try_assists                     INTEGER,
    tries                           INTEGER,
    points                          INTEGER,

    -- Possession / sets
    possession_percentage           REAL,
    territory                       REAL,
    total_sets                      INTEGER,
    complete_sets                   INTEGER,
    completion_rate_str             TEXT,    -- raw "36/43"
    completion_rate_pct             REAL,    -- derived
    errors                          INTEGER,
    in_complete_sets                INTEGER,

    -- Kicks
    kicks                           INTEGER,
    kick_metres                     INTEGER,
    attacking_kicks                 INTEGER,
    long_kicks                      INTEGER,
    kicks_4020                      INTEGER,
    kicks_2040                      INTEGER,
    kicks_dead                      INTEGER,
    drop_outs                       INTEGER,
    forced_drop_outs                INTEGER,

    -- Defence
    tackles                         INTEGER,
    missed_tackles                  INTEGER,
    tackles_one_on_one              INTEGER,
    tackle_opp_half                 INTEGER,
    tackled_opp_20                  INTEGER,
    line_engagements                INTEGER,

    -- Discipline
    penalties_conceded              INTEGER,
    penalties_awarded               INTEGER,
    sin_bins                        INTEGER,
    send_offs                       INTEGER,
    set_restart_infringements_conceded INTEGER,
    set_restart_infringements_awarded  INTEGER,
    challenges                      INTEGER,
    correct_challenges              INTEGER,
    incorrect_challenges            INTEGER,

    -- General play
    play_the_balls                  INTEGER,
    general_play_pass               INTEGER,
    decoys                          INTEGER,
    supports                        INTEGER,
    options                         INTEGER,

    -- Goals / field goals
    goal_rate_str                   TEXT,    -- raw "4 from 6"
    goal_percentage                 REAL,
    field_goals                     INTEGER,
    field_goal_attempts             INTEGER,
    field_goal_misses               INTEGER,
    two_point_field_goals           INTEGER,

    -- Misc
    win_prediction_percentage       REAL,
    possession_time                 INTEGER,  -- milliseconds
    territory_time                  INTEGER,

    fetched_at                      TEXT     NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    raw_json                        TEXT,     -- full JSON blob for forward-compatibility

    UNIQUE (fox_match_id, team_side),
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

CREATE INDEX IF NOT EXISTS idx_match_team_stats_season_round
    ON match_team_stats (season, round_number);

CREATE INDEX IF NOT EXISTS idx_match_team_stats_match_id
    ON match_team_stats (match_id);
