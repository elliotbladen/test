-- migration 010: extend tier2_performance with T3–T6 adjustments, totals, and market prices

ALTER TABLE tier2_performance ADD COLUMN totals_T1          REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN totals_T2          REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN totals_T3          REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN totals_T4          REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN totals_T5          REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN totals_T6          REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN final_total        REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN pred_home_score    REAL;
ALTER TABLE tier2_performance ADD COLUMN pred_away_score    REAL;

-- T3 handicap deltas
ALTER TABLE tier2_performance ADD COLUMN t3_home_delta      REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN t3_away_delta      REAL    NOT NULL DEFAULT 0.0;

-- T4 venue
ALTER TABLE tier2_performance ADD COLUMN t4_handicap_delta  REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN t4_venue_name      TEXT;

-- T5 injury
ALTER TABLE tier2_performance ADD COLUMN t5_handicap_delta  REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN t5_home_injury_pts REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN t5_away_injury_pts REAL    NOT NULL DEFAULT 0.0;

-- T6 referee
ALTER TABLE tier2_performance ADD COLUMN t6_handicap_delta  REAL    NOT NULL DEFAULT 0.0;
ALTER TABLE tier2_performance ADD COLUMN t6_bucket          TEXT;
ALTER TABLE tier2_performance ADD COLUMN t6_referee_name    TEXT;

-- Fair market prices
ALTER TABLE tier2_performance ADD COLUMN fair_home_odds         REAL;
ALTER TABLE tier2_performance ADD COLUMN fair_away_odds         REAL;
ALTER TABLE tier2_performance ADD COLUMN home_win_probability   REAL;
ALTER TABLE tier2_performance ADD COLUMN fair_handicap_line     REAL;
ALTER TABLE tier2_performance ADD COLUMN fair_total_line        REAL;
