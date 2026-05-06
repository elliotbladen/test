# BetMate — Claude Context

---

## HOW TO START A SESSION

1. Read **Current State** below — this tells you what's happening right now
2. Check `handover/sessions/` for the latest diary if you need more detail
3. Do NOT ask "what were you working on?" — the answer is here

---

## CURRENT STATE
**Last updated:** 2026-05-06
**Update this section at the end of every session, before writing the handover diary.**

### App State
- Dev server: `npm run dev` → http://127.0.0.1:3000 (use 127.0.0.1 not localhost on Windows)
- Build: passing ✅
- Theme: dark (RacingZone-inspired, black/white/green) — do not revert
- Working pages: `/odds` (NRL + AFL tabs), `/research`, `/tools`

### Scheduled Tasks (Task Scheduler)
| Task | Schedule | Status |
|------|----------|--------|
| "BetMate Odds Snapshot 10min" | Every 10 min | ✅ Running |
| "BetMate NRL Injuries" | Monday 10:00 | ✅ Installed |

### Scrapers — Output Locations
| Scraper | Output | Consumed by |
|---------|--------|-------------|
| `lib/scraper/odds_snapshot.py` | `data/odds_snapshots/YYYY/YYYY-MM-DD.csv` | UI + study |
| `lib/scraper/odds_movement_tracker.py` | `data/odds_movements/YYYY/YYYY-MM-DD.csv` | UI alerts |
| `lib/scraper/nrl_injuries.py` | `data/nrl/injuries/processed/latest-injuries.json` | BettingEngine T5 |

### Injury Scraper — Current Source
Source changed 2026-05-05: NRL.com casualty ward (Fox Sports broke).
URL: `https://www.nrl.com/news/{season}/01/01/nrl-casualty-ward-...`
Last scraped: 2026-05-05 (R10, 103 records)

### Odds API Budget
~30,000 calls/month. Current usage ~25,920/month (10-min snapshots).
Headroom for manual checks but don't add more frequent polling.

### Pending Work
- Odds movement alerts: add threshold filter (only alert if change_pct >= 10%)
- UI: no pending redesign — user reverted RacingZone polish on 2026-05-05, keep current look
- AFL scraper: no equivalent injury scraper yet

---

## HANDOVER RULE
Write a diary entry to `handover/sessions/YYYY-MM-DD_description.md` at the end of EVERY session.
No exceptions.

---

## PROJECT OVERVIEW

BetMate is a Next.js frontend that:
1. Shows live odds from The Odds API (NRL + AFL)
2. Runs Python scrapers that feed data into BettingEngine (injuries, style stats)
3. Tracks odds snapshots and price movements intraday

### Tech Stack
- Next.js (TypeScript)
- The Odds API for market data
- Python scrapers (run via `uv`, Task Scheduler on Windows)
- Supabase (auth + some data)

### Environment Setup (NEW MACHINE)
**Do this EVERY time on a fresh pull. Missing .env.local = everything broken.**

1. Copy `.env.local.example` → `.env.local`
2. Fill in:
   ```
   ODDS_API_KEY=<key>
   NEXT_PUBLIC_SUPABASE_URL=<url>
   NEXT_PUBLIC_SUPABASE_ANON_KEY=<key>
   ```
3. `npm install`
4. `npm run dev`

"No games" or empty odds = missing `.env.local`. This is NEVER a code bug.

### Running Python Scrapers
```powershell
# Use uv — full path required for Task Scheduler:
& C:\Users\ElliotBladen\.local\bin\uv.exe run python lib/scraper/odds_snapshot.py
& C:\Users\ElliotBladen\.local\bin\uv.exe run python lib/scraper/nrl_injuries.py

# uv cache is local to avoid permission issues:
# BetMate\.uv-cache
```

### Key Files
| File | Purpose |
|------|---------|
| `lib/scraper/odds_snapshot.py` | Pulls odds from API, appends to dated CSV |
| `lib/scraper/odds_movement_tracker.py` | Diffs last two snapshots, writes movements CSV |
| `lib/scraper/nrl_injuries.py` | Scrapes NRL.com casualty ward |
| `scripts/run_odds_snapshot_cycle.ps1` | Wrapper: runs snapshot + movement tracker |
| `scripts/install_odds_snapshot_task.ps1` | Installs 10-min Task Scheduler task |

### Dev Server Issues
If `.next` build cache corrupts (symptom: `Cannot find module './948.js'`):
```powershell
Stop-Process -Name node -Force
Remove-Item -Recurse -Force .next
npm run dev
```
