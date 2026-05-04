# Market Snapshots

Daily NRL and AFL market snapshots are captured from already-collected odds
workbooks and appended to `market_snapshots`.

## NRL Source

Current configured NRL source:

```text
/Users/elliotbladen/betmate-web/public/data/nrl/historical-odds/latest/nrl.xlsx
```

The snapshotter reads the workbook's `Data` sheet and records the latest
available price columns:

- H2H: `Home Odds Close` / `Away Odds Close`, falling back to open if needed
- Handicap: `Home Line Close` / `Away Line Close` plus line odds
- Total: `Total Score Close` plus over/under odds

Rows are appended. Existing snapshots are not overwritten.

## Commands

Dry run next round:

```bash
python3 scripts/betmate_market_snapshot.py --round-mode next --dry-run
```

Capture next round:

```bash
python3 scripts/betmate_market_snapshot.py --round-mode next
```

Capture a specific round:

```bash
python3 scripts/betmate_market_snapshot.py --round 11
```

## AFL Source

Current configured AFL source:

```text
/Users/elliotbladen/Downloads/afl (7).xlsx
```

The AFL workbook does not include a round column, so the AFL snapshotter uses a
date window. It creates/finds canonical AFL matches as needed, then appends
snapshots against those `match_id`s.

Dry run upcoming AFL games in the next 10 days:

```bash
python3 scripts/afl_market_snapshot.py --dry-run
```

Capture upcoming AFL games in the next 10 days:

```bash
python3 scripts/afl_market_snapshot.py
```

Dry run a known date range:

```bash
python3 scripts/afl_market_snapshot.py --date-from 2026-04-23 --date-to 2026-04-26 --round 7 --dry-run
```

Reports are written to:

```text
logs/market_snapshots/
```

## Schedule

The NRL macOS LaunchAgent is installed as:

```text
com.bettingmodel.nrl-market-snapshot
```

It runs daily at 09:00 and executes:

```bash
/Users/elliotbladen/Betting_model/.venv/bin/python3 \
  /Users/elliotbladen/Betting_model/scripts/betmate_market_snapshot.py \
  --config config/betmate_automation.yaml \
  --round-mode next
```

Installer:

```bash
python3 scripts/install_market_snapshot_launchd.py --hour 9 --minute 0 --load
```

Uninstall:

```bash
python3 scripts/install_market_snapshot_launchd.py --uninstall
```

The AFL macOS LaunchAgent is installed as:

```text
com.bettingmodel.afl-market-snapshot
```

It runs daily at 09:05 and executes:

```bash
/Users/elliotbladen/Betting_model/.venv/bin/python3 \
  /Users/elliotbladen/Betting_model/scripts/afl_market_snapshot.py \
  --config config/betmate_automation.yaml \
  --days 10
```

AFL installer:

```bash
python3 scripts/install_afl_market_snapshot_launchd.py --hour 9 --minute 5 --load
```

## Current Note

As of 2026-05-03 11:35 AEST, Betmate's odds workbook only contains prices up to
NRL Round 9. Round 11 is correctly targeted by the script, but no snapshots will
be inserted until the Betmate workbook includes Round 11 rows.

As of 2026-05-03 11:40 AEST, the configured AFL workbook contains prices through
2026-04-26. The AFL parser found 9 games and 54 snapshots for 2026-04-23 to
2026-04-26 in dry-run mode, but the live 2026-05-03 to 2026-05-13 window has no
rows yet.
