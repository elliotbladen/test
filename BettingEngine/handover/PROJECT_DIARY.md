# Project Diary — BettingEngine + BetMate
Last updated: 2026-05-04

One doc. Everything built. Newest at the top.

---

## 2026-05-04 — AFL Tab Fix + New Machine Setup Protocol

### Root cause — this cost a full session to debug, don't repeat it

**Symptom**: AFL tab showed "No games available." NRL worked fine.

**Cause 1 — `.env.local` not in GitHub**
`.env.local` is gitignored (correct — it has secrets). But this means any fresh `git pull` on a new machine produces a broken app. The odds API routes return 500 "ODDS_API_KEY not configured." Without the key, NOTHING loads.

**Cause 2 — header sport tabs were cosmetic**
The NRL/AFL pills in the header had no `onClick`. Clicking AFL in the header did nothing. The working tabs were inside the page body. Users clicked the header, nothing happened, and assumed AFL was gone.

**Cause 3 — `useState` doesn't react to URL changes**
When I wired the header tabs to use URL params (`/odds?sport=AFL`), clicking them changed the URL but `activeSport` state didn't update because `useState(initialValue)` only reads the initial value once. Fixed by adding a `useEffect` that watches `searchParams` and calls `setActiveSport` on every URL change.

### What was fixed
- `Header.tsx` — NRL/AFL tabs now navigate to `/odds?sport=NRL|AFL` (real links)
- `Header.tsx` — hamburger menu added for mobile (Research was also invisible on mobile)
- `app/odds/page.tsx` — `useEffect([searchParams])` syncs `activeSport` with URL
- `.env.local.example` — fixed wrong key name (`NEXT_PUBLIC_ODDS_API_KEY` → `ODDS_API_KEY`)

### NEW MACHINE SETUP — do this EVERY time you pull to a new computer

> **This is the step you keep forgetting. Do it before anything else.**

1. Copy `.env.local.example` → `.env.local`
2. Fill in values:
   ```
   ODDS_API_KEY=29cffda625d3420dc24db352a076a5db
   NEXT_PUBLIC_SUPABASE_URL=<your supabase url>
   NEXT_PUBLIC_SUPABASE_ANON_KEY=<your supabase anon key>
   ```
3. `npm install`
4. `npm run dev`

Without step 2, the app starts but ALL odds show errors or empty. This is not a code bug — it is always a missing `.env.local`.

### Key file: `BetMate/.env.local.example`
Always keep this file up to date. Every new env var added to the app must also be added to `.env.local.example` so a fresh pull is not broken.

---

## 2026-05-04 — Mobile Nav Fix

### BetMate — Header hamburger menu
- **Problem**: `nav` was `hidden sm:flex` — no way to reach Research (or any page) on mobile or narrow windows
- **Fix**: Added hamburger button (visible mobile-only, `sm:hidden`) that toggles a full-width drawer below the header
- Drawer shows all three nav links (Odds / Tools / Research) with active state in green
- Drawer auto-closes on route change (`useEffect` on `pathname`)
- Desktop layout unchanged

---

## 2026-05-04 — R11 Pricing Readiness + BetMate UI + Odds Snapshot

### BettingEngine
- **Referee validation fixed** — `step6_validate` now treats missing referee as warning (T6=0), not fatal error. Refs not announced until Tue/Wed so Monday 7:03 PM run was dying.
- **Style stats auto-import** — `step0b_import_style_stats()` added to `prepare_round.py`. Runs at every pricing call. Reads BetMate's `latest-style-stats.csv`, UPSERTs into `team_style_stats`.
- **Results loader** — `scripts/load_results.py` + `data/import/r10_results_2026.csv` template. CSV-to-DB results ingestion for manual score entry.
- **AI manager agent** — discussed, decided against for now. Scheduled tasks + human review is the right V1 approach.

### BetMate — UI Redesign
- RacingZone-inspired: black/white/green premium feel
- Header: solid green `border-b-2` line, two-tone logo (Bet white / Mate green), green underline nav active states
- Cards: `#111111` on `#0D0D0D` page — visibly lifted. Borders `#252525`.
- Market tabs: underline indicator (not filled background)
- Muted text tightened: `#5C5C5C` not `#888`

### BetMate — Daily Odds Snapshot
- `lib/scraper/odds_snapshot.py` — pulls NRL + AFL from The Odds API daily
- Saves to `data/odds_snapshots/YYYY/YYYY-MM-DD.csv`
- 716 rows per day — every game × bookmaker × market × outcome
- Windows Task: daily 9:00 AM — **installed and running**
- Purpose: end-of-year study — line movement, bookmaker quality, EV validation

---

## 2026-05-04 — BetMate Scraper Pipeline

