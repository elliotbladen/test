# 2026-05-04 — BetMate Scraper Pipeline + BettingEngine Integration
**Agent:** Claude (claude-sonnet-4-6)
**Round context:** NRL Round 11 2026 (Magic Round, May 15–17)

---

## What was done

### Problem
BetMate only had a T2 style stats scraper. Fixtures, injuries, and referees were
manually created files (`data/import/injuries_rN.json`, `referees_rN.csv`).
BettingEngine had no concept of BetMate as an information hub.

### BetMate — new scrapers

#### `lib/scraper/nrl_fixture.py`
- Scrapes NRL.com draw API: `https://www.nrl.com/draw/data/?competition=111&season=YYYY&round=N`
- Outputs: `data/nrl/fixture/processed/latest-fixture.json`
- Fields: season, round, home_team, away_team, venue, kickoff_utc, kickoff_local
- Auto-detects round from `--round-one-monday` if `--round` not supplied

#### `lib/scraper/nrl_injuries.py`
- Scrapes Fox Sports NRL injury list page
- Outputs: `data/nrl/injuries/processed/latest-injuries.json`
- Format: same array structure as BettingEngine's `--injury-json` expects
- Includes `importance_tier` logic (elite/key/rotation) based on known player list + position

#### `lib/scraper/nrl_referees.py`
- Scrapes NRL.com draw page for referee appointments
- Tries Next.js JSON blob first, falls back to HTML text scan
- Outputs: `data/nrl/referees/processed/latest-referees.csv`
- Format: `home_team,away_team,referee` — same as `--referee-csv` expects
- Note: referees announced Tue/Wed — scraper returns 0 records on Monday (not an error)

#### `lib/scraper/nrl_round_prep.py`
- Orchestrator: runs fixture → injuries → referees in sequence
- Single entry point for the 6:05 PM scheduled task
- Flags if fixture returns 0 games (pricing will be blocked)
- 0 injury/referee records = warn only (both can legitimately be empty early week)

### Windows Scheduled Tasks installed

| Task | Time | Script |
|------|------|--------|
| BetMate NRL Style Stats Scrape | 6:00 PM Mon | `lib/scraper/nrl_style_stats.py` |
| BetMate NRL Round Prep | 6:05 PM Mon | `lib/scraper/nrl_round_prep.py` |
| BettingEngine NRL Pricing | 7:03 PM Mon | `scripts/prepare_round.py` |

All three tasks: Status=Ready, StartWhenAvailable=true.

### BettingEngine — `scripts/prepare_round.py` updated

1. **`_find_betmate_root()`** — finds BetMate at `../BetMate` (sibling dir) or `$BETMATE_ROOT` env var
2. **`betmate_latest_fixture/injuries/referees()`** — path helpers for each data file
3. **Step 0 — `step0_load_fixture_from_betmate()`** — runs before step 1:
   - Reads `latest-fixture.json` from BetMate
   - INSERT OR IGNORE each game into `matches` table if not already there
   - Looks up team IDs by name, venue IDs by name (fuzzy match)
4. **`--round 0`** — now default. Auto-detects round from BetMate fixture.
5. **Auto-resolve injuries/referees** — if `--injury-json`/`--referee-csv` not supplied, checks BetMate paths automatically.

### BetMate folder structure (nrl/)
```
data/nrl/
  fixture/
    raw/2026/round-N.json
    processed/2026/round-N-fixture.json
    processed/latest-fixture.json       ← BettingEngine reads this
    logs/scrape.log
  injuries/
    raw/2026/round-N.json
    processed/2026/round-N-injuries.json
    processed/latest-injuries.json      ← BettingEngine reads this
    logs/scrape.log
  referees/
    raw/2026/round-N.json
    processed/2026/round-N-referees.csv
    processed/latest-referees.csv       ← BettingEngine reads this
    logs/scrape.log
  style-stats/  (existing, unchanged)
  logs/round_prep.log
```

---

