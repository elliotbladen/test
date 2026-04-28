-- =============================================================================
-- 017_afl_foundation.sql
-- AFL support: teams, venues, umpires, team stats scaffold, match context ext.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- AFL Teams (18 teams, 2026 season)
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO teams (team_name, team_short_name, league, active_flag) VALUES
  ('Adelaide Crows',              'ADE', 'AFL', 1),
  ('Brisbane Lions',              'BRI', 'AFL', 1),
  ('Carlton Blues',               'CAR', 'AFL', 1),
  ('Collingwood Magpies',         'COL', 'AFL', 1),
  ('Essendon Bombers',            'ESS', 'AFL', 1),
  ('Fremantle Dockers',           'FRE', 'AFL', 1),
  ('Geelong Cats',                'GEE', 'AFL', 1),
  ('Gold Coast Suns',             'GCS', 'AFL', 1),
  ('Greater Western Sydney Giants','GWS', 'AFL', 1),
  ('Hawthorn Hawks',              'HAW', 'AFL', 1),
  ('Melbourne Demons',            'MEL', 'AFL', 1),
  ('North Melbourne Kangaroos',   'NME', 'AFL', 1),
  ('Port Adelaide Power',         'POR', 'AFL', 1),
  ('Richmond Tigers',             'RIC', 'AFL', 1),
  ('St Kilda Saints',             'STK', 'AFL', 1),
  ('Sydney Swans',                'SYD', 'AFL', 1),
  ('West Coast Eagles',           'WCE', 'AFL', 1),
  ('Western Bulldogs',            'WBD', 'AFL', 1);

-- ---------------------------------------------------------------------------
-- AFL Venues
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO venues (venue_name, city, state, country, surface_type, venue_notes) VALUES
  ('MCG',                    'Melbourne',   'VIC', 'Australia', 'grass',     'Melbourne Cricket Ground — 100k capacity. Home: Melbourne, Richmond'),
  ('Marvel Stadium',         'Melbourne',   'VIC', 'Australia', 'synthetic', 'Docklands roof stadium. Home: Carlton, Essendon, Western Bulldogs, St Kilda, North Melbourne'),
  ('Adelaide Oval',          'Adelaide',    'SA',  'Australia', 'grass',     'Home: Adelaide Crows, Port Adelaide'),
  ('Optus Stadium',          'Perth',       'WA',  'Australia', 'grass',     'Home: West Coast Eagles, Fremantle Dockers'),
  ('GMHBA Stadium',          'Geelong',     'VIC', 'Australia', 'grass',     'Home: Geelong Cats'),
  ('Gabba',                  'Brisbane',    'QLD', 'Australia', 'grass',     'Brisbane Lions primary home ground'),
  ('Engie Stadium',          'Sydney',      'NSW', 'Australia', 'grass',     'Home: GWS Giants (primary)'),
  ('SCG',                    'Sydney',      'NSW', 'Australia', 'grass',     'Sydney Cricket Ground — Home: Sydney Swans'),
  ('People First Stadium',   'Gold Coast',  'QLD', 'Australia', 'grass',     'Home: Gold Coast Suns'),
  ('UTAS Stadium',           'Launceston',  'TAS', 'Australia', 'grass',     'Hawthorn Tassie home games'),
  ('Blundestone Arena',      'Hobart',      'TAS', 'Australia', 'grass',     'Hawthorn Hobart games'),
  ('Norwood Oval',           'Adelaide',    'SA',  'Australia', 'grass',     'Adelaide secondary ground'),
  ('TIO Traeger Park',       'Alice Springs','NT', 'Australia', 'grass',     'Neutral venue — outback rounds'),
  ('Mars Stadium',           'Ballarat',    'VIC', 'Australia', 'grass',     'Western Bulldogs secondary ground'),
  ('University of Tasmania Stadium', 'Launceston', 'TAS', 'Australia', 'grass', 'UTAS — Hawthorn TAS base'),
  ('Cazalys Stadium',        'Cairns',      'QLD', 'Australia', 'grass',     'Neutral/Brisbane secondary');

-- ---------------------------------------------------------------------------
-- AFL Team Home Bases (for Tier 3 travel calculation)
-- Uses existing team_home_bases table structure
-- ---------------------------------------------------------------------------
-- Note: team_id values will be set after teams are inserted.
-- Run scripts/seed_afl_teams.py to populate team_home_bases with lat/lng.

