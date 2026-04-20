-- migration 014: add T7 columns to tier2_performance

ALTER TABLE tier2_performance ADD COLUMN totals_T7          REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN t7_condition_type  TEXT;
ALTER TABLE tier2_performance ADD COLUMN t7_dew_risk        INTEGER NOT NULL DEFAULT 0;
