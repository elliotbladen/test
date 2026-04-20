-- =============================================================================
-- Migration 001: Add Tier 2 yardage bucket columns to team_stats
-- =============================================================================
--
-- PURPOSE
-- -------
-- Adds the 7 nullable REAL columns needed by the Tier 2 yardage bucket signals
-- to the team_stats table. These columns are already present in the canonical
-- schema.sql definition. This migration brings existing databases up to date.
--
-- BEHAVIOUR ON RE-RUN
-- -------------------
-- The migration runner executes each statement independently and ignores
-- "duplicate column name" errors. Re-running against an already-migrated
-- database is safe and produces no changes.
--
-- FIELDS ADDED
-- ------------
-- Signal 1: run metres / post-contact metres
--   run_metres_pg           REAL   avg run metres per game this season
--   post_contact_metres_pg  REAL   avg post-contact metres per game (optional)
--
-- Signal 2: completion / errors / discipline
--   completion_rate         REAL   set completion rate (0.0–1.0)
--   errors_pg               REAL   unforced errors per game
--   penalties_pg            REAL   penalties conceded per game
--
-- Signal 3: kick metres
--   kick_metres_pg          REAL   avg kick metres per game
--
-- Signal 4: ruck speed (placeholder — NULL until data source is onboarded)
--   ruck_speed_score        REAL   composite ruck speed / PTB proxy score
--
-- =============================================================================

ALTER TABLE team_stats ADD COLUMN run_metres_pg          REAL;
ALTER TABLE team_stats ADD COLUMN post_contact_metres_pg REAL;
ALTER TABLE team_stats ADD COLUMN completion_rate        REAL;
ALTER TABLE team_stats ADD COLUMN errors_pg              REAL;
ALTER TABLE team_stats ADD COLUMN penalties_pg           REAL;
ALTER TABLE team_stats ADD COLUMN kick_metres_pg         REAL;
ALTER TABLE team_stats ADD COLUMN ruck_speed_score       REAL;
