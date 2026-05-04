#!/usr/bin/env python3
"""
scripts/log_actual_bet.py
=========================
Append new bets or settle existing bets in data/bets/actual_bets_2026.csv.

USAGE
-----
Log a new (pending) bet:
    python scripts/log_actual_bet.py log \
        --sport NRL --season 2026 --round 11 \
        --home "Brisbane Broncos" --away "Sydney Roosters" \
        --market h2h --selection "Brisbane Broncos" \
        --odds 2.10 --stake 50 \
        [--line -3.5] \
        [--bookmaker bet365] \
        [--model-price 1.95] [--model-line -3.5] \
        [--notes "strong value"]

Settle an existing bet:
    python scripts/log_actual_bet.py settle \
        --bet-id 2026-0007 \
        --result win --return 105.00 \
        [--closing-price 2.05] [--closing-line -3.5]

Show current ledger summary:
    python scripts/log_actual_bet.py list
"""

import argparse
import csv
import os
import sys
from datetime import datetime

BETS_CSV = os.path.join(os.path.dirname(__file__), '..', 'data', 'bets', 'actual_bets_2026.csv')

FIELDNAMES = [
    'bet_id', 'placed_date', 'placed_time', 'sport', 'season', 'round',
    'home_team', 'away_team', 'market_type', 'selection', 'line',
    'odds_taken', 'stake', 'return_amount', 'result', 'pnl',
    'bookmaker', 'model_price', 'model_line',
    'closing_price', 'closing_line', 'clv',
    'source_signal_id', 'source_text', 'notes',
]


# =============================================================================
# Helpers
# =============================================================================

