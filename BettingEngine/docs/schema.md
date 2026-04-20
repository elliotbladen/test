# Database Schema Specification - V1

## Purpose

This document defines the core relational schema for the V1 NRL pricing engine.

The schema is designed to support:

- ingestion
- normalization
- historical storage
- market snapshot tracking
- model versioning
- tier-by-tier adjustment logging
- signal generation
- actual bet logging
- bankroll history

The schema should work in SQLite first and scale to PostgreSQL later.

---

## Design Rules

### Rule 1
Each match must have one canonical `match_id`.

### Rule 2
Market prices are append-only.
New snapshots are added, not overwritten.

### Rule 3
Every model run must store `model_version`.

### Rule 4
Every signal must trace back to:
- the match
- the market snapshot
- the model run

### Rule 5
Every actual bet must trace back to a signal.

### Rule 6
Baseline outputs and adjustment outputs must both be stored.

---

## Core Tables

## 1. teams

Stores canonical teams.

### Fields
- `team_id` INTEGER PRIMARY KEY
- `team_name` TEXT NOT NULL
- `team_short_name` TEXT
- `league` TEXT NOT NULL
- `active_flag` BOOLEAN DEFAULT 1
- `created_at` DATETIME
- `updated_at` DATETIME

---

## 2. venues

Stores canonical venues.

### Fields
- `venue_id` INTEGER PRIMARY KEY
- `venue_name` TEXT NOT NULL
- `city` TEXT
- `state` TEXT
- `country` TEXT
- `home_team_id` INTEGER NULL
- `surface_type` TEXT NULL
- `venue_notes` TEXT NULL
- `created_at` DATETIME
- `updated_at` DATETIME

### Foreign keys
- `home_team_id -> teams.team_id`

---

## 3. referees

Stores referee identities for Tier 6.

### Fields
- `referee_id` INTEGER PRIMARY KEY
- `referee_name` TEXT NOT NULL
- `active_flag` BOOLEAN DEFAULT 1
- `created_at` DATETIME
- `updated_at` DATETIME

---

## 4. matches

Canonical match table.

### Fields
- `match_id` INTEGER PRIMARY KEY
- `sport` TEXT NOT NULL
- `competition` TEXT NOT NULL
- `season` INTEGER NOT NULL
- `round_number` INTEGER NULL
- `match_date` DATE NOT NULL
- `kickoff_datetime` DATETIME NOT NULL
- `home_team_id` INTEGER NOT NULL
- `away_team_id` INTEGER NOT NULL
- `venue_id` INTEGER NOT NULL
- `status` TEXT NOT NULL
- `referee_id` INTEGER NULL
- `source_match_key` TEXT NULL
- `created_at` DATETIME
- `updated_at` DATETIME

### Foreign keys
- `home_team_id -> teams.team_id`
- `away_team_id -> teams.team_id`
- `venue_id -> venues.venue_id`
- `referee_id -> referees.referee_id`

---

## 5. bookmakers

Stores bookmaker identities.

### Fields
- `bookmaker_id` INTEGER PRIMARY KEY
- `bookmaker_name` TEXT NOT NULL
- `bookmaker_code` TEXT NOT NULL
- `priority_rank` INTEGER
- `created_at` DATETIME

### Examples
- Bet365
- Pinnacle

---

## 6. market_snapshots

Stores bookmaker market data at specific timestamps.

### Fields
- `snapshot_id` INTEGER PRIMARY KEY
- `match_id` INTEGER NOT NULL
- `bookmaker_id` INTEGER NOT NULL
- `captured_at` DATETIME NOT NULL
- `market_type` TEXT NOT NULL
- `selection_name` TEXT NOT NULL
- `line_value` REAL NULL
- `odds_decimal` REAL NOT NULL
- `is_opening` BOOLEAN DEFAULT 0
- `is_closing` BOOLEAN DEFAULT 0
- `source_url` TEXT NULL
- `source_method` TEXT NOT NULL
- `created_at` DATETIME

### Market type values
- `h2h`
- `handicap`
- `total`

### Selection examples
- `home`
- `away`
- `over`
- `under`

### Notes
This table stores:
- line history
- opening prices
- current prices
- closing prices
- multi-bookmaker snapshots

### Foreign keys
- `match_id -> matches.match_id`
- `bookmaker_id -> bookmakers.bookmaker_id`

---

## 7. results

Stores final match outcomes.

