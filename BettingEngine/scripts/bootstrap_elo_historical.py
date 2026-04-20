#!/usr/bin/env python3
"""
scripts/bootstrap_elo_historical.py

Multi-season ELO bootstrap: 2009 → 2024 (train), 2025 (test/holdout).

Reads all seasons from a single xlsx file (nrl (4).xlsx covers 2009-2026).

ERA HANDLING
------------
The NRL game changed structurally across this period. Two mechanisms handle it:

1. Era-specific K-factors
   Higher K in transition years = ratings adjust faster = old signals decay
   quicker when the game changes.

   Pre-2020 (pre-six-again):  K = 20
   2020 (six-again introduced): K = 28   ← game changed mid-season
   2021 (bedding in):          K = 24
   2022+ (modern era):         K = 20

2. Season boundary reversion
   Every off-season, all ELOs are pulled back toward 1500.
   Larger reversion at the 2020 rule-change boundary to partially reset
   pre-six-again signals.

   Standard boundary:          reversion = 0.25
   2020 rule-change boundary:  reversion = 0.40

Both are configurable below.

2025 HOLDOUT TEST
-----------------
After training through 2024, the script evaluates on 2025:
  - Predicts win/loss before each game using pre-game ELO
  - Compares predicted margin vs actual margin
  - Reports: accuracy %, MAE, and compares to naive baseline

DB WRITE
--------
After the test, writes end-of-2025 ELO ratings to team_stats as a
new snapshot (as_of_date = '2026-01-01'). prepare_round.py picks this
up as the starting ELO for the 2026 season and applies 2026 results on top.

USAGE
-----
    # Dry run — see full output, no DB writes
    python scripts/bootstrap_elo_historical.py --dry-run

    # Full run — train 2009-2024, test 2025, write to DB
    python scripts/bootstrap_elo_historical.py

    # Custom xlsx path
    python scripts/bootstrap_elo_historical.py \
        --xlsx '/Users/elliotbladen/Downloads/nrl (4).xlsx'

    # Override train/test split
    python scripts/bootstrap_elo_historical.py \
        --train-from 2012 --train-to 2024 --test-season 2025
"""

import argparse
import sqlite3
import sys
import yaml
import math
import pandas as pd
from pathlib import Path
from datetime import date
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Default config — all tuneable via command line
# ---------------------------------------------------------------------------

STARTING_ELO   = 1500.0
POINTS_PER_ELO = 0.04        # used to convert ELO diff → predicted margin

XLSX_DEFAULT   = Path.home() / 'Downloads' / 'nrl (4).xlsx'

# Era-specific K-factors
# Higher K = faster rating adjustment = older-era signals decay faster
ERA_K = {
    2009: 20, 2010: 20, 2011: 20, 2012: 20, 2013: 20,
    2014: 20, 2015: 20, 2016: 20, 2017: 20, 2018: 20,
    2019: 20,
    2020: 28,   # six-again introduced mid-season — game changed structurally
    2021: 24,   # post-six-again bedding in
    2022: 20, 2023: 20, 2024: 20, 2025: 20,
}

# Season boundary reversion rates
# Higher = stronger pull back toward 1500 = less carryover from prior season
ERA_REVERSION = {
    2020: 0.40,   # extra reset entering post-six-again era
    2021: 0.30,   # still bedding in
}
DEFAULT_REVERSION = 0.25

# ---------------------------------------------------------------------------
# Team name normalisation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ELO maths
# ---------------------------------------------------------------------------

def expected_score(r_home: float, r_away: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((r_away - r_home) / 400.0))


def predicted_margin(r_home: float, r_away: float,
                     home_advantage: float = 3.5) -> float:
    """Convert ELO differential to expected home margin."""
    return (r_home - r_away) * POINTS_PER_ELO + home_advantage


def margin_score(home_score: int, away_score: int,
                 sigmoid_k: float = 20.0) -> float:
    """
    Sigmoid-based outcome score using actual margin.
    Replaces binary 1/0 with a continuous value:
      - 40pt win  → ~0.87  (much more informative than 1.0)
      - 2pt win   → ~0.52  (barely above a coin flip)
      - draw      → 0.50
    sigmoid_k controls the steepness (lower = more sensitive to margin).
    """
    # Cap margin at 20pts — blowouts are noisy and don't reflect true quality gap
    margin = max(-20, min(20, home_score - away_score))
    return 1.0 / (1.0 + math.exp(-margin / sigmoid_k))