-- ---------------------------------------------------------------------------
-- AFL Umpires — NOT USED
-- Tier 6 removed for AFL. 3 rotating field umpires with no reliable
-- public tracking data. Effect size too small to model systematically.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- afl_team_stats table
-- Mirrors NRL team_stats but with AFL-specific columns.
-- Stores per-team per-season snapshot used by Tier 1 and Tier 2.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS afl_team_stats (
    stat_id               INTEGER  PRIMARY KEY AUTOINCREMENT,
    team_id               INTEGER  NOT NULL,
    season                INTEGER  NOT NULL,
    as_of_date            DATE     NOT NULL,

    -- ELO
    elo_rating            REAL     NOT NULL DEFAULT 1500.0,

    -- Season record
    games_played          INTEGER  NOT NULL DEFAULT 0,
    wins                  INTEGER  NOT NULL DEFAULT 0,
    losses                INTEGER  NOT NULL DEFAULT 0,
    draws                 INTEGER  NOT NULL DEFAULT 0,
    win_pct               REAL,

    -- Scoring (AFL total points, not goals.behinds — engine works in pts)
    points_for            REAL,    -- avg points scored per game
    points_against        REAL,    -- avg points conceded per game
    points_diff           REAL,    -- avg differential per game

    -- Pythagorean
    pythagorean_win_pct   REAL,

    -- Attack / defence ratings (normalised, for Tier 1)
    attack_rating         REAL,    -- deviation from league avg scoring
    defence_rating        REAL,    -- deviation from league avg conceding

    -- Form
    recent_form_rating    REAL,    -- recent form score (-1 to +1)

    -- AFL-specific style stats (for Tier 2)
    contested_poss_pg     REAL,    -- contested possessions per game
    clearances_pg         REAL,    -- clearances per game
    inside_50s_pg         REAL,    -- inside 50s per game
    scoring_shots_pg      REAL,    -- scoring shots (goals + behinds) per game
    marks_inside_50_pg    REAL,    -- marks inside 50 per game
    intercept_poss_pg     REAL,    -- intercept possessions per game
    rebound_50s_pg        REAL,    -- rebound 50s per game
    goal_conversion_pct   REAL,    -- goals / scoring shots

    -- Prior season (for early-season blending)
    prior_season_points_for      REAL,
    prior_season_points_against  REAL,
    prior_season_pythagorean     REAL,
    prior_season_elo             REAL,

    -- Metadata
    data_source           TEXT,
    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (team_id) REFERENCES teams(team_id),
    UNIQUE (team_id, season, as_of_date)
);

-- ---------------------------------------------------------------------------
-- afl_match_context table
-- AFL-specific match context for Tier 3-8.
-- Mirrors NRL match_context but with AFL umpire fields.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS afl_match_context (
    context_id              INTEGER  PRIMARY KEY AUTOINCREMENT,
    match_id                INTEGER  NOT NULL UNIQUE,

    -- Tier 3: Rest / Travel
    home_rest_days          INTEGER,
    away_rest_days          INTEGER,
    home_travel_km          REAL,
    away_travel_km          REAL,

    -- Tier 4: Venue context
    is_neutral_venue        BOOLEAN  DEFAULT 0,

    -- Tier 5: Injuries (summary — detail in injury_reports)
    home_injury_pts         REAL     DEFAULT 0.0,
    away_injury_pts         REAL     DEFAULT 0.0,

    -- Tier 6: Umpire (AFL uses panel of 3 field umpires)
    umpire_panel            TEXT,    -- comma-separated names
    umpire_bucket           TEXT,    -- whistle_heavy | flow_heavy | neutral
    free_kick_rate          REAL,    -- avg free kicks per game for this panel
    advantage_rate          REAL,    -- avg advantages paid per game
    home_free_differential  REAL,    -- home team frees minus away (hist avg for panel)
    umpire_home_win_pct     REAL,    -- hist home win % for this umpire panel

    -- Tier 7: Emotional
    has_emotional_flags     BOOLEAN  DEFAULT 0,

    -- Tier 8: Weather
    precipitation_mm        REAL,
    wind_kmh                REAL,
    temp_c                  REAL,
    weather_condition       TEXT,    -- clear | rain | heavy_rain | wind

    -- Metadata
    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

-- ---------------------------------------------------------------------------
-- afl_umpire_stats table
-- Historical umpire performance stats (populated once data is sourced).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS afl_umpire_stats (
    stat_id             INTEGER  PRIMARY KEY AUTOINCREMENT,
    referee_id          INTEGER  NOT NULL,    -- references referees table
    season              INTEGER  NOT NULL,
    games_umpired       INTEGER  DEFAULT 0,
    free_kick_rate      REAL,                -- avg total frees per game
    advantage_rate      REAL,                -- avg advantages per game
    home_free_diff      REAL,                -- avg (home frees - away frees) per game
    home_win_pct        REAL,                -- home team win % in games umpired
    bucket              TEXT,                -- whistle_heavy | flow_heavy | neutral
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (referee_id) REFERENCES referees(referee_id),
    UNIQUE (referee_id, season)
);

-- ---------------------------------------------------------------------------
-- Schema migration record
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO schema_migrations (migration_name, applied_at)
VALUES ('017_afl_foundation', CURRENT_TIMESTAMP);
