-- =============================================================================
-- Migration 002: Add Family A (Territory & Control) columns to team_style_stats
-- =============================================================================
--
-- PURPOSE
-- -------
-- Adds the 4 nullable REAL columns needed by Tier 2 Family A to team_style_stats.
-- These columns are already present in the canonical schema.sql definition.
-- This migration brings existing databases up to date.
--
-- BEHAVIOUR ON RE-RUN
-- -------------------
-- The migration runner executes each statement independently and ignores
-- "duplicate column name" errors. Re-running against an already-migrated
-- database is safe and produces no changes.
--
-- FIELDS ADDED
-- ------------
-- Family A: Territory / Control
--   completion_rate  REAL   set completion rate as decimal (0.0–1.0)
--   kick_metres_pg   REAL   avg kick metres per game
--   errors_pg        REAL   unforced errors per game
--   penalties_pg     REAL   penalties conceded per game
--
-- =============================================================================

ALTER TABLE team_style_stats ADD COLUMN completion_rate  REAL;
ALTER TABLE team_style_stats ADD COLUMN kick_metres_pg   REAL;
ALTER TABLE team_style_stats ADD COLUMN errors_pg        REAL;
ALTER TABLE team_style_stats ADD COLUMN penalties_pg     REAL;