def apply_reversion(ratings: dict, season: int) -> dict:
    rate = ERA_REVERSION.get(season, DEFAULT_REVERSION)
    return {
        name: round(elo * (1.0 - rate) + STARTING_ELO * rate, 2)
        for name, elo in ratings.items()
    }, rate


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_xlsx(xlsx_path: str) -> pd.DataFrame:
    df = pd.read_excel(str(xlsx_path), header=1)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    df['year'] = df['Date'].dt.year
    df['home_score'] = pd.to_numeric(df['Home Score'], errors='coerce')
    df['away_score'] = pd.to_numeric(df['Away Score'], errors='coerce')
    df = df.dropna(subset=['home_score', 'away_score'])
    df['home_team'] = df['Home Team'].apply(canon)
    df['away_team'] = df['Away Team'].apply(canon)
    return df


def get_season_matches(df: pd.DataFrame, season: int) -> list:
    sub = df[df['year'] == season].sort_values('Date')
    rows = []
    for _, r in sub.iterrows():
        rows.append({
            'date':       r['Date'].strftime('%Y-%m-%d'),
            'home_team':  r['home_team'],
            'away_team':  r['away_team'],
            'home_score': int(r['home_score']),
            'away_score': int(r['away_score']),
        })
    return rows


# ---------------------------------------------------------------------------
# Training pass
# ---------------------------------------------------------------------------

def train_season(matches: list, ratings: dict, season: int,
                 verbose: bool = True) -> dict:
    k = ERA_K.get(season, 20)

    for m in matches:
        for t in (m['home_team'], m['away_team']):
            if t not in ratings:
                ratings[t] = STARTING_ELO

    if verbose:
        print(f"\n{'─'*100}")
        print(f"  TRAIN  {season}   {len(matches)} games   K={k}")
        print(f"{'─'*100}")
        print(f"  {'Date':>10}  {'Home':>35}  {'Away':>35}  {'Score':>7}  {'ΔHome':>7}")

    for m in matches:
        h, a     = m['home_team'], m['away_team']
        r_h, r_a = ratings[h], ratings[a]
        hs, aws  = m['home_score'], m['away_score']

        e_h = expected_score(r_h, r_a)
        s_h = 1.0 if hs > aws else (0.0 if hs < aws else 0.5)
        s_a = 1.0 - s_h

        delta_h = k * (s_h - e_h)
        delta_a = k * (s_a - (1.0 - e_h))

        ratings[h] = r_h + delta_h
        ratings[a] = r_a + delta_a

        if verbose:
            print(f"  {m['date']:>10}  {h:>35}  {a:>35}  "
                  f"{hs:>3}-{aws:<3}  {delta_h:>+7.2f}")

    return ratings


# ---------------------------------------------------------------------------
# Test / holdout evaluation
# ---------------------------------------------------------------------------

def evaluate_season(matches: list, ratings: dict, season: int,
                    home_advantage: float = 3.5) -> dict:
    """
    Run predictions on the holdout season.
    Ratings ARE updated as the season progresses (live ELO),
    but predictions are made BEFORE each game using pre-game ratings.
    """
    k = ERA_K.get(season, 20)

    correct_direction = 0
    margin_errors     = []
    naive_errors      = []   # baseline: always predict home wins by home_advantage
    results           = []

    print(f"\n{'═'*110}")
    print(f"  TEST / HOLDOUT   {season}   {len(matches)} games   K={k}")
    print(f"{'═'*110}")
    print(f"  {'Date':>10}  {'Home':>32}  {'Away':>32}  "
          f"{'Score':>7}  {'ActMgn':>7}  {'PredMgn':>8}  {'Err':>6}  {'Correct':>7}")
    print(f"  {'─'*10}  {'─'*32}  {'─'*32}  "
          f"{'─'*7}  {'─'*7}  {'─'*8}  {'─'*6}  {'─'*7}")

    for m in matches:
        h, a = m['home_team'], m['away_team']
        if h not in ratings:
            ratings[h] = STARTING_ELO
        if a not in ratings:
            ratings[a] = STARTING_ELO

        r_h, r_a = ratings[h], ratings[a]
        hs, aws  = m['home_score'], m['away_score']
        actual   = hs - aws

        pred     = predicted_margin(r_h, r_a, home_advantage)
        err      = abs(actual - pred)
        correct  = (pred > 0 and actual > 0) or (pred < 0 and actual < 0)

        margin_errors.append(err)
        naive_errors.append(abs(actual - home_advantage))
        if correct:
            correct_direction += 1

        results.append({
            'date':        m['date'],
            'home':        h,
            'away':        a,
            'home_score':  hs,
            'away_score':  aws,
            'actual_mgn':  actual,
            'pred_mgn':    round(pred, 1),
            'error':       round(err, 1),
            'correct':     correct,
        })

        flag = '✓' if correct else '✗'
        print(f"  {m['date']:>10}  {h:>32}  {a:>32}  "
              f"{hs:>3}-{aws:<3}  {actual:>+7}  {pred:>+8.1f}  "
              f"{err:>6.1f}  {flag:>7}")

        # Update ratings for subsequent games
        e_h     = expected_score(r_h, r_a)
        s_h     = 1.0 if hs > aws else (0.0 if hs < aws else 0.5)
        delta_h = k * (s_h - e_h)
        delta_a = k * ((1.0 - s_h) - (1.0 - e_h))
        ratings[h] = r_h + delta_h
        ratings[a] = r_a + delta_a

    n        = len(matches)
    mae      = sum(margin_errors) / n
    naive    = sum(naive_errors) / n
    acc      = correct_direction / n * 100

    print(f"\n  {'─'*60}")
    print(f"  RESULTS — {season} holdout ({n} games)")
    print(f"  {'─'*60}")
    print(f"  Win direction accuracy:   {acc:.1f}%   (naive home-always: {home_advantage:+.1f}pt baseline)")
    print(f"  Margin MAE (ELO model):   {mae:.2f} pts")
    print(f"  Margin MAE (naive):       {naive:.2f} pts   (always predict home +{home_advantage:.1f})")
    print(f"  Improvement vs naive:     {naive - mae:+.2f} pts")
    if naive > mae:
        print(f"  ✓  ELO model BEATS naive baseline on {season} holdout")
    else:
        print(f"  ✗  ELO model does NOT beat naive baseline — consider tuning K / reversion")

    return {
        'season':          season,
        'n_games':         n,
        'accuracy_pct':    round(acc, 2),
        'mae':             round(mae, 2),
        'naive_mae':       round(naive, 2),
        'improvement':     round(naive - mae, 2),
        'ratings_after':   dict(ratings),
        'game_results':    results,
    }