def _csv_path():
    path = os.path.normpath(BETS_CSV)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _read_all():
    path = _csv_path()
    if not os.path.exists(path):
        return []
    with open(path, newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def _write_all(rows):
    path = _csv_path()
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            # Fill any missing new columns with ''
            writer.writerow({f: row.get(f, '') for f in FIELDNAMES})


def _next_bet_id(rows, season):
    existing = [r['bet_id'] for r in rows if r['bet_id'].startswith(str(season) + '-')]
    if not existing:
        return f'{season}-0001'
    nums = []
    for bid in existing:
        try:
            nums.append(int(bid.split('-')[1]))
        except (IndexError, ValueError):
            pass
    return f'{season}-{max(nums) + 1:04d}'


def _clv(odds_taken, closing_price):
    """Closing line value: % edge vs closing price."""
    try:
        o = float(odds_taken)
        c = float(closing_price)
        if c <= 1.0 or o <= 1.0:
            return ''
        # CLV = (1/closing - 1/odds_taken) expressed as percentage of closing probability
        closing_prob = 1.0 / c
        taken_prob   = 1.0 / o
        return round((taken_prob - closing_prob) / closing_prob * 100, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return ''


# =============================================================================
# Subcommands
# =============================================================================

def cmd_log(args):
    rows = _read_all()
    bet_id = _next_bet_id(rows, args.season)
    now = datetime.now()
    placed_date = args.date or now.strftime('%Y-%m-%d')
    placed_time = args.time or now.strftime('%H:%M')

    row = {
        'bet_id':          bet_id,
        'placed_date':     placed_date,
        'placed_time':     placed_time,
        'sport':           args.sport.upper(),
        'season':          args.season,
        'round':           args.round,
        'home_team':       args.home,
        'away_team':       args.away,
        'market_type':     args.market.lower(),
        'selection':       args.selection,
        'line':            args.line or '',
        'odds_taken':      args.odds,
        'stake':           f'{float(args.stake):.2f}',
        'return_amount':   args.return_amount or '0.00',
        'result':          args.result or 'pending',
        'pnl':             '',
        'bookmaker':       args.bookmaker or 'unknown',
        'model_price':     args.model_price or '',
        'model_line':      args.model_line or '',
        'closing_price':   args.closing_price or '',
        'closing_line':    args.closing_line or '',
        'clv':             '',
        'source_signal_id': args.signal_id or '',
        'source_text':     args.source_text or '',
        'notes':           args.notes or '',
    }

    # If fully settled at log time, compute pnl and clv immediately
    if row['result'] in ('win', 'loss', 'void') and row['return_amount'] != '0.00':
        _settle_row(row)

    rows.append(row)
    _write_all(rows)
    print(f'Logged bet {bet_id}: {args.sport} R{args.round} {args.selection} @ {args.odds} x${args.stake}')


def _settle_row(row):
    """Mutate a row in-place to compute pnl and clv from existing fields."""
    stake  = float(row.get('stake', 0) or 0)
    ret    = float(row.get('return_amount', 0) or 0)
    result = row.get('result', '')
    if result == 'win':
        row['pnl'] = f'{ret - stake:.2f}'
    elif result == 'loss':
        row['return_amount'] = '0.00'
        row['pnl'] = f'{-stake:.2f}'
    elif result == 'void':
        row['return_amount'] = f'{stake:.2f}'
        row['pnl'] = '0.00'

    # Compute CLV if closing price is known
    cp = row.get('closing_price', '')
    if cp:
        row['clv'] = _clv(row.get('odds_taken', ''), cp)


def cmd_settle(args):
    rows = _read_all()
    target = None
    for row in rows:
        if row['bet_id'] == args.bet_id:
            target = row
            break

    if target is None:
        print(f'ERROR: bet_id {args.bet_id} not found in ledger.', file=sys.stderr)
        sys.exit(1)

    target['result'] = args.result
    if args.result == 'win' and args.return_amount:
        target['return_amount'] = f'{float(args.return_amount):.2f}'
    if args.closing_price:
        target['closing_price'] = args.closing_price
    if args.closing_line:
        target['closing_line'] = args.closing_line

    _settle_row(target)
    _write_all(rows)
    print(f'Settled {args.bet_id}: {args.result}  P/L {target["pnl"]}  CLV {target.get("clv", "n/a")}')


def cmd_list(args):
    rows = _read_all()
    if not rows:
        print('No bets logged.')
        return

    print(f'{"BET_ID":<12} {"DATE":<12} {"SPORT":<5} {"RND":<4} {"MARKET":<9} '
          f'{"SELECTION":<30} {"ODDS":>6} {"STAKE":>7} {"RESULT":<8} {"P/L":>8} {"CLV":>6}')
    print('-' * 110)
    for r in rows:
        result = r.get('result', 'pending') or 'pending'
        pnl    = r.get('pnl', '') or ''
        clv    = r.get('clv', '') or ''
        print(f'{r["bet_id"]:<12} {r["placed_date"]:<12} {r["sport"]:<5} {r["round"]:<4} '
              f'{r["market_type"]:<9} {r["selection"]:<30} {r["odds_taken"]:>6} '
              f'{r["stake"]:>7} {result:<8} {pnl:>8} {clv:>6}')

    staked = sum(float(r.get('stake', 0) or 0) for r in rows)
    pnl    = sum(float(r.get('pnl', 0) or 0) for r in rows if r.get('pnl'))
    wins   = sum(1 for r in rows if r.get('result') == 'win')
    losses = sum(1 for r in rows if r.get('result') == 'loss')
    print('-' * 110)
    print(f'  {len(rows)} bets  |  {wins}W / {losses}L  |  Staked: ${staked:.2f}  |  P/L: ${pnl:+.2f}')


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Log or settle bets in actual_bets_2026.csv')
    sub = parser.add_subparsers(dest='cmd', required=True)

    # --- log ---
    p_log = sub.add_parser('log', help='Append a new bet')
    p_log.add_argument('--sport',         required=True)
    p_log.add_argument('--season',        required=True, type=int)
    p_log.add_argument('--round',         required=True, type=int)
    p_log.add_argument('--home',          required=True)
    p_log.add_argument('--away',          required=True)
    p_log.add_argument('--market',        required=True, choices=['h2h', 'handicap', 'total'])
    p_log.add_argument('--selection',     required=True)
    p_log.add_argument('--odds',          required=True, type=float)
    p_log.add_argument('--stake',         required=True, type=float)
    p_log.add_argument('--line',          default=None)
    p_log.add_argument('--bookmaker',     default='unknown')
    p_log.add_argument('--result',        default='pending', choices=['pending', 'win', 'loss', 'void'])
    p_log.add_argument('--return-amount', default=None, dest='return_amount')
    p_log.add_argument('--closing-price', default=None, dest='closing_price')
    p_log.add_argument('--closing-line',  default=None, dest='closing_line')
    p_log.add_argument('--model-price',   default=None, dest='model_price')
    p_log.add_argument('--model-line',    default=None, dest='model_line')
    p_log.add_argument('--signal-id',     default=None, dest='signal_id')
    p_log.add_argument('--source-text',   default=None, dest='source_text')
    p_log.add_argument('--notes',         default=None)
    p_log.add_argument('--date',          default=None, help='Override placed_date (YYYY-MM-DD)')
    p_log.add_argument('--time',          default=None, help='Override placed_time (HH:MM)')

    # --- settle ---
    p_set = sub.add_parser('settle', help='Settle an existing bet')
    p_set.add_argument('--bet-id',        required=True, dest='bet_id')
    p_set.add_argument('--result',        required=True, choices=['win', 'loss', 'void'])
    p_set.add_argument('--return',        default=None, dest='return_amount',
                       help='Total return inc. stake (wins only)')
    p_set.add_argument('--closing-price', default=None, dest='closing_price')
    p_set.add_argument('--closing-line',  default=None, dest='closing_line')

    # --- list ---
    sub.add_parser('list', help='Print current ledger')

    args = parser.parse_args()
    {'log': cmd_log, 'settle': cmd_settle, 'list': cmd_list}[args.cmd](args)


if __name__ == '__main__':
    main()
