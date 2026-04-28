#!/usr/bin/env python3
"""
ml/roi_analysis.py

Cross-reference 2025 ML backtest high-confidence picks with
actual closing odds from nrl (5).xlsx (OddsPortal data).

Calculates real dollar ROI for $1 flat stake on each qualifying bet.

USAGE
-----
    python3 ml/roi_analysis.py --threshold 70
    python3 ml/roi_analysis.py --threshold 65
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

ROOT        = Path(__file__).resolve().parent.parent
BACKTEST    = ROOT / 'results' / '2025_ml_backtest.txt'
ODDS_FILE   = Path('/Users/elliotbladen/Downloads/nrl (5).xlsx')

# ── Team name normalisation ───────────────────────────────────────────────────
# Map OddsPortal names → canonical names used in backtest
TEAM_MAP = {
    # Canonical → canonical
    'Penrith Panthers':              'Penrith Panthers',
    'Melbourne Storm':               'Melbourne Storm',
    'Brisbane Broncos':              'Brisbane Broncos',
    'Sydney Roosters':               'Sydney Roosters',
    'Canberra Raiders':              'Canberra Raiders',
    'South Sydney Rabbitohs':        'South Sydney Rabbitohs',
    'Cronulla Sharks':               'Cronulla Sharks',
    'Newcastle Knights':             'Newcastle Knights',
    'Parramatta Eels':               'Parramatta Eels',
    'Gold Coast Titans':             'Gold Coast Titans',
    'Wests Tigers':                  'Wests Tigers',
    'Dolphins':                      'Dolphins',
    'Redcliffe Dolphins':            'Dolphins',
    # Manly variants
    'Manly-Warringah Sea Eagles':    'Manly-Sea Eagles',
    'Manly Sea Eagles':              'Manly-Sea Eagles',
    'Manly-Sea Eagles':              'Manly-Sea Eagles',
    # Warriors variants
    'New Zealand Warriors':          'NZ Warriors',
    'NZ Warriors':                   'NZ Warriors',
    # Cowboys variants
    'North Queensland Cowboys':      'North Cowboys',
    'North QLD Cowboys':             'North Cowboys',
    'North Cowboys':                 'North Cowboys',
    # Dragons variants
    'St George Illawarra Dragons':   'St. George Dragons',
    'St. George Illawarra Dragons':  'St. George Dragons',
    'St George Dragons':             'St. George Dragons',
    'St. George Dragons':            'St. George Dragons',
    # Bulldogs variants
    'Canterbury Bulldogs':           'Bulldogs',
    'Canterbury-Bankstown Bulldogs': 'Bulldogs',
    'Bulldogs':                      'Bulldogs',
}

def norm(name: str) -> str:
    name = (name or '').strip()
    return TEAM_MAP.get(name, name)


# ── Parse backtest file ───────────────────────────────────────────────────────
def parse_backtest(path: Path) -> list[dict]:
    games = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            m = re.match(
                r'(\d{4}-\d{2}-\d{2})\s+'
                r'(.+?)\s{2,}'
                r'(.+?)\s{2,}'
                r'(\d+\.\d+)%\s+'
                r'(.+?)\s{2,}'
                r'(.+?)\s+'
                r'([✓✗])\s+'
                r'([+-]?\d+\.\d+)\s+'
                r'([+-]?\d+\.\d+)\s+'
                r'(\d+\.\d+)\s+'
                r'(\d+\.\d+)\s+'
                r'(OVER|UNDER)',
                line
            )
            if m:
                ml_pct = float(m.group(4))
                games.append({
                    'date':        m.group(1),
                    'home':        m.group(2).strip(),
                    'away':        m.group(3).strip(),
                    'ml_pct':      ml_pct,
                    'ml_pick':     m.group(5).strip(),
                    'actual':      m.group(6).strip(),
                    'correct':     m.group(7) == '✓',
                    'confidence':  abs(ml_pct - 50.0) + 50.0,
                    # Which side is the ML backing?
                    'pick_is_home': m.group(5).strip() == m.group(2).strip(),
                })
    return games


# ── Load odds from xlsx ───────────────────────────────────────────────────────
def load_odds(path: Path) -> dict:
    """
    Returns dict keyed by (date_str, home_norm, away_norm) →
        {home_close, away_close}
    """
    wb   = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws   = wb['Data']
    rows = list(ws.iter_rows(values_only=True))

    # Row index 1 = column headers
    # home_close = col index 16 (0-based), away_close = col index 20
    # Date = col 0, Home = col 2, Away = col 3
    COL_DATE        = 0
    COL_HOME        = 2
    COL_AWAY        = 3
    COL_HOME_BEST   = 9    # Home Odds best (OddsPortal max — always populated)
    COL_AWAY_BEST   = 11   # Away Odds best (OddsPortal max — always populated)
    COL_HOME_OPEN   = 13   # Home Odds Open (always populated)
    COL_AWAY_OPEN   = 17   # Away Odds Open (always populated)
    COL_HOME_CLOSE  = 16   # Home Odds Close (only Grand Final for 2025)
    COL_AWAY_CLOSE  = 20   # Away Odds Close (only Grand Final for 2025)

    lookup = {}
    for row in rows[2:]:   # skip title row + header row
        date_val = row[COL_DATE]
        if not date_val:
            continue
        if isinstance(date_val, datetime):
            date_str = date_val.strftime('%Y-%m-%d')
        else:
            try:
                date_str = str(date_val)[:10]
            except:
                continue

        home_raw = row[COL_HOME]
        away_raw = row[COL_AWAY]
        if not home_raw or not away_raw:
            continue

        home_n = norm(str(home_raw))
        away_n = norm(str(away_raw))

        def safe_float(v):
            try: return float(v) if v else None
            except (TypeError, ValueError): return None

        key = (date_str, home_n, away_n)
        lookup[key] = {
            'home_open':  safe_float(row[COL_HOME_OPEN]),
            'away_open':  safe_float(row[COL_AWAY_OPEN]),
            'home_close': safe_float(row[COL_HOME_CLOSE]) or safe_float(row[COL_HOME_OPEN]),
            'away_close': safe_float(row[COL_AWAY_CLOSE]) or safe_float(row[COL_AWAY_OPEN]),
            'home_best':  safe_float(row[COL_HOME_BEST]),
            'away_best':  safe_float(row[COL_AWAY_BEST]),
        }

    return lookup


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--threshold', type=float, default=70.0)
    args = parser.parse_args()

    print(f'Loading backtest...')
    bt_games = parse_backtest(BACKTEST)
    print(f'  {len(bt_games)} games parsed')

    print(f'Loading odds file...')
    odds = load_odds(ODDS_FILE)
    print(f'  {len(odds)} game-odds entries loaded')

    # Filter to confidence threshold
    qualified = [g for g in bt_games if g['confidence'] >= args.threshold]
    print(f'\n  Games at ≥{args.threshold:.0f}% confidence: {len(qualified)}')

    # Match each qualified game to closing odds
    matched   = []
    unmatched = []

    for g in qualified:
        home_n = norm(g['home'])
        away_n = norm(g['away'])
        key    = (g['date'], home_n, away_n)
        od     = odds.get(key)

        if not od:
            unmatched.append(g)
            continue

        pick_open  = od['home_open']  if g['pick_is_home'] else od['away_open']
        pick_close = od['home_close'] if g['pick_is_home'] else od['away_close']
        pick_best  = od['home_best']  if g['pick_is_home'] else od['away_best']

        if not pick_open:
            unmatched.append(g)
            continue

        matched.append({**g,
            'pick_open':  pick_open,
            'pick_close': pick_close,
            'pick_best':  pick_best,
        })

    print(f'  Matched to closing odds: {len(matched)}')
    if unmatched:
        print(f'  Unmatched (no odds found): {len(unmatched)}')
        for u in unmatched[:5]:
            print(f'    {u["date"]} {norm(u["home"])} vs {norm(u["away"])}')

    if not matched:
        print('No matched games — cannot calculate ROI.')
        sys.exit(1)

    def calc_roi(games, odds_key):
        stake     = 1.0
        total_in  = len(games) * stake
        total_ret = sum(g[odds_key] * stake if g['correct'] else 0.0 for g in games)
        profit    = total_ret - total_in
        roi_pct   = profit / total_in * 100
        return total_in, total_ret, profit, roi_pct

    wins   = sum(1 for g in matched if g['correct'])
    losses = len(matched) - wins
    strike = wins / len(matched) * 100

    in_o,  ret_o,  pl_o,  roi_o  = calc_roi(matched, 'pick_open')
    in_c,  ret_c,  pl_c,  roi_c  = calc_roi(matched, 'pick_close')
    in_b,  ret_b,  pl_b,  roi_b  = calc_roi(matched, 'pick_best')

    SEP = '─' * 85
    print()
    print('=' * 85)
    print(f'  ML CONFIDENCE ROI — 2025 Season  (≥{args.threshold:.0f}% confidence)')
    print(f'  Odds source: OddsPortal  |  Open = market open  |  Close = closing line  |  Best = max odds')
    print('=' * 85)
    print()
    print(f'  Bets: {len(matched)}   Wins: {wins}   Losses: {losses}   Strike: {strike:.1f}%')
    print()
    print(f'  {"":30} {"OPEN":>12} {"CLOSE":>12} {"BEST ODDS":>12}')
    print(f'  {SEP[:70]}')
    print(f'  {"Total staked":<30} ${in_o:>10.2f}  ${in_c:>10.2f}  ${in_b:>10.2f}')
    print(f'  {"Total returned":<30} ${ret_o:>10.2f}  ${ret_c:>10.2f}  ${ret_b:>10.2f}')
    print(f'  {"Profit / Loss":<30} ${pl_o:>+10.2f}  ${pl_c:>+10.2f}  ${pl_b:>+10.2f}')
    print(f'  {"ROI":<30} {roi_o:>+10.1f}%  {roi_c:>+10.1f}%  {roi_b:>+10.1f}%')
    print()

    # Band breakdown
    bands = [
        ('65–69%', 65, 70),
        ('70–74%', 70, 75),
        ('75–79%', 75, 80),
        ('80%+',   80, 101),
    ]
    print(f'  BREAKDOWN BY CONFIDENCE BAND:')
    print(f'  {"Band":<10} {"N":>4} {"W":>4} {"Strike":>8}  {"Open ROI":>10} {"Close ROI":>10} {"Best ROI":>10}')
    print(f'  {SEP[:65]}')
    for label, lo, hi in bands:
        sub = [g for g in matched if lo <= g['confidence'] < hi]
        if not sub:
            continue
        sw = sum(1 for g in sub if g['correct'])
        _, _, _, ro = calc_roi(sub, 'pick_open')
        _, _, _, rc = calc_roi(sub, 'pick_close')
        _, _, _, rb = calc_roi(sub, 'pick_best')
        print(f'  {label:<10} {len(sub):>4} {sw:>4} {sw/len(sub)*100:>7.1f}%  '
              f'{ro:>+9.1f}%  {rc:>+9.1f}%  {rb:>+9.1f}%')

    print()
    print(f'  INDIVIDUAL BETS (sorted by confidence):')
    print(f'  {"Date":<12} {"Pick":<26} {"Conf":>5}  {"Open":>5} {"Close":>6} {"Best":>5}  Result')
    print(f'  {SEP}')
    for g in sorted(matched, key=lambda x: -x['confidence']):
        result = '✓ WIN ' if g['correct'] else '✗ LOSS'
        pick   = g['ml_pick'][:25]
        cl = f'${g["pick_close"]:.2f}' if g['pick_close'] else '  —  '
        print(f'  {g["date"]:<12} {pick:<26} {g["confidence"]:>5.1f}%'
              f'  ${g["pick_open"]:.2f}  {cl:>6}  ${g["pick_best"]:.2f}  {result}')

    print()
    print('=' * 85)


if __name__ == '__main__':
    main()