### Fields
- `result_id` INTEGER PRIMARY KEY
- `match_id` INTEGER NOT NULL
- `home_score` INTEGER NOT NULL
- `away_score` INTEGER NOT NULL
- `total_score` INTEGER NOT NULL
- `margin` INTEGER NOT NULL
- `winning_team_id` INTEGER NULL
- `result_status` TEXT NOT NULL
- `captured_at` DATETIME
- `created_at` DATETIME

### Foreign keys
- `match_id -> matches.match_id`
- `winning_team_id -> teams.team_id`

---

## 8. team_stats

Stores derived team-level baseline stats.

### Fields
- `team_stat_id` INTEGER PRIMARY KEY
- `team_id` INTEGER NOT NULL
- `season` INTEGER NOT NULL
- `as_of_date` DATE NOT NULL
- `games_played` INTEGER
- `points_for_avg` REAL
- `points_against_avg` REAL
- `home_points_for_avg` REAL
- `home_points_against_avg` REAL
- `away_points_for_avg` REAL
- `away_points_against_avg` REAL
- `elo_rating` REAL
- `attack_rating` REAL
- `defence_rating` REAL
- `recent_form_rating` REAL
- `created_at` DATETIME

### Foreign keys
- `team_id -> teams.team_id`

---

## 9. match_context

Stores contextual variables for Tiers 3 to 7.

### Fields
- `context_id` INTEGER PRIMARY KEY
- `match_id` INTEGER NOT NULL
- `home_rest_days` INTEGER NULL
- `away_rest_days` INTEGER NULL
- `home_off_bye` BOOLEAN DEFAULT 0
- `away_off_bye` BOOLEAN DEFAULT 0
- `home_travel_km` REAL NULL
- `away_travel_km` REAL NULL
- `weather_rain_flag` BOOLEAN DEFAULT 0
- `weather_wind_kph` REAL NULL
- `weather_temp_c` REAL NULL
- `weather_humidity_pct` REAL NULL
- `weather_summary` TEXT NULL
- `full_moon_flag` BOOLEAN DEFAULT 0
- `new_moon_flag` BOOLEAN DEFAULT 0
- `moon_window_plus_minus_one_day` BOOLEAN DEFAULT 0
- `home_key_injuries_count` INTEGER NULL
- `away_key_injuries_count` INTEGER NULL
- `home_spine_injuries_count` INTEGER NULL
- `away_spine_injuries_count` INTEGER NULL
- `venue_fortress_flag_home` BOOLEAN NULL
- `created_at` DATETIME
- `updated_at` DATETIME

### Notes
Moon fields are included to support Tier 7 experimental lunar logic.

### Foreign keys
- `match_id -> matches.match_id`

---

## 10. injury_reports

Optional but recommended in V1 if available.

### Fields
- `injury_report_id` INTEGER PRIMARY KEY
- `match_id` INTEGER NOT NULL
- `team_id` INTEGER NOT NULL
- `player_name` TEXT NOT NULL
- `player_role` TEXT NULL
- `importance_tier` TEXT NULL
- `status` TEXT NOT NULL
- `notes` TEXT NULL
- `source_url` TEXT NULL
- `captured_at` DATETIME
- `created_at` DATETIME

### Foreign keys
- `match_id -> matches.match_id`
- `team_id -> teams.team_id`

---

## 11. model_runs

Stores one full pricing run for one match.

### Fields
- `model_run_id` INTEGER PRIMARY KEY
- `match_id` INTEGER NOT NULL
- `run_timestamp` DATETIME NOT NULL
- `model_version` TEXT NOT NULL
- `baseline_home_points` REAL NOT NULL
- `baseline_away_points` REAL NOT NULL
- `baseline_margin` REAL NOT NULL
- `baseline_total` REAL NOT NULL
- `final_home_points` REAL NOT NULL
- `final_away_points` REAL NOT NULL
- `final_margin` REAL NOT NULL
- `final_total` REAL NOT NULL
- `home_win_probability` REAL NOT NULL
- `away_win_probability` REAL NOT NULL
- `fair_home_odds` REAL NOT NULL
- `fair_away_odds` REAL NOT NULL
- `fair_handicap_line` REAL NOT NULL
- `fair_total_line` REAL NOT NULL
- `run_status` TEXT NOT NULL
- `notes` TEXT NULL
- `created_at` DATETIME

### Foreign keys
- `match_id -> matches.match_id`

---

## 12. model_adjustments

Stores each adjustment applied during a model run.

