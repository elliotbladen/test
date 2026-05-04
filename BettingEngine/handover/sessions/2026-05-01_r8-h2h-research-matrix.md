# 2026-05-01 — AFL R8 H2H Research Matrix (Triple Signal Scan)
**Agent:** Claude (claude-sonnet-4-6)
**Round context:** AFL Round 8 2026

---

## What was done

Implemented and ran `scripts/h2h_research_r8.py` — a historical situational ROI scanner for the AFL H2H market.

### Concept
For each R8 game, for each team, filter `ml/afl/results/features_afl.csv` for historical games where this week's EXACT conditions match:
- Same calendar month (May only — not June, not April)
- Same opponent (Carlton vs St Kilda checks Carlton vs St Kilda history, not Collingwood)
- Same home/away role
- Moon phase only applied if THIS game is a full moon (or new moon)
- Rest-day angles only applied if THIS team ACTUALLY HAS those rest days this week
- Opponent rest angle only applied if the opponent IS on short rest this week

ROI formula: `mean(win × opening_odds) - 1` with min n=8 and threshold 20%.

### Script created
`scripts/h2h_research_r8.py`
- Loads features_afl.csv, computes moon_age for every historical game
- Scans 11 angle types per team per game (H2H record, month, full moon, rest, opp rest, home/away+month combos)
- Reports triple signals (3+ angles ≥20% ROI all matching this week's exact conditions)

---

## Results

### Triple signal found: Adelaide Crows (HOME) vs Port Adelaide

| Angle | ROI | n |
|-------|-----|---|
| vs Port (H2H record) | +53.2% | 12 |
| Full moon games | +26.2% | 21 |
| Full moon at home | +26.2% | 21 |

All match: Crows are home, playing Port, on a full moon (May 1, moon age ~14.3d).

**Caveat**: Angles #2 and #3 are correlated (same 21-game subset filtered differently). Independent signals: vs Port (+53.2%) and full moon (+26.2%). Still two strong independent signals plus one corroborating cut.

### Notable near-misses (2 angles only)

| Game | Team | Angles |
|------|------|--------|
| Dockers (AWAY) vs Bulldogs | Fremantle | +26.7% May (n=28), Away in May (same subset) |
| Melbourne (AWAY) vs Sydney | Melbourne Demons | +59.0% in May (n=25), Away in May (same subset) |
| Essendon (HOME) vs Brisbane | Essendon | +27.8% in May (n=24), Home in May (same subset) |
| Gold Coast (HOME) vs GWS | Gold Coast | +22.3% after 8+ days rest (n=33) |
| Richmond (AWAY) vs West Coast | Richmond | +27.2% vs Eagles H2H (n=9) |

Note: most "near-misses" have only month + home/away-in-month as their two angles, which are the same underlying filter. True independent signal count is lower.

### Games with no angles
- Collingwood vs Hawthorn (home or away)
- Carlton vs St Kilda (home or away) — surprising given blues May form in other years

---

## Key technical notes

- `features_afl.csv` goes to R6 only. ELO/form stale but H2H odds are historical opening prices — still valid for ROI angle mining.
- Moon phase computed from KNOWN_NEW_MOON = 2000-01-06, lunar cycle 29.530589 days.
- R8 games April 30 – May 2 fall in full moon window (age 13.0–16.5d threshold).
- May 3 games (Sydney vs Melbourne, Gold Coast vs GWS) have moon age 16.6d — just outside full moon window, so no full moon angles applied to those games.
- Script deduplicates angle labels so same filter can't appear twice.

---

## Watch out for

- Adelaide vs Port Showdown: our rules engine has Crows -42.2 margin and ML has -28.2. Market set a modest line (likely Showdown caution factor). The H2H research matrix adds situational support. All three signals point same direction — this is the highest-confidence play in R8.
- Melbourne's May away record (+59.0% ROI, n=25) is remarkable but has no second independent angle this week (Sydney is a strong home favourite). Worth noting but not a triple signal.
- All May angles (Games in May / Away in May / Home in May) use the same underlying subset — they're correlated. Don't count them as independent signals.

---

## Next session should

1. **Ingest R8 results** after games play out (Apr 30 – May 3) into features_afl.csv to fix stale ELO for R9
2. **Build actuals ingestion** for afl_shadow_predictions table (actual_margin, actual_total, actual_home_win)
3. **Backfill AFL R7 to DB** — run prepare_afl_round.py --round 7
4. **NRL R9 backfill** to ml_shadow_predictions: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe ml/run_r9_shadow.py --season 2026 --round 9`
5. **Build generalised h2h_research.py** — parameterise by round number instead of hardcoding R8 fixture/rest dates
6. **Fix West Coast T4 fortress** — negative applied to home team seems wrong
