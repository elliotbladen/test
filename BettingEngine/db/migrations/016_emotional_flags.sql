-- Migration 016: create emotional_flags table (Tier 7 Emotional layer)
--
-- Stores per-match, per-team emotional/human-context factors that can
-- materially influence NRL game effort and performance.
--
-- Flag types:
--   milestone        - 100th/200th/300th game, debut, captain's first game
--   new_coach        - team's first game under a new head coach
--   star_return      - key player back from a long injury or suspension
--   shame_blowout    - team coming off a 30+ point loss (bounce-back game)
--   origin_boost     - players just returned from Origin camp, peak condition
--   farewell         - player or coach farewell game / final season
--   personal_tragedy - team rallying around personal adversity
--   rivalry_derby    - recognized derby or rivalry fixture
--   must_win         - win-or-bust finals-position game

CREATE TABLE IF NOT EXISTS emotional_flags (
    flag_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id      INTEGER NOT NULL REFERENCES matches(match_id),
    team_id       INTEGER NOT NULL REFERENCES teams(team_id),
    flag_type     TEXT    NOT NULL
                      CHECK (flag_type IN (
                          'milestone', 'new_coach', 'star_return',
                          'shame_blowout', 'origin_boost', 'farewell',
                          'personal_tragedy', 'rivalry_derby', 'must_win'
                      )),
    flag_strength TEXT    NOT NULL DEFAULT 'normal'
                      CHECK (flag_strength IN ('minor', 'normal', 'major')),
    player_name   TEXT,           -- NULL for team-level flags
    notes         TEXT,
    source_url    TEXT,
    captured_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_emotional_flags_match
    ON emotional_flags (match_id);

CREATE INDEX IF NOT EXISTS idx_emotional_flags_team
    ON emotional_flags (team_id, match_id);

-- Unique constraint to support INSERT ... ON CONFLICT DO UPDATE.
-- player_name uses COALESCE so team-level flags (NULL player) also deduplicate.
CREATE UNIQUE INDEX IF NOT EXISTS idx_emotional_flags_unique
    ON emotional_flags (match_id, team_id, flag_type, COALESCE(player_name, ''));
