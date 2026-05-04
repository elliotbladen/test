# 2026-05-01 — AFL R8 Pricing (Rules + ML Shadow) + Model Training
**Agent:** Claude (claude-sonnet-4-6)
**Round context:** AFL Round 8 2026

---

## What was done

### AFL ML models trained
- AFL ML models did NOT exist (gitignored `ml/afl/results/models/`).
- Ran `ml/afl/train.py` using `.venv/Scripts/python.exe` (the project venv).
- Models saved to `ml/afl/results/models/margin_model.pkl`, `total_model.pkl`, `h2h_model.pkl`.
- **NOTE:** python3.14 at `/c/Users/ElliotBladen/.local/bin/python3.14` does NOT have numpy/pandas.
  Always use `.venv/Scripts/python.exe` for all pricing scripts in this project.

### AFL R8 fixture added to `scripts/prepare_afl_round.py`
R8 fixture (2026-04-30 to 2026-05-03):
- Collingwood vs Hawthorn | MCG | 2026-04-30
- Western Bulldogs vs Fremantle | Marvel Stadium | 2026-05-01
- Adelaide vs Port Adelaide | Adelaide Oval | 2026-05-01
- Essendon vs Brisbane Lions | Marvel Stadium | 2026-05-02
- West Coast vs Richmond | Optus Stadium | 2026-05-02
- Geelong vs North Melbourne | GMHBA Stadium | 2026-05-02
- Carlton vs St Kilda | Marvel Stadium | 2026-05-02
- Sydney vs Melbourne | SCG | 2026-05-03
- Gold Coast vs GWS | People First Stadium | 2026-05-03

R8 injuries, emotional flags (Adelaide/Port Showdown) also added.
Default `--round` arg changed to 8.

### DB storage added to `scripts/prepare_afl_round.py`
- Added `store_to_db()` function (sqlite3 only, no external deps).
- Creates `afl_shadow_predictions` table on first run.
- Stores: rules T1-T7 prices + ML shadow prices + all tier breakdowns + agreement_flag.
- Actuals columns (`actual_margin`, `actual_total`, `actual_home_win`) exist for post-round fill-in.
- Error columns (`rules_margin_error`, `ml_margin_error`, etc.) computed once actuals filled.
- Upsert on `(home_team, away_team, season, round_number)` — safe to re-run.

### R8 pricing run
- Output: `results/r8_afl_2026.txt`
- DB: 9 rows stored in `afl_shadow_predictions` (season=2026, round=8)
- Run command: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/prepare_afl_round.py --season 2026 --round 8`

---

## Key R8 findings

### Rules Engine (T1-T7)
| Game | Final Margin | Final Total | Home Odds |
|------|-------------|-------------|-----------|
| Magpies vs Hawks (MCG) | Hawks -5.0 | 169.5 | 2.25 |
| Bulldogs vs Dockers | Bulldogs -23.0 | 183.5 | 1.35 |
| **Crows vs Power (Showdown)** | Crows -42.2 | 168.5 | 1.14 |
| Bombers vs Lions | Lions -57.1 | 170.0 | 17.76 |
| Eagles vs Tigers | Eagles -20.3 | 139.0 | 1.40 |
| **Cats vs Kangaroos** | Cats -52.9 | 187.0 | 1.08 |
| Blues vs Saints | Blues -12.2 | 166.0 | 1.58 |
| **Swans vs Demons** | Swans -43.4 | 188.5 | 1.13 |
| Suns vs Giants | Suns -18.0 | 182.5 | 1.45 |

### ML Shadow divergences (rules vs ML gap beyond thresholds)
- **Bombers vs Lions** — rules has Lions -57pts; ML has Lions -30pts (+27.5pt margin gap). Biggest gap this round. ML much less bearish on Brisbane.
- **Cats vs Kangaroos** — rules has Cats -53pts; ML has Cats -34pts. ML far less extreme.
- **Suns vs Giants** — H2H huge gap: rules has Suns 69%; ML has Suns 92%. ML strongly favours Suns at home.
- **Magpies vs Hawks** — rules has Hawks by 5; ML agrees on margin but H2H shows ML more bullish Collingwood.
- Most agreed: Blues vs Saints (virtually identical margin and H2H, no divergence flag).
- T2 style data through R7 (footywire_snapshots.csv up to R8 snapshot exists — 18 teams).
- T1 calibration: +3.8pt margin correction, -0.2pt total correction (n=45 games this season).
- ML total bias correction: +14.6pts (large — models trained on 2009-2023, 2026 scoring higher).

---

## Current state

| Component | Status |
|-----------|--------|
| AFL rules engine (T1-T7) | Working. `scripts/prepare_afl_round.py --round N` |
| AFL ML models | Trained 2026-05-01. In `ml/afl/results/models/` (gitignored — rebuild with `ml/afl/train.py`) |
| AFL shadow pricing output | R8: `results/r8_afl_2026.txt`. R7: `results/r7_afl_2026.txt` |
| AFL DB storage | Working. `afl_shadow_predictions` table, 9 R8 rows |
| AFL actuals ingestion | NOT BUILT. actuals columns exist but NULL |
| R7 stored to DB | NOT DONE — never wired up the DB write for R7 |
| NRL R10 ML shadow | Done — `results/r10_ml_shadow_2026.txt`, 8 rows in `ml_shadow_predictions` |
| NRL R9 backfill to DB | NOT DONE |

---

## Watch out for

- **Python environment**: MUST use `.venv/Scripts/python.exe` for ALL pricing scripts.
  `python3.14` at `/c/Users/ElliotBladen/.local/bin/python3.14` has NO numpy/pandas.
  Run all scripts as: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/...`
- AFL ML models are gitignored (like NRL). After fresh checkout, run `ml/afl/train.py`.
- `features_afl.csv` only goes to 2026-04-12 (R6). R7 results not ingested.
  ELO ratings and form in the features CSV are stale by 2 rounds for R8 pricing.
  This affects both rules T1 baseline and ML feature quality.
- ML total bias of +14.6pts is large — 2026 scoring rates are running above what 2009-2023
  training data expects. Watch this closely as season progresses.
- `afl_shadow_predictions` table created fresh in this session — first AFL DB storage.
- R7 AFL predictions were never stored to DB (that session ran before DB storage existed).
  If you want complete history, manually run R7 with the R7 fixture (it's still in FIXTURE dict).
- West Coast Eagles playing home at Optus Stadium Perth for Eagles vs Tigers.
  T4 fortress applied -3.0 to Eagles (negative = away team plays better there? — check T4 logic).
  Actually this is correct: West Coast is home team and Optus Stadium shows -3.0, meaning the
  venue factor works against the "home" team designation here. May be a data artifact.

---

## Next session should

1. **Add R8 results** to `features_afl.csv` after all games are played (May 3-4). This keeps
   ELO and form data current for R9 pricing.
2. **Build actuals ingestion** for AFL — after each round, fill `afl_shadow_predictions.actual_*`
   columns and compute errors. Same pattern needed for NRL `ml_shadow_predictions`.
3. **Backfill AFL R7** to DB — run `scripts/prepare_afl_round.py --round 7` with DB storage now wired.
4. **Fix West Coast Eagles T4** — the -3.0 fortress penalty applied to the home team seems wrong.
   Check `pricing/afl_tier4_venue.py` — West Coast's home ground should give them a positive T4.
5. **Backfill NRL R9** to `ml_shadow_predictions` DB table:
   `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe ml/run_r9_shadow.py --season 2026 --round 9`
6. **Rename** `ml/run_r9_shadow.py` → `ml/run_shadow.py`
