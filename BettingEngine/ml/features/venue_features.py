#!/usr/bin/env python3
"""
ml/features/venue_features.py

Session 4 — Add venue scoring tendencies to the game log.

For each game, looks back at all PRIOR games at that venue and computes:
  - Historical average total at the venue
  - Historical home win % at the venue
  - Sample size (games played at venue before this one)

Uses only data available BEFORE the game (no look-ahead).
Requires MIN_SAMPLE games at a venue before populating (else blank).

USAGE
-----
    python ml/features/venue_features.py \
        --game-log ml/results/game_log_elo.csv \
        --out      ml/results/game_log_features.csv
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

MIN_SAMPLE = 5   # minimum prior games at venue before we trust the stats


def build_venue_stats(rows):
    """
    For each game, compute venue stats from all PRIOR games at that venue.
    Returns list of dicts with venue columns added.
    """
    # Running tallies per venue — updated after each game
    venue_totals  = defaultdict(list)   # list of total scores
    venue_hw      = defaultdict(list)   # list of 1/0 home wins

    out_rows = []
    for r in rows:
        venue = r['venue'].strip()

        prior_totals = venue_totals[venue]
        prior_hw     = venue_hw[venue]
        n            = len(prior_totals)

        if n >= MIN_SAMPLE:
            venue_avg_total    = round(sum(prior_totals) / n, 2)
            venue_home_win_pct = round(sum(prior_hw) / n, 4)
            venue_sample       = n
        else:
            venue_avg_total    = ''
            venue_home_win_pct = ''
            venue_sample       = n   # still log sample size even if below threshold

        row = dict(r)
        row.update({
            'venue_avg_total':    venue_avg_total,
            'venue_home_win_pct': venue_home_win_pct,
            'venue_sample':       venue_sample,
        })
        out_rows.append(row)

        # Update running tallies AFTER capturing snapshot
        try:
            actual_total  = int(r['actual_total'])
            home_win      = int(r['home_win'])
            venue_totals[venue].append(actual_total)
            venue_hw[venue].append(home_win)
        except (ValueError, KeyError):
            pass

    return out_rows


def print_summary(rows):
    has_venue = [r for r in rows if r['venue_avg_total'] != '']
    no_venue  = len(rows) - len(has_venue)

    print(f"\n  {'─'*50}")
    print(f"  Venue features summary")
    print(f"  {'─'*50}")
    print(f"  Games with venue stats:    {len(has_venue)}")
    print(f"  Games without (too early): {no_venue}")

    if has_venue:
        totals = [float(r['venue_avg_total']) for r in has_venue]
        hwp    = [float(r['venue_home_win_pct']) for r in has_venue]
        print(f"\n  Venue avg total range:  {min(totals):.1f} – {max(totals):.1f}")
        print(f"  Home win pct range:     {min(hwp):.3f} – {max(hwp):.3f}")

        # Highest and lowest scoring venues (from last row per venue)
        venue_latest = {}
        for r in has_venue:
            if r['venue']:
                venue_latest[r['venue']] = r
        by_total = sorted(venue_latest.values(),
                          key=lambda r: float(r['venue_avg_total']))
        print(f"\n  Lowest scoring venues:")
        for r in by_total[:3]:
            print(f"    {r['venue']:<40} avg={float(r['venue_avg_total']):.1f}")
        print(f"  Highest scoring venues:")
        for r in by_total[-3:]:
            print(f"    {r['venue']:<40} avg={float(r['venue_avg_total']):.1f}")


def main():
    parser = argparse.ArgumentParser(description='Add venue features to game log')
    parser.add_argument('--game-log', default=str(ROOT / 'ml/results/game_log_elo.csv'))
    parser.add_argument('--out',      default=str(ROOT / 'ml/results/game_log_features.csv'))
    args = parser.parse_args()

    if not Path(args.game_log).exists():
        print(f"ERROR: not found: {args.game_log}", file=sys.stderr)
        sys.exit(1)

    print("Loading game log ...")
    with open(args.game_log) as f:
        rows = list(csv.DictReader(f))
    print(f"  {len(rows)} games")

    print("Building venue stats (no look-ahead) ...")
    out_rows = build_venue_stats(rows)

    print_summary(out_rows)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out_rows[0].keys())
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\n  Written {len(out_rows)} rows → {out}")
    print("\nDone.")


if __name__ == '__main__':
    main()