### Fields
- `adjustment_id` INTEGER PRIMARY KEY
- `model_run_id` INTEGER NOT NULL
- `tier_number` INTEGER NOT NULL
- `tier_name` TEXT NOT NULL
- `adjustment_code` TEXT NOT NULL
- `adjustment_description` TEXT NOT NULL
- `home_points_delta` REAL DEFAULT 0
- `away_points_delta` REAL DEFAULT 0
- `margin_delta` REAL DEFAULT 0
- `total_delta` REAL DEFAULT 0
- `applied_flag` BOOLEAN DEFAULT 1
- `created_at` DATETIME

### Example
- Tier 7
- `moon_full_home_boost`
- `Full moon +/-1 day home crowd intensity adjustment`

### Foreign keys
- `model_run_id -> model_runs.model_run_id`

---

## 13. signals

Stores model-generated betting recommendations.

### Fields
- `signal_id` INTEGER PRIMARY KEY
- `model_run_id` INTEGER NOT NULL
- `match_id` INTEGER NOT NULL
- `bookmaker_id` INTEGER NOT NULL
- `market_type` TEXT NOT NULL
- `selection_name` TEXT NOT NULL
- `line_value` REAL NULL
- `market_odds` REAL NOT NULL
- `model_odds` REAL NULL
- `model_probability` REAL NOT NULL
- `ev_value` REAL NOT NULL
- `ev_percent` REAL NOT NULL
- `raw_kelly_fraction` REAL NOT NULL
- `applied_kelly_fraction` REAL NOT NULL
- `capped_stake_fraction` REAL NOT NULL
- `recommended_stake_amount` REAL NOT NULL
- `confidence_level` TEXT NOT NULL
- `signal_label` TEXT NOT NULL
- `veto_flag` BOOLEAN DEFAULT 0
- `veto_reason` TEXT NULL
- `created_at` DATETIME

### Foreign keys
- `model_run_id -> model_runs.model_run_id`
- `match_id -> matches.match_id`
- `bookmaker_id -> bookmakers.bookmaker_id`

---

## 14. bets

Stores actual user actions, separate from recommendations.

### Fields
- `bet_id` INTEGER PRIMARY KEY
- `signal_id` INTEGER NOT NULL
- `placed_flag` BOOLEAN DEFAULT 0
- `placed_timestamp` DATETIME NULL
- `bookmaker_id` INTEGER NOT NULL
- `stake_amount` REAL NOT NULL
- `odds_taken` REAL NOT NULL
- `line_taken` REAL NULL
- `result` TEXT NULL
- `pnl_amount` REAL NULL
- `closing_odds` REAL NULL
- `clv_value` REAL NULL
- `notes` TEXT NULL
- `created_at` DATETIME
- `updated_at` DATETIME

### Foreign keys
- `signal_id -> signals.signal_id`
- `bookmaker_id -> bookmakers.bookmaker_id`

---

## 15. bankroll_log

Stores bankroll state over time.

### Fields
- `bankroll_log_id` INTEGER PRIMARY KEY
- `log_timestamp` DATETIME NOT NULL
- `starting_bankroll` REAL NOT NULL
- `ending_bankroll` REAL NOT NULL
- `open_exposure` REAL DEFAULT 0
- `closed_pnl` REAL DEFAULT 0
- `notes` TEXT NULL
- `created_at` DATETIME

---

## Relationship Summary

### Core chain
- `matches` -> `market_snapshots`
- `matches` -> `results`
- `matches` -> `match_context`
- `matches` -> `model_runs`
- `model_runs` -> `model_adjustments`
- `model_runs` -> `signals`
- `signals` -> `bets`

This chain preserves traceability from:
raw market -> model run -> signal -> actual bet -> settlement

---

## Required Indexing Priorities

When implementing, prioritize indexes on:

- `matches.season`
- `matches.match_date`
- `market_snapshots.match_id`
- `market_snapshots.bookmaker_id`
- `market_snapshots.captured_at`
- `model_runs.match_id`
- `signals.match_id`
- `signals.bookmaker_id`
- `bets.signal_id`

These will matter quickly.

---

## V1 Minimal Required Tables

If implementation must start lean, the minimum set is:

- teams
- venues
- referees
- matches
- bookmakers
- market_snapshots
- results
- team_stats
- match_context
- model_runs
- model_adjustments
- signals
- bets
- bankroll_log

---

## Future Schema Expansion

Later versions may add:

- player master table
- player ratings
- coach table
- style/archetype table
- weather source snapshots
- exchange order book table
- live event states
- model experiment registry
- multi-sport shared entities

Version 1 should focus on keeping the current schema stable and auditable.