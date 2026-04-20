#!/usr/bin/env python3
"""
ml/features/game_log.py

Session 1 — Build per-game log with rest days for every team.

Reads nrl (4).xlsx and produces a flat CSV with one row per game:
  - Basic game info (season, date, teams, venue, scores)
  - Rest days for home and away team
  - Rest classification (short / normal / long / bye / first_game)
  - Rest differential (home - away)
  - Previous game result for each team (for form features in Session 4)

This is the foundation all other situational features build on.

USAGE
-----
    python ml/features/game_log.py \
        --xlsx '/Users/elliotbladen/Downloads/nrl (4).xlsx' \
        --out ml/results/game_log.csv

OUTPUT COLUMNS
--------------
    season
    date
    home_team
    away_team
    venue
    home_score
    away_score
    actual_margin       home - away
    actual_total        home + away
    home_win            1/0
    home_rest_days      days since home team's last game (blank = first game of season)
    away_rest_days      days since away team's last game
    rest_diff           home_rest_days - away_rest_days
    home_rest_class     short / normal / long / bye / first_game
    away_rest_class     short / normal / long / bye / first_game
    home_prev_margin    margin from home team's last game (their perspective)
    away_prev_margin    margin from away team's last game (their perspective)
    home_off_big_win    1 if home team won last game by 20+
    home_off_big_loss   1 if home team lost last game by 20+
    away_off_big_win    1 if away team won last game by 20+
    away_off_big_loss   1 if away team lost last game by 20+
    home_win_streak     consecutive wins entering this game (0 if on a loss streak)
    away_win_streak
    home_loss_streak    consecutive losses entering this game
    away_loss_streak

REST CLASSIFICATIONS
--------------------
    first_game  : no prior game this season (round 1 or first game after long break)
    short       : ≤6 days
    normal      : 7-9 days
    long        : 10-13 days
    bye         : 14+ days
"""

import argparse
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent.parent

# Rest classification thresholds (matches tier3_situational.py)
SHORT_MAX  = 6
NORMAL_MAX = 9
LONG_MAX   = 13
BIG_WIN_THRESHOLD  = 20
BIG_LOSS_THRESHOLD = 20

# Team name normalisation — same as bootstrap_elo_historical.py
NAME_MAP = {
    'Canterbury Bulldogs':       'Canterbury-Bankstown Bulldogs',
    'Cronulla Sharks':           'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':          'Manly-Warringah Sea Eagles',
    'North QLD Cowboys':         'North Queensland Cowboys',
    'North Queensland Cowboys':  'North Queensland Cowboys',
    'St George Dragons':         'St. George Illawarra Dragons',
    'St George Illawarra':       'St. George Illawarra Dragons',
    'Brisbane':                  'Brisbane Broncos',
    'Canberra':                  'Canberra Raiders',
    'Gold Coast':                'Gold Coast Titans',
    'Melbourne':                 'Melbourne Storm',
    'Newcastle':                 'Newcastle Knights',
    'Parramatta':                'Parramatta Eels',
    'Penrith':                   'Penrith Panthers',
    'South Sydney':              'South Sydney Rabbitohs',
    'Sydney Roosters':           'Sydney Roosters',
    'Wests Tigers':              'Wests Tigers',
    'Warriors':                  'New Zealand Warriors',
    'NZ Warriors':               'New Zealand Warriors',
    'Dolphins':                  'Dolphins',
}

def canon(name: str) -> str:
    s = str(name).strip()
    return NAME_MAP.get(s, s)


def classify_rest(days: int) -> str:
    if days <= SHORT_MAX:
        return 'short'
    if days <= NORMAL_MAX:
        return 'normal'
    if days <= LONG_MAX:
        return 'long'
    return 'bye'


