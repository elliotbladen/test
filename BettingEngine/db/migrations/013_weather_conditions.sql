-- migration 013: weather_conditions — per-match weather snapshot and T7 delta

CREATE TABLE IF NOT EXISTS weather_conditions (
    match_id          INTEGER PRIMARY KEY REFERENCES matches(match_id),
    venue_id          INTEGER,
    kickoff_time      TEXT,          -- ISO local datetime, e.g. '2026-04-10T19:50:00'
    temp_c            REAL,
    dew_point_c       REAL,
    humidity_pct      REAL,
    wind_kmh          REAL,
    precipitation_mm  REAL,
    condition_type    TEXT,          -- 'clear', 'dew', 'light_rain', etc.
    dew_risk          INTEGER,       -- 0 or 1 (BOOLEAN)
    totals_delta      REAL,          -- T7 totals adjustment (≤ 0.0, capped at -6.0)
    data_source       TEXT,          -- 'open_meteo', 'metservice', 'mock_clear', 'manual'
    fetched_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);
