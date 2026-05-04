# 2026-05-03 11:55 AEST — Actual Bets Ledger
**Agent:** Codex
**Round context:** AFL R8 2026, NRL R10 2026

---

## What was done

- Created physical folders for actual bet tracking:
  - `data/bets/`
  - `outputs/bets/`
- Created actual bets ledger:
  - `data/bets/actual_bets_2026.csv`
- Created first performance summary:
  - `outputs/bets/performance_summary_2026.csv`
- Logged 6 user-placed bets from pasted slip text:
  - Carlton H2H @ 2.55, stake $40, loss
  - Western Bulldogs H2H @ 3.21, stake $33, loss
  - Adelaide Crows -9.5 @ 1.89, stake $50, loss
  - Carlton v St Kilda under 183.5 @ 1.89, stake $50, win, return $94.50
  - Dolphins v Storm under 54.5 @ 1.84, stake $50, win, return $92.00
  - Dolphins -3.5 @ 1.89, stake $50, win, return $94.50

## Current state

- Actual bets are currently tracked in CSV, not in the DB `bets` table.
- The DB `bets` table exists but requires `signal_id`, so a proper signal-linked workflow still needs building.
- Current settled performance:
  - bets: 6
  - wins: 3
  - losses: 3
  - pending: 0
  - total staked: $273.00
  - total return: $281.00
  - P/L: +$8.00
  - ROI: +2.93%
- Sport split:
  - AFL: 1W / 3L, P/L -$78.50, ROI -45.38%
  - NRL: 2W / 0L, P/L +$86.50, ROI +86.50%

## Watch out for

- User clarified the betting slip semantics:
  - `No Return` means settled loss.
  - `+ $return` means settled win.
- The first ledger attempt incorrectly treated one missing return as pending; it was corrected after the full slip was pasted.
- Bookmaker is currently stored as `unknown` because the pasted slip did not specify the bookmaker.
- Returns are total returns including stake. P/L is `return_amount - stake`.
- For DB-backed bet tracking, do not insert into `bets` without a real `signal_id` unless schema/workflow is deliberately changed.

## Next session should

1. Build a proper `scripts/log_actual_bet.py` workflow that appends to CSV and optionally links to DB signals.
2. Build `scripts/bet_performance_report.py` so summaries are generated, not manually edited.
3. Add columns for model comparison:
   - model_price
   - model_line
   - closing_price
   - closing_line
   - clv
   - source_signal_id
4. Decide whether actual bets should remain CSV-first or whether to add a looser `actual_bets` table separate from signal-linked `bets`.
