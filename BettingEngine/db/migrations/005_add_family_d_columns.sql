-- db/migrations/005_add_family_d_columns.sql
-- Family D: Kicking Pressure & Exit Stress  [soft launch — controlled trial]
--
-- fdo_pg   forced dropouts per game  (style: pin-pressure aggressor)
-- krm_pg   kick return metres per game  (vulnerability: low = poor exit quality)
--
-- Both are independent from all existing family stats.
-- No overlap with 2A (kick_metres_pg), 2B (lb/tb/mt/lbc), or 2C (run_metres/mt).

ALTER TABLE team_style_stats ADD COLUMN fdo_pg  REAL;
ALTER TABLE team_style_stats ADD COLUMN krm_pg  REAL;
