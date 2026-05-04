# 2026-05-03 11:02 AEST — Betmate Automation + Market Intelligence
**Agent:** Codex
**Round context:** NRL R10/R11 2026, AFL R8 2026, market intelligence research

---

## What was done

- Built Betmate-side import layer that reads already-collected Betmate files, not web scraping:
  - `betmate_ingest/common.py`
  - `betmate_ingest/reader.py`
  - `betmate_ingest/normalize.py`
  - `betmate_ingest/validation.py`
  - `betmate_ingest/pipeline.py`
  - `betmate_ingest/freshness.py`
  - `betmate_ingest/storage.py`
- Added automation/config/scripts:
  - `config/betmate_automation.yaml`
  - `scripts/betmate_import_round.py`
  - `scripts/price_from_betmate.py`
  - `scripts/betmate_auto_price.py`
  - `scripts/install_betmate_launchd.py`
  - `scripts/save_afl_market_intel_profiles.py`
- Betmate source root currently configured as:
  - `/Users/elliotbladen/betmate-web/public/data/nrl`
- Confirmed Betmate source files currently expected under:
  - `injuries-suspensions/latest/injuries-suspensions.json`
  - `referees/latest/referees.json`
  - `emotional-flags/latest/emotional-flags.json`
  - `historical-odds/latest/nrl.xlsx`
- Import writes engine inputs:
  - `data/import/injuries_r<round>.json`
  - `data/import/referees_r<round>.csv`
  - `data/import/emotional_r<round>.json`
  - staged audit folder under `data/import/betmate/r<round>_<season>/`
- Added freshness/preflight guard so pricing refuses to run when core data is stale or mismatched:
  - stale/missing Betmate manifests
  - referee manifest round mismatch
  - incomplete previous-round DB results
  - stale `team_stats`
  - stale `team_stats.elo_rating`
- Added Monday automation via launchd:
  - label `com.bettingmodel.betmate-auto-price`
  - plist `/Users/elliotbladen/Library/LaunchAgents/com.bettingmodel.betmate-auto-price.plist`
  - schedule Monday 19:03
  - command runs `scripts/betmate_auto_price.py --config config/betmate_automation.yaml`
  - confirmed loaded with `launchctl list`
- Added DB migration/storage for market intelligence:
  - `db/migrations/020_market_intelligence_storage.sql`
  - tables: `betmate_import_runs`, `betmate_preflight_checks`, `market_intel_profiles`, `market_intel_signals`
- Saved 81 AFL market-intel profiles into `market_intel_profiles`.
- Added docs:
  - `docs/betmate_ingest.md`

## Current state

- Existing pricing math was not changed. The new work changes collection/staging/preflight around the engine.
- Automated pricing is installed for Mondays at 19:03, but it should stop and report if required inputs are not current.
- Manual wrappers also run preflight unless `--skip-preflight` is passed.
- Latest observed preflight failures were expected and useful:
  - Betmate referees source was for round 9 while target engine round was later.
  - previous round DB results were incomplete.
  - `team_stats` / ELO were not current enough for target pricing.
- `market_intel_profiles` has historical AFL movement profiles stored.
- `market_intel_signals` is still empty. Live signal generation has not been built yet.
- General migration runner is blocked by older migration `009_injury_unique_constraint.sql`:
  - error: `table injury_reports_new has 11 columns but 12 values were supplied`
  - `020_market_intelligence_storage.sql` was applied directly and recorded in `schema_migrations`.

## Research/results captured this session

- NRL R10 saved prices exist in `results/r10_pricing_2026.csv`.
- AFL R8 saved totals exist in `results/r8_afl_2026.txt`.
- AFL historical totals/H2H movement research used:
  - `/Users/elliotbladen/Downloads/afl (7).xlsx`
- Key AFL total movement findings saved conceptually into profiles:
  - Fremantle total drift down -> under had strong historical ROI.
  - Collingwood / St Kilda / Melbourne also had useful drift-down under profiles, with weaker or mixed recent strength.
  - West Coast / North Melbourne total drift up -> over had useful recent ROI.
  - Brisbane total drift up -> over was stronger pre-recent than recent.
- Key AFL H2H movement findings from 2022+:
  - Western Bulldogs, Brisbane, Gold Coast, Sydney, Adelaide, Fremantle, Geelong firm often.
  - Best recent firm-and-bet ROIs were Collingwood, Fremantle, Port Adelaide, Hawthorn.
- Bookmaker market-intelligence note:
  - AFL/NRL should not assume Pinnacle is the sole leader.
  - Track Sportsbet, TAB, Ladbrokes/Neds, bet365, Betfair Exchange, and Pinnacle if available.
  - Sportsbet appears to be the largest Australian online bookmaker; Betfair is useful when liquid; TAB remains a local benchmark.
  - Pinnacle official API is not freely/publicly available as of current research; third-party odds APIs may be needed.

## Watch out for

- Do not treat Betmate import as a scraper. Betmate has already collected the source information; this repo only reads and normalizes it.
- Do not change the pricing-engine math without explicit instruction. The user specifically wants the maths preserved.
- The launchd plist lives outside the repo under `~/Library/LaunchAgents`; repo scripts/config document and recreate it.
- Current git status includes generated/import outputs and untracked automation files. Do not revert user work.
- `data/import/injuries_r10.json` and `data/import/referees_r10.csv` are modified from Betmate import tests.
- `.github/` is untracked and was not investigated in this handover.
- Referee JSON uses an `assignments` array; reader supports that shape.
- Team aliases added include:
  - `Cronulla Sutherland Sharks` -> `Cronulla-Sutherland Sharks`
  - `Manly Warringah Sea Eagles` -> `Manly-Warringah Sea Eagles`

## Next session should

1. Build live `market_intel_signals` generation from current bookmaker snapshots and stored `market_intel_profiles`.
2. Add daily bookmaker snapshot ingestion/storage if the user sets up the data source.
3. Fix migration `009_injury_unique_constraint.sql` so the normal migration runner works again.
4. Add an audit command that prints preflight state in plain English before Monday pricing.
5. Backfill/verify current `team_stats`, ELO, and previous-round results so automated Monday pricing can pass preflight.
