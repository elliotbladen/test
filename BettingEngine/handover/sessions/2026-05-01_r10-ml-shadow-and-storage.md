# 2026-05-01 — R10 ML Shadow + DB Storage + Handover Setup
**Agent:** Claude (claude-sonnet-4-6)
**Round context:** NRL Round 10 2026

---

## What was done

### ML Shadow — Round 10
- Ran ML shadow engine for all 8 R10 games
- Output saved: `results/r10_ml_shadow_2026.txt`
- 8 rows written to new `ml_shadow_predictions` table in DB

### Model rebuild pipeline fixed
- Models were missing (gitignored .joblib files — known issue)
- Built `ml/rebuild_models.py` — self-contained script that trains all 3 XGBoost
  models (margin, total, h2h) directly from `ml/data/rlp_match_data.csv`
- No xlsx dependency. Run `python ml/rebuild_models.py` after any fresh checkout.
- Models saved as `ml/models/*_v20260501.joblib`
- Also writes `ml/data/game_log_referee.csv` (referee log, NOT gitignored)

### Shadow script improvements (`ml/run_r9_shadow.py`)
- Now accepts `--round N` for any round (was partly hardcoded to R9)
- Auto-detects latest model version (no more hardcoded `v20260419`)
- Auto-detects latest `team_stats` as_of_date from DB
- Writes output as UTF-8 (was crashing on Windows with Unicode chars)
- Now writes all predictions to `ml_shadow_predictions` DB table after each run

### DB — new table: `ml_shadow_predictions`
Stores per-game ML predictions every round with:
- ML raw + adjusted margin/total/h2h
- T2/T5/T7 adjustments applied
- Rules model values for comparison
- `agreement_flag`: 'strong' / 'direction' / 'disagree'
- Actuals columns (actual_margin, actual_total, actual_home_win) — NULL until
  results are entered. Need a results ingestion step each week.
- Error columns (ml_margin_error etc.) — computed once actuals are filled

### Handover folder
- Created `handover/` with `README.md` and `sessions/` subdirectory

---

## Current state

| Component | Status |
|-----------|--------|
| Rules engine (T1-T8) | Working. Data in `tier2_performance` |
| ML models | Rebuilt v20260501. In `ml/models/` (gitignored) |
| ML shadow script | Working for any round via `--round N` |
| ML predictions in DB | Working — R10 stored |
| Actual results ingestion | NOT BUILT. Actuals in `ml_shadow_predictions` are NULL |
| Agreement flag | Stored per-game: strong/direction/disagree |
| R9 shadow predictions | In txt file only — NOT backfilled to DB yet |

---

## Watch out for

- `ml/models/*.joblib` and `ml/data/game_log_referee.csv` are generated files.
  `game_log_referee.csv` is in `ml/data/` (NOT gitignored — safe).
  Models are gitignored — always run `rebuild_models.py` after fresh checkout.
- Shadow script is still named `run_r9_shadow.py` — misleading name but works
  for any round via `--round N`. Rename it to `run_shadow.py` when convenient.
- `model_runs` table exists but is still empty — was never wired up.
- `results` table in DB is empty for 2026. Actual scores not being auto-populated.
- RLP match data CSV only has NRL 2025 games through March 30 (32 games).
  Full 2025 season results are in the DB but not in the CSV. This means
  the 2025 test split during training is only 24 games — small but acceptable.
- Travel distance (T3) features are NaN in all historical training data.
  The model doesn't use them. R10 travel data exists in DB but travel effect
  is not being learned. Worth fixing in next model rebuild.

---

## Next session should

1. **Build actuals ingestion** — after each round, enter actual scores and
   trigger a function that fills `ml_shadow_predictions.actual_*` and computes
   errors. Same for `tier2_performance.actual_*`.
2. **Backfill R9** — run shadow script for R9 and store to DB
   (`python ml/run_r9_shadow.py --season 2026 --round 9`)
3. **Rename** `run_r9_shadow.py` → `run_shadow.py`
4. **Fix travel features** in `rebuild_models.py` — pull travel km from DB
   for 2009+ games where available
5. **End-of-season audit query** — write a SQL view or Python script that
   produces ML vs Rules vs Actual comparison across all rounds
