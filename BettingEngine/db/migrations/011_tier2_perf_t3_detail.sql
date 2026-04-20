-- migration 011: add T3 sub-family detail columns to tier2_performance

ALTER TABLE tier2_performance ADD COLUMN t3_3a_delta         REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN t3_3b_delta         REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN t3_3c_home_delta    REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN t3_3c_away_delta    REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN t3_home_rest_days   INTEGER;
ALTER TABLE tier2_performance ADD COLUMN t3_away_rest_days   INTEGER;
ALTER TABLE tier2_performance ADD COLUMN t3_home_travel_km   REAL;
ALTER TABLE tier2_performance ADD COLUMN t3_away_travel_km   REAL;