### BetMate — new scrapers
- `lib/scraper/nrl_fixture.py` — NRL.com draw API, outputs `latest-fixture.json`
- `lib/scraper/nrl_injuries.py` — Fox Sports injury list, outputs `latest-injuries.json`
- `lib/scraper/nrl_referees.py` — NRL.com draw page for referee appointments
- `lib/scraper/nrl_round_prep.py` — orchestrator, runs all three in sequence
- `lib/scraper/nrl_historical_results.py` — Playwright scraper for aussportsbetting.com xlsx

### BetMate — Windows Tasks installed
| Task | Time |
|------|------|
| BetMate NRL Historical Results | Mon 5:00 PM |
| BetMate NRL Style Stats Scrape | Mon 6:00 PM |
| BetMate NRL Round Prep | Mon 6:05 PM |
| BettingEngine NRL Pricing | Mon 7:03 PM |

### BettingEngine — prepare_round.py updated
- `_find_betmate_root()` — locates BetMate at `../BetMate`
- `step0_load_fixture_from_betmate()` — inserts R{N} fixtures from BetMate JSON
- `--round 0` default — auto-detects from BetMate fixture
- Auto-resolves injury + referee paths from BetMate if not supplied

### R11 fixture scraped
- 8 games, Magic Round, all Suncorp Stadium, May 15–17

---

## 2026-05-03 — Market Snapshots + Actual Bets Ledger

- BetMate market snapshot infrastructure built
- Actual bets ledger created for tracking real wagers
- NRL + AFL market intel pages

---

## 2026-05-01 — R8 Full Pricing + AFL Models + ML Shadow

### BettingEngine
- R8 full pricing run — NRL + AFL
- H2H, handicap, totals research matrices for R8
- AFL pricing engine built — `scripts/prepare_afl_round.py`
- AFL T1–T8 model adapted from NRL engine
- ML shadow model — parallel predictions stored in `results/`
- `ml/rebuild_models.py` — retrain on historical data

---

## System Overview (current state 2026-05-04)

### What runs automatically
| When | What | Output |
|------|------|--------|
| Daily 9:00 AM | BetMate odds snapshot | `data/odds_snapshots/YYYY/YYYY-MM-DD.csv` |
| Mon 5:00 PM | NRL historical results download | `data/nrl/historical/latest.xlsx` |
| Mon 6:00 PM | NRL style stats scrape | `data/nrl/style-stats/processed/latest-style-stats.csv` |
| Mon 6:05 PM | NRL round prep (fixture + injuries + referees) | `data/nrl/*/processed/latest-*.json/csv` |
| Mon 7:03 PM | BettingEngine NRL pricing | Terminal output + DB |

### What still needs human input each week
| Task | When | How |
|------|------|-----|
| Enter previous round results | Monday before 7:03 PM | Fill `data/import/rN_results_2026.csv`, run `scripts/load_results.py` |
| Check injury scraper quality | Monday evening | Verify `latest-injuries.json` has real players |
| Check referee assignments | Tuesday/Wednesday | Re-run pricing after refs announced |
| Review pricing output | Monday 7:03 PM | Inspect terminal output before acting |

### Key file locations
| Data | Path |
|------|------|
| NRL fixture | `BetMate/data/nrl/fixture/processed/latest-fixture.json` |
| NRL injuries | `BetMate/data/nrl/injuries/processed/latest-injuries.json` |
| NRL referees | `BetMate/data/nrl/referees/processed/latest-referees.csv` |
| NRL historical xlsx | `BetMate/data/nrl/historical/latest.xlsx` |
| Style stats | `BetMate/data/nrl/style-stats/processed/latest-style-stats.csv` |
| Daily odds CSV | `BetMate/data/odds_snapshots/YYYY/YYYY-MM-DD.csv` |
| BettingEngine DB | `BettingEngine/data/betting.db` |
| Pricing entry point | `BettingEngine/scripts/prepare_round.py` |

### Repos
- `BettingEngine` — Python pricing engine, SQLite DB, 8-tier model
- `BetMate` — Next.js web app, Python scrapers, data hub for BettingEngine
- Both pushed to GitHub: `elliotbladen/BettingEngine` + `elliotbladen/test` (BetMate)

---

## Pending / Known Issues

- **R10 results** — still NULL in DB. Must be entered before next pricing run.
- **Injury scraper quality** — Fox Sports parse untested on real round. Check `latest-injuries.json` after Monday 6:05 PM.
- **Referee scraper** — returns 0 records until Tue/Wed. Normal. Re-run pricing Wednesday.
- **Style stats stale in DB** — step0b will fix this at next 7:03 PM run.
- **BetMate UI** — changes deployed, browser hard refresh needed (`Ctrl+Shift+R`).
- **AFL pricing** — engine built but not wired into the Monday pipeline yet.