# ---------------------------------------------------------------------------
# Final standings table
# ---------------------------------------------------------------------------

def print_standings(ratings: dict, label: str):
    print(f"\n  {'─'*60}")
    print(f"  ELO standings — {label}")
    print(f"  {'─'*60}")
    print(f"  {'#':>3}  {'Team':<38}  {'ELO':>8}  {'Δ1500':>8}")
    for i, (name, elo) in enumerate(
        sorted(ratings.items(), key=lambda x: -x[1]), 1
    ):
        print(f"  {i:>3}  {name:<38}  {elo:>8.1f}  {elo-STARTING_ELO:>+8.1f}")


# ---------------------------------------------------------------------------
# DB write
# ---------------------------------------------------------------------------

def write_to_db(conn, ratings: dict, as_of_date: str,
                season: int, dry_run: bool):
    """
    Write final ELO ratings to team_stats as a new snapshot.
    prepare_round.py will pick this up as the starting point for the season.
    """
    name_to_id = {
        r['team_name']: r['team_id']
        for r in conn.execute("SELECT team_id, team_name FROM teams").fetchall()
    }

    print(f"\n{'═'*60}")
    if dry_run:
        print(f"  DRY RUN — DB write skipped")
    else:
        print(f"  Writing ELO snapshot → team_stats")
        print(f"  season={season}  as_of_date={as_of_date}")
    print(f"{'═'*60}")

    written = skipped = 0
    for name, elo in sorted(ratings.items(), key=lambda x: -x[1]):
        tid = name_to_id.get(name)
        if tid is None:
            print(f"  SKIP (no team_id): {name}")
            skipped += 1
            continue

        existing = conn.execute(
            "SELECT team_stat_id FROM team_stats "
            "WHERE team_id=? AND season=? AND as_of_date=?",
            (tid, season, as_of_date)
        ).fetchone()

        if not dry_run:
            if existing:
                conn.execute(
                    "UPDATE team_stats SET elo_rating=? WHERE team_stat_id=?",
                    (round(elo, 2), existing[0])
                )
                action = 'UPDATE'
            else:
                conn.execute(
                    """INSERT INTO team_stats
                       (team_id, season, as_of_date, elo_rating,
                        games_played, wins, losses, win_pct)
                       VALUES (?,?,?,?,0,0,0,0)""",
                    (tid, season, as_of_date, round(elo, 2))
                )
                action = 'INSERT'
        else:
            action = 'dry-run'

        print(f"  {name:<40}  elo={elo:>8.2f}  [{action}]")
        written += 1

    if not dry_run:
        conn.commit()
    print(f"\n  Written: {written}   Skipped: {skipped}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Historical ELO bootstrap 2009-2024, test on 2025'
    )
    parser.add_argument('--xlsx',
                        default=str(XLSX_DEFAULT),
                        help=f'Path to NRL xlsx (default: {XLSX_DEFAULT})')
    parser.add_argument('--train-from', type=int, default=2009,
                        help='First training season (default: 2009)')
    parser.add_argument('--train-to',   type=int, default=2024,
                        help='Last training season (default: 2024)')
    parser.add_argument('--test-season', type=int, default=2025,
                        help='Holdout test season (default: 2025)')
    parser.add_argument('--home-advantage', type=float, default=3.5,
                        help='Home advantage in points for margin prediction (default: 3.5)')
    parser.add_argument('--write-season', type=int, default=2026,
                        help='Season to write ELO snapshot under in DB (default: 2026)')
    parser.add_argument('--as-of-date', default='2026-01-01',
                        help='as_of_date for the DB snapshot (default: 2026-01-01)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print full output but do not write to DB')
    parser.add_argument('--quiet', action='store_true',
                        help='Suppress per-game training output (test output always shown)')
    parser.add_argument('--settings', default='config/settings.yaml')
    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # Load data
    # -------------------------------------------------------------------------
    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        print(f"ERROR: xlsx not found: {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'═'*80}")
    print(f"  bootstrap_elo_historical.py")
    print(f"  Train: {args.train_from} → {args.train_to}")
    print(f"  Test:  {args.test_season}")
    print(f"  File:  {xlsx_path.name}")
    print(f"  Mode:  {'DRY RUN' if args.dry_run else 'WRITE'}")
    print(f"{'═'*80}")

    print(f"\nLoading {xlsx_path.name} ...")
    df = load_xlsx(str(xlsx_path))

    years_in_file = sorted(df['year'].unique())
    print(f"  Years found: {years_in_file[0]} – {years_in_file[-1]}  "
          f"({len(df)} games total)")

    # -------------------------------------------------------------------------
    # Training pass: 2009 → 2024
    # -------------------------------------------------------------------------
    ratings = {}
    train_seasons = list(range(args.train_from, args.train_to + 1))

    print(f"\n{'═'*80}")
    print(f"  TRAINING PASS   {args.train_from} → {args.train_to}")
    print(f"{'═'*80}")

    for i, season in enumerate(train_seasons):
        matches = get_season_matches(df, season)
        if not matches:
            print(f"\n  WARNING: no data for {season} — skipping")
            continue

        # Season boundary reversion (not applied before the very first season)
        if i > 0 and ratings:
            ratings, rate = apply_reversion(ratings, season)
            if not args.quiet:
                print(f"\n  ── Season boundary → {season}  "
                      f"reversion={rate:.2f} ──")

        ratings = train_season(matches, ratings, season,
                               verbose=not args.quiet)

        if not args.quiet:
            print_standings(ratings, f"end of {season}")

    # Final training standings (always shown)
    print(f"\n{'═'*80}")
    print(f"  FINAL TRAINING STANDINGS — entering {args.test_season}")
    print(f"{'═'*80}")
    print_standings(ratings, f"end of {args.train_to}")

    # -------------------------------------------------------------------------
    # Test pass: 2025
    # -------------------------------------------------------------------------
    test_matches = get_season_matches(df, args.test_season)
    if not test_matches:
        print(f"\nERROR: no data for test season {args.test_season}", file=sys.stderr)
        sys.exit(1)

    # Apply reversion before test season (same as any other season boundary)
    ratings, rate = apply_reversion(ratings, args.test_season)
    print(f"\n  Season boundary reversion before {args.test_season}: rate={rate:.2f}")

    test_result = evaluate_season(
        test_matches, ratings, args.test_season, args.home_advantage
    )

    # ratings dict is now updated through end of 2025
    final_ratings = test_result['ratings_after']

    print(f"\n{'═'*80}")
    print(f"  FINAL ELO — end of {args.test_season}  (ready for {args.write_season})")
    print(f"{'═'*80}")
    print_standings(final_ratings, f"end of {args.test_season}")

    # -------------------------------------------------------------------------
    # DB write
    # -------------------------------------------------------------------------
    with open(args.settings) as f:
        settings = yaml.safe_load(f)
    db_path = settings.get('database', {}).get('path', 'data/model.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    write_to_db(
        conn, final_ratings,
        as_of_date=args.as_of_date,
        season=args.write_season,
        dry_run=args.dry_run
    )
    conn.close()

    print(f"\n{'═'*80}")
    print(f"  SUMMARY")
    print(f"{'═'*80}")
    print(f"  Training seasons:  {args.train_from} – {args.train_to}")
    print(f"  Test season:       {args.test_season}")
    print(f"  Test accuracy:     {test_result['accuracy_pct']}%")
    print(f"  Test MAE:          {test_result['mae']} pts")
    print(f"  Naive MAE:         {test_result['naive_mae']} pts")
    print(f"  Improvement:       {test_result['improvement']:+.2f} pts vs naive")
    if not args.dry_run:
        print(f"  DB snapshot:       season={args.write_season}  "
              f"as_of_date={args.as_of_date}")
    print(f"\nDone.")


if __name__ == '__main__':
    main()
