#!/usr/bin/env python3
"""
scripts/bet_performance_report.py
===================================
Reads data/bets/actual_bets_2026.csv and prints a performance report.
Also regenerates outputs/bets/performance_summary_2026.csv.

USAGE
-----
    python scripts/bet_performance_report.py [--season 2026] [--sport NRL] [--no-save]
"""

import argparse
import csv
import os
from collections import defaultdict

BETS_CSV    = os.path.join(os.path.dirname(__file__), '..', 'data', 'bets', 'actual_bets_2026.csv')
SUMMARY_CSV = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'bets', 'performance_summary_2026.csv')

SUMMARY_FIELDS = [
    'scope', 'bets', 'settled_bets', 'wins', 'losses', 'pending',
    'total_staked', 'settled_staked', 'total_return', 'pnl', 'roi',
    'avg_odds', 'strike_rate',
    # CLV fields (when closing prices are available)
    'bets_with_clv', 'avg_clv',
]


# =============================================================================
# Stats helpers
# =============================================================================

def _stats(rows):
    bets          = len(rows)
    wins          = sum(1 for r in rows if r.get('result') == 'win')
    losses        = sum(1 for r in rows if r.get('result') == 'loss')
    pending       = sum(1 for r in rows if (r.get('result') or 'pending') == 'pending')
    settled_rows  = [r for r in rows if r.get('result') in ('win', 'loss', 'void')]
    settled_bets  = len(settled_rows)

    total_staked   = sum(float(r.get('stake', 0) or 0) for r in rows)
    settled_staked = sum(float(r.get('stake', 0) or 0) for r in settled_rows)
    total_return   = sum(float(r.get('return_amount', 0) or 0) for r in settled_rows)
    pnl            = total_return - settled_staked
    roi            = (pnl / settled_staked) if settled_staked else 0.0

    odds_vals      = [float(r['odds_taken']) for r in rows if r.get('odds_taken')]
    avg_odds       = (sum(odds_vals) / len(odds_vals)) if odds_vals else 0.0

    strike_rate    = (wins / settled_bets) if settled_bets else 0.0

    # CLV
    clv_vals = []
    for r in rows:
        c = r.get('clv', '')
        if c not in ('', None):
            try:
                clv_vals.append(float(c))
            except ValueError:
                pass
    bets_with_clv = len(clv_vals)
    avg_clv       = (sum(clv_vals) / bets_with_clv) if clv_vals else None

    return {
        'bets':          bets,
        'settled_bets':  settled_bets,
        'wins':          wins,
        'losses':        losses,
        'pending':       pending,
        'total_staked':  round(total_staked, 2),
        'settled_staked': round(settled_staked, 2),
        'total_return':  round(total_return, 2),
        'pnl':           round(pnl, 2),
        'roi':           round(roi, 4),
        'avg_odds':      round(avg_odds, 4),
        'strike_rate':   round(strike_rate, 4),
        'bets_with_clv': bets_with_clv,
        'avg_clv':       round(avg_clv, 2) if avg_clv is not None else '',
    }


# =============================================================================
# Report
# =============================================================================

def _print_block(label, s):
    pnl_str  = f'${s["pnl"]:+.2f}'
    roi_str  = f'{s["roi"] * 100:+.1f}%'
    clv_str  = f'{s["avg_clv"]}%' if s['avg_clv'] != '' else 'n/a'
    sr_str   = f'{s["strike_rate"] * 100:.0f}%'
    print(f'  {label}')
    print(f'    Bets:    {s["bets"]}  ({s["wins"]}W / {s["losses"]}L / {s["pending"]} pending)')
    print(f'    Staked:  ${s["total_staked"]:.2f}  |  Return: ${s["total_return"]:.2f}')
    print(f'    P/L:     {pnl_str}  ({roi_str} ROI)')
    print(f'    Avg odds: {s["avg_odds"]:.2f}  |  Strike: {sr_str}  |  Avg CLV: {clv_str}')


def _print_market_breakdown(rows):
    by_market = defaultdict(list)
    for r in rows:
        by_market[r.get('market_type', 'unknown')].append(r)
    for market, mrs in sorted(by_market.items()):
        s = _stats(mrs)
        wins = s['wins']
        losses = s['losses']
        roi = f'{s["roi"] * 100:+.1f}%'
        pnl = f'${s["pnl"]:+.2f}'
        print(f'      {market:<10}  {len(mrs):>3} bets  {wins}W/{losses}L  {pnl}  ({roi})')


def run_report(args):
    if not os.path.exists(BETS_CSV):
        print(f'No bets file found at {BETS_CSV}')
        return

    with open(BETS_CSV, newline='', encoding='utf-8') as fh:
        all_rows = list(csv.DictReader(fh))

    if args.season:
        all_rows = [r for r in all_rows if str(r.get('season', '')) == str(args.season)]
    if args.sport:
        all_rows = [r for r in all_rows if r.get('sport', '').upper() == args.sport.upper()]

    if not all_rows:
        print('No bets match the filter criteria.')
        return

    # Group by sport
    by_sport = defaultdict(list)
    for r in all_rows:
        by_sport[r.get('sport', 'unknown').upper()].append(r)

    overall = _stats(all_rows)

    season_label = f' {args.season}' if args.season else ''
    sport_label  = f' — {args.sport.upper()}' if args.sport else ''
    print()
    print(f'=== Betting Performance{season_label}{sport_label} ===')
    print()
    _print_block('OVERALL', overall)
    print()

    for sport in sorted(by_sport):
        sport_rows = by_sport[sport]
        s = _stats(sport_rows)
        _print_block(sport, s)
        _print_market_breakdown(sport_rows)
        print()

    # Save summary CSV
    if not args.no_save:
        _save_summary(all_rows, by_sport, args.season)
        print(f'Summary saved → {SUMMARY_CSV}')


def _save_summary(all_rows, by_sport, season):
    os.makedirs(os.path.dirname(SUMMARY_CSV), exist_ok=True)

    summary_rows = []
    overall = _stats(all_rows)
    overall['scope'] = 'all'
    summary_rows.append(overall)

    for sport in sorted(by_sport):
        s = _stats(by_sport[sport])
        s['scope'] = sport
        summary_rows.append(s)

    with open(SUMMARY_CSV, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow({f: row.get(f, '') for f in SUMMARY_FIELDS})


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Print betting performance report')
    parser.add_argument('--season', default=None, help='Filter to season (e.g. 2026)')
    parser.add_argument('--sport',  default=None, help='Filter to sport (e.g. NRL, AFL)')
    parser.add_argument('--no-save', action='store_true', dest='no_save',
                        help='Print only — do not regenerate summary CSV')
    args = parser.parse_args()
    run_report(args)


if __name__ == '__main__':
    main()
