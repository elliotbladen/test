# 2026-05-05 - Odds tracking and ops fixes

**Agent:** Codex

---

## Summary

Main work today moved BetMate from one-off daily odds snapshots toward intraday odds movement tracking.

The system now pulls NRL + AFL odds every 10 minutes, appends each pull to the dated snapshot CSV, then compares the latest two pulls and writes any price movements to a separate movement CSV.

---

## Odds Snapshot Changes

### Previous behavior

`lib/scraper/odds_snapshot.py` wrote:

- `data/odds_snapshots/YYYY/YYYY-MM-DD.csv`
- `data/odds_snapshots/latest.csv`

But the dated file was overwritten each run. That was fine for one daily snapshot, but wrong for intraday movement tracking.

### Current behavior

The dated CSV is now appended intraday:

```text
data/odds_snapshots/2026/2026-05-05.csv
```

`latest.csv` remains the most recent pull only.

This means the dated file becomes the time series.

---

## Movement Tracker

Added:

```text
lib/scraper/odds_movement_tracker.py
```

It reads the latest two `snapshot_time` groups from the current day snapshot file and writes price changes to:

```text
data/odds_movements/YYYY/YYYY-MM-DD.csv
data/odds_movements/latest.csv
```

Output columns:

```text
detected_date
detected_time
from_snapshot_time
to_snapshot_time
sport
game_id
home_team
away_team
commence_time
bookmaker
market
outcome
point
old_price
new_price
change
change_pct
direction
```

The tracker is idempotent for a given `to_snapshot_time + sport + game + bookmaker + market + outcome + point`, so reruns should not duplicate the same movement rows in the dated movement file.

`latest.csv` may contain only a header if the most recent 10-minute window had no movements. That is expected. The full history is in the dated file.

---

## Scheduled Task

Added wrapper:

```text
scripts/run_odds_snapshot_cycle.ps1
```

This runs:

```text
uv run --with requests python lib/scraper/odds_snapshot.py
uv run python lib/scraper/odds_movement_tracker.py
```

Updated installer:

```text
scripts/install_odds_snapshot_task.ps1
```

Current installed task:

```text
BetMate Odds Snapshot 10min
Schedule: every 10 minutes
State: Ready
LastTaskResult: 0
NextRunTime: 2026-05-05 2:20 PM
```

Old failing task:

```text
BetMate Daily Odds Snapshot
State: Disabled
```

Important fix: Task Scheduler could not find plain `uv`, so the installed task now uses:

```text
C:\Users\ElliotBladen\.local\bin\uv.exe
```

It also sets a repo-local uv cache:

```text
BetMate\.uv-cache
```

This avoids the earlier `uv` cache permission failure.

---

## API Usage

Current plan mentioned by user:

```text
30,000 API calls/month
```

Approx current usage:

```text
1 full NRL + AFL pull ~= 6 API calls
Every 10 minutes = 6 pulls/hour
6 x 6 = 36 calls/hour
36 x 24 = 864 calls/day
864 x 30 = 25,920 calls/month
```

This leaves some headroom for manual checks and UI route calls.

---

## UI / Dev Server Notes

User disliked the RacingZone polish attempt, so it was reverted. See:

```text
handover/sessions/2026-05-05_racingzone-polish-reverted.md
```

Kept non-visual fixes:

- `app/layout.tsx` wraps `Header` in `Suspense`
- `app/odds/page.tsx` wraps odds content in `Suspense`
- `README.md` now correctly documents `ODDS_API_KEY`, not `NEXT_PUBLIC_ODDS_API_KEY`

Dev server issue encountered:

```text
Cannot find module './948.js'
```

Cause was stale/corrupt `.next` dev cache. Fixed by stopping stale Next processes, deleting `.next`, and restarting.

Verified working:

```text
http://127.0.0.1:3000/odds
/api/odds/nrl -> 200 OK
/api/odds/afl -> 200 OK
```

Prefer `127.0.0.1` over `localhost` on this Windows machine if browser access is flaky.

---

## Validation Done

Commands/tests run:

```text
python -m py_compile lib/scraper/odds_snapshot.py
python -m py_compile lib/scraper/odds_movement_tracker.py
powershell -ExecutionPolicy Bypass -File scripts/run_odds_snapshot_cycle.ps1 -UvExe "C:\Users\ElliotBladen\.local\bin\uv.exe"
Start-ScheduledTask -TaskName "BetMate Odds Snapshot 10min"
```

Final scheduled task test:

```text
LastTaskResult: 0
```

Movement tracking successfully detected changes during testing, including:

```text
GWS vs Essendon
PointsBet Essendon H2H: 7.00 -> 8.00 (+14.29%)
```

---

## Next Suggested Work

1. Add a simple report script for `data/odds_movements/latest.csv` and dated movement files.
2. Add filters for noisy Betfair Exchange `h2h_lay` prices if they create false alerts.
3. Consider a threshold mode, e.g. only alert if `abs(change_pct) >= 10`.
4. Add notification output later: terminal, email, Discord, Telegram, or app UI.
