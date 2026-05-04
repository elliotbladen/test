#!/usr/bin/env python3
"""
scripts/market_movement_report.py
==================================
Print open / latest / close price movement by game from market_snapshots.

USAGE
-----
    python scripts/market_movement_report.py --season 2026 --round 11
    python scripts/market_movement_report.py --season 2026 --round 8 --sport AFL
    python scripts/market_movement_report.py --season 2026 --round 10 --market h2h
    python scripts/market_movement_report.py --match-id 485

Movement is shown per market type (h2h, handicap, total), per selection.
For each, you see: OPEN → LATEST (CLOSE if flagged), and the drift in
percentage points of implied probability.
"""

import argparse
import os
import sqlite3
import sys
import yaml

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.yaml')


def _get_conn(settings_path):
    with open(settings_path) as fh:
        settings = yaml.safe_load(fh)
    db_path = settings.get('database', {}).get('path', 'data/betting_model.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _implied(odds):
    if not odds or float(odds) <= 1.0:
        return None
    return 1.0 / float(odds)


def _drift_str(open_odds, latest_odds):
    """Return a descriptive drift string: '2.10 → 1.95 (▲ 3.5pp)'"""
    if open_odds is None or latest_odds is None:
        return f'{latest_odds or "?"}'
    o_imp = _implied(open_odds)
    l_imp = _implied(latest_odds)
    if o_imp is None or l_imp is None:
        return f'{open_odds} → {latest_odds}'
    drift_pp = (l_imp - o_imp) * 100
    arrow    = '▲' if drift_pp > 0 else ('▼' if drift_pp < 0 else '—')
    return f'{open_odds:.3f} → {latest_odds:.3f}  ({arrow} {abs(drift_pp):.1f}pp)'


def get_matches(conn, season, round_number, sport, match_id):
    if match_id:
        rows = conn.execute("""
            SELECT m.match_id, m.season, m.round_number,
                   ht.team_name AS home, at.team_name AS away,
                   m.match_date, m.kickoff_datetime
            FROM matches m
            JOIN teams ht ON ht.team_id = m.home_team_id
            JOIN teams at ON at.team_id = m.away_team_id
            WHERE m.match_id = ?
        """, (match_id,)).fetchall()
    else:
        params = [season, round_number]
        rows = conn.execute("""
            SELECT m.match_id, m.season, m.round_number,
                   ht.team_name AS home, at.team_name AS away,
                   m.match_date, m.kickoff_datetime
            FROM matches m
            JOIN teams ht ON ht.team_id = m.home_team_id
            JOIN teams at ON at.team_id = m.away_team_id
            WHERE m.season = ? AND m.round_number = ?
            ORDER BY m.match_date, m.kickoff_datetime
        """, params).fetchall()
    return rows


def get_snapshots(conn, match_id, market_filter, bookmaker_filter):
    params = [match_id]
    extra  = ''
    if market_filter:
        extra  += ' AND s.market_type = ?'
        params.append(market_filter)
    if bookmaker_filter:
        extra += ' AND b.bookmaker_code = ?'
        params.append(bookmaker_filter)

    return conn.execute(f"""
        SELECT s.snapshot_id, s.market_type, s.selection_name, s.line_value,
               s.odds_decimal, s.is_opening, s.is_closing, s.captured_at,
               b.bookmaker_name, b.bookmaker_code
        FROM market_snapshots s
        JOIN bookmakers b ON b.bookmaker_id = s.bookmaker_id
        WHERE s.match_id = ? {extra}
        ORDER BY s.market_type, s.selection_name, s.captured_at
    """, params).fetchall()


def _group_snapshots(snaps):
    """Group by (market_type, selection_name, line_value, bookmaker_code)."""
    groups = {}
    for s in snaps:
        key = (s['market_type'], s['selection_name'],
                s['line_value'], s['bookmaker_code'])
        groups.setdefault(key, []).append(s)
    return groups


def print_match_report(match, snaps):
    kdt = match['kickoff_datetime'] or ''
    # kickoff_datetime may be "2026-03-26 19:50:00" or ISO "2026-03-26T19:50:00"
    kickoff_time = kdt.replace('T', ' ').split(' ')[1][:5] if ' ' in kdt or 'T' in kdt else ''
    header = f'{match["home"]} v {match["away"]}  |  S{match["season"]} R{match["round_number"]}  |  {match["match_date"] or ""}  {kickoff_time}'
    print()
    print(f'  {header}')
    print('  ' + '─' * len(header))

    if not snaps:
        print('    (no snapshots)')
        return

    groups = _group_snapshots(snaps)

    current_market = None
    for key in sorted(groups.keys()):
        market_type, selection, line, bookie = key
        rows = groups[key]

        if market_type != current_market:
            current_market = market_type
            print(f'\n    [{market_type.upper()}]')

        open_row    = next((r for r in rows if r['is_opening']), None)
        close_row   = next((r for r in rows if r['is_closing']), None)
        latest_row  = rows[-1]  # most recent by captured_at

        open_odds   = float(open_row['odds_decimal'])   if open_row   else None
        close_odds  = float(close_row['odds_decimal'])  if close_row  else None
        latest_odds = float(latest_row['odds_decimal'])

        line_str = f' (line {line:+.1f})' if line is not None else ''
        label    = f'{selection}{line_str}'
        drift    = _drift_str(open_odds, latest_odds)

        close_str = f'  [close {close_odds:.3f}]' if close_row and close_row != latest_row else ''
        bookie_str = f'  [{bookie}]' if bookie else ''
        n = len(rows)

        print(f'      {label:<28}  {drift}{close_str}  ({n} snaps){bookie_str}')


def main():
    parser = argparse.ArgumentParser(description='Market line movement report')
    parser.add_argument('--settings',   default=SETTINGS_PATH)
    parser.add_argument('--season',     type=int, default=None)
    parser.add_argument('--round',      type=int, default=None, dest='round_number')
    parser.add_argument('--sport',      default=None, help='NRL or AFL (informational only)')
    parser.add_argument('--market',     default=None, choices=['h2h', 'handicap', 'total'],
                        help='Filter to one market type')
    parser.add_argument('--bookmaker',  default=None, help='Filter by bookmaker code')
    parser.add_argument('--match-id',   default=None, type=int, dest='match_id',
                        help='Report on a single match_id')

    args = parser.parse_args()

    if not args.match_id and (args.season is None or args.round_number is None):
        parser.error('Provide --season and --round, or --match-id')

    conn = _get_conn(args.settings)

    matches = get_matches(conn, args.season, args.round_number, args.sport, args.match_id)
    if not matches:
        print('No matches found for the given filters.')
        sys.exit(0)

    sport_label = f' — {args.sport.upper()}' if args.sport else ''
    rnd_label   = f'R{args.round_number}' if args.round_number else ''
    print(f'\n=== Market Movement Report  S{args.season or ""} {rnd_label}{sport_label} ===')

    total_snaps = 0
    for match in matches:
        snaps = get_snapshots(conn, match['match_id'], args.market, args.bookmaker)
        total_snaps += len(snaps)
        print_match_report(match, snaps)

    print(f'\n  {len(matches)} match(es)  |  {total_snaps} snapshot(s) total\n')
    conn.close()


if __name__ == '__main__':
    main()