def load_games(xlsx_path: str) -> list[dict]:
    """Load all games from xlsx, sorted by date."""
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl not installed. Run: pip install openpyxl", file=sys.stderr)
        sys.exit(1)

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    # Header is row index 1 (row 0 is the 'Odds Portal' banner)
    header = rows[1]

    games = []
    for row in rows[2:]:
        if not row[0]:
            continue

        raw_date = row[0]
        if hasattr(raw_date, 'date'):
            game_date = raw_date.date()
        else:
            try:
                game_date = datetime.strptime(str(raw_date)[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                continue

        home_team  = canon(str(row[2]).strip()) if row[2] else None
        away_team  = canon(str(row[3]).strip()) if row[3] else None
        venue      = str(row[4]).strip() if row[4] else ''

        # Kickoff time (col index 1) — stored as time object or string
        raw_time = row[1]
        if hasattr(raw_time, 'hour'):
            kickoff_hour = raw_time.hour
        else:
            try:
                t = datetime.strptime(str(raw_time)[:5], '%H:%M')
                kickoff_hour = t.hour
            except (ValueError, TypeError):
                kickoff_hour = 19  # default evening kickoff

        try:
            home_score = int(float(str(row[5])))
            away_score = int(float(str(row[6])))
        except (TypeError, ValueError):
            continue

        if not home_team or not away_team:
            continue

        games.append({
            'date':         game_date,
            'season':       game_date.year,
            'home_team':    home_team,
            'away_team':    away_team,
            'venue':        venue,
            'kickoff_hour': kickoff_hour,
            'home_score':   home_score,
            'away_score':   away_score,
        })

    return sorted(games, key=lambda g: g['date'])


def build_game_log(games: list[dict]) -> list[dict]:
    """
    For each game, calculate rest days and form context
    using each team's prior game history.
    """
    # Track last game info per team per season
    # Structure: {team: {'date': date, 'margin': int, 'won': bool, 'win_streak': int, 'loss_streak': int}}
    team_history = defaultdict(lambda: None)

    rows = []
    for g in games:
        h = g['home_team']
        a = g['away_team']
        d = g['date']
        season = g['season']

        # ── Rest days ──
        h_hist = team_history[h]
        a_hist = team_history[a]

        # Reset history at season boundary
        if h_hist and h_hist['season'] != season:
            h_hist = None
        if a_hist and a_hist['season'] != season:
            a_hist = None

        if h_hist:
            home_rest_days  = (d - h_hist['date']).days
            home_rest_class = classify_rest(home_rest_days)
        else:
            home_rest_days  = None
            home_rest_class = 'first_game'

        if a_hist:
            away_rest_days  = (d - a_hist['date']).days
            away_rest_class = classify_rest(away_rest_days)
        else:
            away_rest_days  = None
            away_rest_class = 'first_game'

        rest_diff = (
            (home_rest_days - away_rest_days)
            if home_rest_days is not None and away_rest_days is not None
            else None
        )

        # ── Previous game form ──
        home_prev_margin   = h_hist['margin']      if h_hist else None
        away_prev_margin   = a_hist['margin']      if a_hist else None
        home_off_big_win   = 1 if h_hist and h_hist['margin'] >= BIG_WIN_THRESHOLD  else 0
        home_off_big_loss  = 1 if h_hist and h_hist['margin'] <= -BIG_LOSS_THRESHOLD else 0
        away_off_big_win   = 1 if a_hist and a_hist['margin'] >= BIG_WIN_THRESHOLD  else 0
        away_off_big_loss  = 1 if a_hist and a_hist['margin'] <= -BIG_LOSS_THRESHOLD else 0
        home_win_streak    = h_hist['win_streak']  if h_hist else 0
        away_win_streak    = a_hist['win_streak']  if a_hist else 0
        home_loss_streak   = h_hist['loss_streak'] if h_hist else 0
        away_loss_streak   = a_hist['loss_streak'] if a_hist else 0

        # ── Game result ──
        margin = g['home_score'] - g['away_score']
        total  = g['home_score'] + g['away_score']
        home_win = 1 if margin > 0 else 0

        rows.append({
            'season':           season,
            'date':             d.strftime('%Y-%m-%d'),
            'kickoff_hour':     g['kickoff_hour'],
            'home_team':        h,
            'away_team':        a,
            'venue':            g['venue'],
            'home_score':       g['home_score'],
            'away_score':       g['away_score'],
            'actual_margin':    margin,
            'actual_total':     total,
            'home_win':         home_win,
            'home_rest_days':   home_rest_days if home_rest_days is not None else '',
            'away_rest_days':   away_rest_days if away_rest_days is not None else '',
            'rest_diff':        rest_diff      if rest_diff is not None else '',
            'home_rest_class':  home_rest_class,
            'away_rest_class':  away_rest_class,
            'home_prev_margin': home_prev_margin if home_prev_margin is not None else '',
            'away_prev_margin': away_prev_margin if away_prev_margin is not None else '',
            'home_off_big_win':  home_off_big_win,
            'home_off_big_loss': home_off_big_loss,
            'away_off_big_win':  away_off_big_win,
            'away_off_big_loss': away_off_big_loss,
            'home_win_streak':   home_win_streak,
            'away_win_streak':   away_win_streak,
            'home_loss_streak':  home_loss_streak,
            'away_loss_streak':  away_loss_streak,
        })

        # ── Update team history ──
        # Home team perspective: margin is home_score - away_score
        h_margin = margin
        h_won    = margin > 0
        team_history[h] = {
            'date':        d,
            'season':      season,
            'margin':      h_margin,
            'win_streak':  (home_win_streak + 1) if h_won else 0,
            'loss_streak': 0 if h_won else (home_loss_streak + 1),
        }

        # Away team perspective: margin is away_score - home_score
        a_margin = -margin
        a_won    = margin < 0
        team_history[a] = {
            'date':        d,
            'season':      season,
            'margin':      a_margin,
            'win_streak':  (away_win_streak + 1) if a_won else 0,
            'loss_streak': 0 if a_won else (away_loss_streak + 1),
        }

    return rows


def print_summary(rows: list[dict]):
    seasons = sorted(set(r['season'] for r in rows))
    print(f"\n  {'─'*50}")
    print(f"  Game log summary")
    print(f"  {'─'*50}")
    print(f"  Total games:     {len(rows)}")
    print(f"  Seasons:         {seasons[0]} – {seasons[-1]}")
    print(f"  {'─'*50}")

    # Rest class distribution
    from collections import Counter
    home_classes = Counter(r['home_rest_class'] for r in rows)
    print(f"\n  Home rest class distribution:")
    for cls in ['first_game', 'short', 'normal', 'long', 'bye']:
        n = home_classes.get(cls, 0)
        print(f"    {cls:<12} {n:>5} games  ({n/len(rows)*100:.1f}%)")

    print(f"\n  Big win/loss flags:")
    print(f"    home off big win:   {sum(r['home_off_big_win'] for r in rows):>5}")
    print(f"    home off big loss:  {sum(r['home_off_big_loss'] for r in rows):>5}")
    print(f"    away off big win:   {sum(r['away_off_big_win'] for r in rows):>5}")
    print(f"    away off big loss:  {sum(r['away_off_big_loss'] for r in rows):>5}")

    # Sample rows
    print(f"\n  Sample (first 3 rows):")
    for r in rows[:3]:
        print(f"    {r['date']}  {r['home_team']:<35} vs {r['away_team']:<35}  "
              f"rest: {str(r['home_rest_days']):>4} / {str(r['away_rest_days']):<4}  "
              f"class: {r['home_rest_class']}/{r['away_rest_class']}")


def main():
    parser = argparse.ArgumentParser(description='Build NRL game log with rest days')
    parser.add_argument('--xlsx', required=True, help='Path to NRL xlsx')
    parser.add_argument('--out',  default='ml/results/game_log.csv',
                        help='Output CSV path (default: ml/results/game_log.csv)')
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        print(f"ERROR: file not found: {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {xlsx_path.name} ...")
    games = load_games(str(xlsx_path))
    print(f"  {len(games)} games loaded")

    print("Building game log ...")
    rows = build_game_log(games)

    print_summary(rows)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n  Written {len(rows)} rows → {out}")
    print("\nDone.")


if __name__ == '__main__':
    main()
