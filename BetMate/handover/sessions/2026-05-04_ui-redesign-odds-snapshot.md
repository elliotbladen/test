# 2026-05-04 — UI Redesign + Daily Odds Snapshot
**Agent:** Claude (claude-sonnet-4-6)

---

## UI Redesign (RacingZone inspired)

Goal: black/white/green premium feel — less startup, more professional data platform.

### Files changed

| File | What changed |
|------|--------------|
| `tailwind.config.js` | New color tokens: `page`, `surface`, `raised`, `line`, `secondary`, `muted`, `ghost` |
| `app/globals.css` | Background `#0D0D0D`, card surface `#111111`, border `#252525`, muted text `#5C5C5C` |
| `app/layout.tsx` | Body bg + themeColor updated to `#0D0D0D` |
| `components/layout/Header.tsx` | Full redesign — see below |
| `components/layout/Footer.tsx` | Two-tone logo, muted colours tightened |
| `components/odds/GameCard.tsx` | Card, tabs, BmCard, EV strip updated |

### Header redesign
- **Solid `border-b-2 border-[#00C896]`** — green line across bottom of header (signature move)
- **Two-tone logo**: "Bet" white + "Mate" green (was all-green mono uppercase)
- **Nav active state**: green `border-b-2` underline indicator (was text colour only)
- **Sport selector**: segmented control style (outlined pill with border-l divider)
- **Sign in**: lighter weight sans-serif, not mono uppercase
- Height: 60px (was 56px)

### GameCard redesign
- Card: `bg-[#111111] border-[#252525]` — visibly lifted from page bg
- Market tabs: green bottom-border underline for active (was `bg-[#00C896]/5` fill)
- BmCard non-best: `bg-[#1A1A1A]` (was flat `#111`)
- Dividers: `#1E1E1E` throughout
- Muted text: `#5C5C5C` (was `#888` — too bright, competed with real content)

---

## Daily Odds Snapshot

### Script: `lib/scraper/odds_snapshot.py`
- Calls The Odds API for NRL (`rugbyleague_nrl`) + AFL (`aussierules_afl`)
- Regions: AU, Markets: h2h + spreads + totals, Format: decimal
- Flattens to one row per game × bookmaker × market × outcome
- Reads API key from `.env.local` automatically
- Saves to `data/odds_snapshots/YYYY/YYYY-MM-DD.csv` + `latest.csv`
- Log: `data/odds_snapshots/logs/snapshot.log`
- Costs ~3 API calls per run (488 remaining as of today)

### CSV columns
`snapshot_date, snapshot_time, sport, game_id, home_team, away_team, commence_time, bookmaker, market, outcome, price, point`

### First run result (2026-05-04)
- NRL: 8 events
- AFL: 9 events
- Total: 716 rows
- File: `data/odds_snapshots/2026/2026-05-04.csv`

### Scheduled task: `scripts/install_odds_snapshot_task.ps1`
- Task name: "BetMate Daily Odds Snapshot"
- Schedule: daily at 09:00 AM
- Status: **Installed and confirmed Ready**

### End-of-year study use cases
- Line movement: how did opening Monday price vs Saturday price compare?
- Best bookmaker: which bookie had the best H2H price most often per team?
- EV validation: did our model's EV signals predict line movement correctly?
- Market efficiency: how tight were spreads over the season?

---

## Next session should

1. Verify UI changes are visible in browser (hard refresh `Ctrl+Shift+R`)
2. Check odds snapshot runs at 9 AM tomorrow — confirm CSV written
3. Continue UI polish based on user feedback
