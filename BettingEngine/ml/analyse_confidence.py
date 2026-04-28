#!/usr/bin/env python3
"""
ml/analyse_confidence.py

Parse the 2025 ML backtest and calculate strike rate + ROI
for bets above a given confidence threshold.

Since we don't have stored bookmaker odds, we show:
  - strike rate at each threshold
  - break-even odds required
  - ROI at assumed price points ($1.50, $1.65, $1.80, $1.90, $2.00)

USAGE
-----
    python ml/analyse_confidence.py
    python ml/analyse_confidence.py --file results/2025_ml_backtest.txt --threshold 65
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_backtest(path: Path) -> list[dict]:
    """
    Parse the human-readable backtest text into a list of game dicts.
    Expected line format (after header):
      date  home  away  ML%  ML_pick  actual_winner  h2h  ml_mgn  act_mgn  ml_tot  act_tot  ou
    """
    games = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            # Match data rows: starts with a date like 2025-MM-DD
            m = re.match(
                r'(\d{4}-\d{2}-\d{2})\s+'        # date
                r'(.+?)\s{2,}'                     # home (2+ spaces as delimiter)
                r'(.+?)\s{2,}'                     # away
                r'(\d+\.\d+)%\s+'                  # ML%
                r'(.+?)\s{2,}'                     # ML pick
                r'(.+?)\s+'                        # actual winner
                r'([✓✗])\s+'                       # H2H result
                r'([+-]?\d+\.\d+)\s+'              # ml_margin
                r'([+-]?\d+\.\d+)\s+'              # act_margin
                r'(\d+\.\d+)\s+'                   # ml_total
                r'(\d+\.\d+)\s+'                   # act_total
                r'(OVER|UNDER)',                    # O/U
                line
            )
            if m:
                ml_pct = float(m.group(4))
                h2h_correct = m.group(7) == '✓'
                games.append({
                    'date':         m.group(1),
                    'home':         m.group(2).strip(),
                    'away':         m.group(3).strip(),
                    'ml_pct':       ml_pct,
                    'ml_pick':      m.group(5).strip(),
                    'actual':       m.group(6).strip(),
                    'h2h_correct':  h2h_correct,
                    'ml_margin':    float(m.group(8)),
                    'act_margin':   float(m.group(9)),
                    'ml_total':     float(m.group(10)),
                    'act_total':    float(m.group(11)),
                    'ou':           m.group(12),
                    # Confidence = distance from 50%
                    'confidence':   abs(ml_pct - 50.0) + 50.0,  # e.g. 70% → 70, 30% → 70
                })
    return games


def analyse(games: list[dict], threshold: float) -> dict:
    """Filter by confidence threshold and compute stats."""
    filtered = [g for g in games if g['confidence'] >= threshold]
    if not filtered:
        return {}

    wins   = sum(1 for g in filtered if g['h2h_correct'])
    losses = len(filtered) - wins
    strike = wins / len(filtered)

    # Break-even odds = 1 / strike_rate
    breakeven = 1 / strike if strike > 0 else None

    # ROI at various assumed flat odds (flat $1 stake each game)
    price_points = [1.40, 1.50, 1.65, 1.80, 1.90, 2.00, 2.20]
    roi_table = []
    for price in price_points:
        profit = wins * (price - 1) - losses * 1
        roi    = profit / len(filtered) * 100
        roi_table.append((price, roi))

    return {
        'threshold': threshold,
        'n_bets':    len(filtered),
        'wins':      wins,
        'losses':    losses,
        'strike':    strike,
        'breakeven': breakeven,
        'roi_table': roi_table,
        'games':     filtered,
    }


def print_report(result: dict):
    if not result:
        print('No games found at this threshold.')
        return

    SEP = '─' * 70
    print()
    print('=' * 70)
    print(f"  ML CONFIDENCE BACKTEST — 2025 Season")
    print(f"  Threshold: ≥{result['threshold']:.0f}% confidence on either team")
    print('=' * 70)
    print()
    print(f"  Games at threshold : {result['n_bets']}")
    print(f"  Wins               : {result['wins']}")
    print(f"  Losses             : {result['losses']}")
    print(f"  Strike rate        : {result['strike']*100:.1f}%")
    print(f"  Break-even odds    : ${result['breakeven']:.3f}" if result['breakeven'] else "  Break-even odds: N/A")
    print()
    print(f"  ROI AT ASSUMED FLAT PRICE (flat $1 stake each bet):")
    print(f"  {'Price':>8}  {'ROI':>8}")
    print(f"  {SEP[:20]}")
    for price, roi in result['roi_table']:
        flag = ' ← break-even zone' if abs(roi) < 3 else ''
        sign = '+' if roi >= 0 else ''
        print(f"  ${price:<7.2f}  {sign}{roi:>6.1f}%{flag}")
    print()

    # Breakdown by confidence band
    bands = [
        ('70–79%',  70, 80),
        ('80–89%',  80, 90),
        ('90%+',    90, 101),
    ]
    print(f"  BREAKDOWN BY CONFIDENCE BAND:")
    print(f"  {'Band':<12} {'N':>5} {'Wins':>6} {'Strike':>8}")
    print(f"  {SEP[:38]}")
    for label, lo, hi in bands:
        sub = [g for g in result['games'] if lo <= g['confidence'] < hi]
        if sub:
            sw = sum(1 for g in sub if g['h2h_correct'])
            print(f"  {label:<12} {len(sub):>5} {sw:>6} {sw/len(sub)*100:>7.1f}%")

    print()
    # List individual games
    print(f"  INDIVIDUAL BETS (sorted by confidence):")
    print(f"  {'Date':<12} {'Pick':<28} {'Conf':>6}  {'Result'}")
    print(f"  {SEP}")
    for g in sorted(result['games'], key=lambda x: -x['confidence']):
        conf_str = f"{g['confidence']:.1f}%"
        result_str = '✓ WIN' if g['h2h_correct'] else '✗ LOSS'
        pick = g['ml_pick'][:27]
        print(f"  {g['date']:<12} {pick:<28} {conf_str:>6}  {result_str}")

    print()
    print('=' * 70)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file',      default=str(ROOT / 'results' / '2025_ml_backtest.txt'))
    parser.add_argument('--threshold', type=float, default=70.0,
                        help='Confidence threshold (default 70 = ML prob ≥70%% or ≤30%%)')
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f'File not found: {path}', file=sys.stderr)
        sys.exit(1)

    games = parse_backtest(path)
    if not games:
        print('No games parsed — check file format.', file=sys.stderr)
        sys.exit(1)

    print(f'  Parsed {len(games)} total games from backtest.')

    result = analyse(games, args.threshold)
    print_report(result)


if __name__ == '__main__':
    main()
