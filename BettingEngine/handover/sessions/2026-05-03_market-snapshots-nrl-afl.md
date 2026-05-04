# 2026-05-03 11:41 AEST — NRL/AFL Market Snapshots
**Agent:** Codex
**Round context:** NRL R11 2026, AFL upcoming 2026 window

---

## What was done

- Implemented real append-only snapshot ingestion in:
  - `ingestion/market_snapshots.py`
- Added NRL market snapshot script:
  - `scripts/betmate_market_snapshot.py`
- Added NRL daily launchd installer:
  - `scripts/install_market_snapshot_launchd.py`
- Added AFL market snapshot script:
  - `scripts/afl_market_snapshot.py`
- Added AFL daily launchd installer:
  - `scripts/install_afl_market_snapshot_launchd.py`
- Added/updated docs:
  - `docs/market_snapshots.md`
- Updated config:
  - `config/betmate_automation.yaml`
  - added AFL odds file path:
    - `/Users/elliotbladen/Downloads/afl (7).xlsx`

## Current state

- Both sports write to the existing DB table:
  - `market_snapshots`
- NRL LaunchAgent installed and loaded:
  - label: `com.bettingmodel.nrl-market-snapshot`
  - schedule: daily 09:00
  - command:
    - `.venv/bin/python3 scripts/betmate_market_snapshot.py --config config/betmate_automation.yaml --round-mode next`
- AFL LaunchAgent installed and loaded:
  - label: `com.bettingmodel.afl-market-snapshot`
  - schedule: daily 09:05
  - command:
    - `.venv/bin/python3 scripts/afl_market_snapshot.py --config config/betmate_automation.yaml --days 10`
- Verified launchd sees both jobs:
  - `- 0 com.bettingmodel.nrl-market-snapshot`
  - `- 0 com.bettingmodel.afl-market-snapshot`
- Snapshot reports are written to:
  - `logs/market_snapshots/`

## Validation

- `python3 -m pytest tests/test_snapshot_handling.py`
  - passed: 2 tests
- NRL R9 dry-run:
  - 48 snapshots would be created
  - confirms NRL parser works when workbook rows exist
- NRL R11 run:
  - 0 snapshots inserted
  - current Betmate workbook does not yet contain R11 rows
- AFL 2026-04-23 to 2026-04-26 dry-run:
  - 9 games found
  - 54 snapshots would be created
  - confirms AFL parser works when workbook rows exist
- AFL 2026-05-03 to 2026-05-13 live/upcoming window:
  - 0 games found
  - configured AFL workbook currently only updated through 2026-04-26

## Watch out for

- Current NRL odds source:
  - `/Users/elliotbladen/betmate-web/public/data/nrl/historical-odds/latest/nrl.xlsx`
  - currently only has prices through NRL R9 as of this handover.
- Current AFL odds source:
  - `/Users/elliotbladen/Downloads/afl (7).xlsx`
  - currently only has prices through 2026-04-26 as of this handover.
- Until upstream odds workbooks include next-round rows, the schedulers run cleanly but insert 0 snapshots.
- AFL fixtures are not generally loaded into `matches` yet. `scripts/afl_market_snapshot.py` creates/finds canonical AFL match rows when doing a real capture.
- Earlier AFL dry-run briefly created 9 canonical AFL R7 match rows before dry-run was made read-only. They have no attached snapshots and are harmless, but note DB now shows 9 AFL matches.
- Do not delete/rewrite `market_snapshots`; it is append-only by design.
- `logs/market_snapshots/` is untracked and contains JSON run reports.

## Next session should

1. Once Betmate updates NRL R11 odds, run:
   - `python3 scripts/betmate_market_snapshot.py --round 11`
2. Once AFL workbook updates with upcoming games, run:
   - `python3 scripts/afl_market_snapshot.py --dry-run`
   - then `python3 scripts/afl_market_snapshot.py`
3. Add a quick report command to print open/current/close movement by game from `market_snapshots`.
4. Consider adding source freshness checks for snapshot workbooks, same style as Betmate preflight.
5. Eventually point AFL to a proper Betmate AFL folder once that exists, instead of the local Downloads workbook.