## R11 fixture (Magic Round) — verified working

Scraped successfully from NRL.com API. All 8 games at Suncorp Stadium.

| Home | Away | Kickoff AEST |
|------|------|--------------|
| Cronulla-Sutherland Sharks | Canterbury-Bankstown Bulldogs | Fri 15 May 18:00 |
| South Sydney Rabbitohs | Dolphins | Fri 15 May 20:00 |
| Wests Tigers | Manly-Warringah Sea Eagles | Sat 16 May 15:00 |
| Sydney Roosters | North Queensland Cowboys | Sat 16 May 17:30 |
| Parramatta Eels | Melbourne Storm | Sat 16 May 19:45 |
| Gold Coast Titans | Newcastle Knights | Sun 17 May 14:00 |
| New Zealand Warriors | Brisbane Broncos | Sun 17 May 16:05 |
| Penrith Panthers | St. George Illawarra Dragons | Sun 17 May 18:25 |

Note: Gold Coast Titans vs Canberra Raiders (R10 bye/reschedule?) not in R11 — only 8 games shown.

---

## Current state

| Component | Status |
|-----------|--------|
| BetMate fixture scraper | ✅ Working — NRL.com API |
| BetMate injuries scraper | ✅ Built — Fox Sports (parse quality depends on page structure) |
| BetMate referee scraper | ✅ Built — NRL.com draw page (announced Tue/Wed) |
| BetMate round prep orchestrator | ✅ Built |
| 6:05 PM scheduled task | ✅ Installed |
| 7:03 PM pricing task | ✅ Installed |
| prepare_round.py BetMate integration | ✅ Step 0 + auto-detect round + auto-resolve paths |
| R10 results in DB | ❌ Still NULL — step 1 will block pricing until entered |
| R11 fixtures in DB | ❌ Not yet — step 0 will load them at 7:03 PM from BetMate |
| Injury page parse quality | ⚠️ Needs real-world test — Fox Sports page structure may differ |
| Referee scraper | ⚠️ Needs real-world test after referees announced (usually Tue/Wed) |

---

## Watch out for

- **R10 results MUST be in DB before 7:03 PM pricing** — step 1 dies if any R10 game has NULL result.
  Enter them manually or build actuals ingestion before tonight.
- **Injury scraper parse** — Fox Sports injury list page may be JS-rendered or have changed structure.
  If `latest-injuries.json` is empty after 6:05 PM, manually check the page and populate the JSON.
- **Referee data** — won't be available until Tue/Wed. Check `latest-referees.csv` before pricing.
  If empty, pricing proceeds with T6=0 for all games (just a warning, not fatal).
- **Team name matching in step 0** — `canon()` in prepare_round.py handles most aliases.
  If a BetMate team name doesn't match, step 0 warns and skips that game (won't insert).
- **Magic Round venue** — all R11 games at Suncorp Stadium. "Suncorp Stadium" must exist in
  BettingEngine `venues` table for venue_id lookup in step 0 to work.

## Install scripts (for re-installation if needed)
```powershell
# BetMate round prep (6:05 PM)
powershell -ExecutionPolicy Bypass -File BetMate\scripts\install_nrl_round_prep_task.ps1

# BettingEngine pricing (7:03 PM)
powershell -ExecutionPolicy Bypass -File BettingEngine\scripts\install_nrl_pricing_task.ps1
```

---

## Next session should

1. **Enter R10 results** into DB so step 1 passes tonight
2. **Test the full pipeline** — run `nrl_round_prep.py` manually and check all three outputs
3. **Verify injury parse** — check `latest-injuries.json` contains real player data (not empty)
4. **Check Suncorp Stadium** exists in BettingEngine `venues` table (for step 0 venue lookup)
5. **Run pricing dry-run** before 7:03 PM: `python scripts/prepare_round.py --season 2026 --dry-run`
6. **Build actuals ingestion** — post-round, fill `results` table for R10 and trigger error computation
