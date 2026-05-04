# 2026-05-04 — R11 Pricing Readiness Fixes
**Agent:** Claude (claude-sonnet-4-6)
**Round context:** NRL Round 11 2026 (Magic Round, May 15–17)

---

## What was done

### Problem
Audit of `prepare_round.py` for tonight's 7:03 PM R11 pricing run revealed three blockers:
1. Missing R10 results in DB (all 8 games NULL — step 1 dies)
2. `step6_validate` treated missing referee as fatal error — R11 refs not announced until Tue/Wed
3. `team_style_stats` stale at 2026-03-24 — BetMate 6 PM scraper updates the CSV but no pipeline imported it into DB

### Fix 1 — step6_validate referee: warning not fatal

**File:** `scripts/prepare_round.py`

Changed:
```python
if not ref_ok:
    errors.append(f'{matchup}: no referee assignment')
```
To:
```python
if not ref_ok:
    warnings.append(f'{matchup}: no referee — T6=0.0 (refs typically announced Tue/Wed)')
```

Result: missing referees are now a warning. Pricing proceeds with T6=0 for all games.
Consistent with how missing injuries are handled (`--strict-injuries` off).

### Fix 2 — step0b: style stats import from BetMate

**File:** `scripts/prepare_round.py`

Added `step0b_import_style_stats(conn, season, dry_run)` function and wired it into
`main()` right after step0 (fixture load).

Reads `data/nrl/style-stats/processed/latest-style-stats.csv` from BetMate.
Maps CSV columns to DB columns:
- `line_breaks_pg` → `lb_pg`
- `tackle_breaks_pg` → `tb_pg`
- `missed_tackles_pg` → `mt_pg`
- `line_breaks_conceded_pg` → `lbc_pg`
- `completion_rate`, `kick_metres_pg`, `errors_pg`, `penalties_pg`, `run_metres_pg` → same name
- `forced_dropouts_pg` → `fdo_pg`
- `kick_return_metres_pg` → `krm_pg`

UPSERTs by (team_id, season, as_of_date). BetMate latest-style-stats.csv is from
Round 10 (as_of_date=2026-04-30) which is current and will update stale 2026-03-24 rows.

### Created: scripts/load_results.py + data/import/r10_results_2026.csv

**Blocker still outstanding:** R10 results must be entered before 7:03 PM.

- `data/import/r10_results_2026.csv` — template with match_ids pre-filled
- `scripts/load_results.py` — reads CSV, upserts into `results` table

**User must:**
1. Fill in `home_score` and `away_score` columns in `r10_results_2026.csv`
2. Run: `python scripts/load_results.py data/import/r10_results_2026.csv --dry-run` (verify)
3. Run: `python scripts/load_results.py data/import/r10_results_2026.csv` (write)

R10 match IDs and matchups:
| ID  | Date       | Home                             | Away                          |
|-----|------------|----------------------------------|-------------------------------|
| 278 | 2026-05-01 | Canterbury-Bankstown Bulldogs    | North Queensland Cowboys      |
| 279 | 2026-05-01 | Dolphins                         | Melbourne Storm               |
| 280 | 2026-05-02 | Gold Coast Titans                | Canberra Raiders              |
| 281 | 2026-05-02 | Parramatta Eels                  | New Zealand Warriors          |
| 282 | 2026-05-02 | Sydney Roosters                  | Brisbane Broncos              |
| 283 | 2026-05-03 | Newcastle Knights                | South Sydney Rabbitohs        |
| 284 | 2026-05-03 | Cronulla-Sutherland Sharks       | Wests Tigers                  |
| 285 | 2026-05-03 | Penrith Panthers                 | Manly-Warringah Sea Eagles    |

---

## Current state for tonight's 7:03 PM run

| Check | Status |
|-------|--------|
| R11 fixture in BetMate | ✅ 8 games at Suncorp Stadium |
| Step 0 fixture load | ✅ Will insert R11 matches from BetMate |
| Step 0b style stats import | ✅ Will update from R10 CSV (as_of 2026-04-30) |
| R10 results in DB | ❌ USER MUST ENTER BEFORE 7:03 PM |
| Step 6 referee validation | ✅ Fixed — now warning only, T6=0 if no refs |
| Suncorp Stadium venue | ✅ venue_id=18, lat/lng present |
| team_stats 2026 | ✅ 17 teams (will be updated at step 2) |
| ELO | ✅ Snapshot exists (will roll forward in step 3) |
| Weather (T8) | ✅ step 6a fetches via Open-Meteo |
| Injuries (T5) | ⚠️ BetMate injuries scraper present; quality unknown |
| Referees (T6) | ⚠️ Not announced yet — T6=0 acceptable (warning only now) |

---

## Action before 7:03 PM

**CRITICAL:** Fill in R10 scores and run:
```powershell
# Edit the CSV first:
notepad BettingEngine\data\import\r10_results_2026.csv

# Dry-run to verify:
& .\.venv\Scripts\python.exe scripts\load_results.py data\import\r10_results_2026.csv --dry-run

# Write:
& .\.venv\Scripts\python.exe scripts\load_results.py data\import\r10_results_2026.csv
```

Then optionally test the full pipeline:
```powershell
& .\.venv\Scripts\python.exe scripts\prepare_round.py --season 2026 --dry-run
```

---

## Next session should

1. **Check tier2_performance** after run — were T2 signals firing correctly for Magic Round?
2. **Verify style stats** were updated to 2026-04-30 from step 0b output
3. **Add a results scraper** — automated way to pull NRL final scores post-round so step 1 doesn't block
4. **Check injury scraper quality** — was latest-injuries.json populated by 6 PM?
5. **Build referee scraper test** — check latest-referees.csv after Tuesday announcement
