#!/usr/bin/env python3
"""
scripts/bootstrap_elo_multisea.py

Multi-season ELO bootstrap: 2021 → 2022 → 2023.

Reads raw match results directly from the NRL source spreadsheet, processes
all three seasons in chronological order, applies mean reversion between
seasons, and writes the final 2023 pre-Round-27 ELO ratings into
team_stats.elo_rating.

FORMULA
-------
Standard ELO, binary win/loss (same as bootstrap_elo_2023.py):

    E_home = 1 / (1 + 10 ^ ((R_away - R_home) / 400))
    E_away = 1 - E_home

    new_R_home = R_home + K * (S_home - E_home)
    new_R_away = R_away + K * (S_away - E_away)

    S = 1.0 (win), 0.5 (draw), 0.0 (loss)

CARRYOVER RULE
--------------
At the end of each season (after the last game of that season is processed),
before starting the next season, apply mean reversion:

    new_start = prev_end * (1 - REVERSION_RATE) + STARTING_ELO * REVERSION_RATE

With REVERSION_RATE = 0.25:
    - Retains 75% of earned signal.
    - Pulls 25% back toward 1500 (average).
    - A team at 1650 enters next season at 1650*0.75 + 1500*0.25 = 1612.5.
    - A team at 1350 enters next season at 1350*0.75 + 1500*0.25 = 1387.5.

ASSUMPTIONS
-----------
1. All teams start 2021 at STARTING_ELO = 1500.
2. K_FACTOR = 32.
3. No home advantage in the ELO update step (added separately at price time).
4. Binary W/L only — no margin-of-victory adjustment in V1.
5. 2021 and 2022: all regular-season games included (no finals in source data).
6. 2023: games strictly before CUTOFF_DATE = '2023-08-31' only.
7. New team (Dolphins, entered 2023): starts at STARTING_ELO = 1500.
8. Source file is read directly from xlsx — 2021/2022 data is not in the DB.

OUTPUT
------
Updates elo_rating in team_stats WHERE season=2023 AND as_of_date='2023-08-30'.
Prints full audit trail including per-season summaries and the carryover table.

USAGE
-----
    cd /path/to/Betting_model
    python scripts/bootstrap_elo_multisea.py [--dry-run] [--xlsx PATH]
"""

import argparse
import sqlite3
import sys
import yaml
import pandas as pd
from pathlib import Path
from datetime import date


# =============================================================================
# Constants
# =============================================================================

STARTING_ELO    = 1500.0
K_FACTOR        = 32.0
REVERSION_RATE  = 0.25        # 25% mean reversion at each season boundary
SEASONS         = [2021, 2022, 2023]
CUTOFF_2023     = '2023-08-31'  # 2023 games strictly before this date only
AS_OF_DATE      = '2023-08-30'  # must match as_of_date in team_stats
WRITE_SEASON    = 2023

# Spreadsheet team names → canonical DB team names
# Only entries that differ from the canonical name are listed.
NAME_MAP = {
    'Canterbury Bulldogs':  'Canterbury-Bankstown Bulldogs',
    'Cronulla Sharks':      'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':     'Manly-Warringah Sea Eagles',
    'North QLD Cowboys':    'North Queensland Cowboys',
    'St George Dragons':    'St. George Illawarra Dragons',
}


# =============================================================================
# Helpers
# =============================================================================

def expected_score(r_a: float, r_b: float) -> float:
    """ELO expected score for team A vs team B at a neutral venue."""
    return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 400.0))


def normalize_name(raw: str) -> str:
    """Map spreadsheet team name to canonical DB name."""
    return NAME_MAP.get(str(raw).strip(), str(raw).strip())


def apply_reversion(ratings: dict) -> dict:
    """
    Apply mean reversion to all ratings at a season boundary.
    Returns a new dict of reverted ratings.
    """
    return {
        name: round(elo * (1.0 - REVERSION_RATE) + STARTING_ELO * REVERSION_RATE, 2)
        for name, elo in ratings.items()
    }


# =============================================================================
# Data loading
# =============================================================================

def load_xlsx_season(df: pd.DataFrame, season: int, cutoff: str = None) -> list:
    """
    Extract match rows for a given season from the pre-loaded DataFrame.

    Returns a list of dicts: {match_date, home_team, away_team, home_score, away_score}.
    Rows with missing scores are excluded.
    If cutoff is given, only rows strictly before that date are returned.
    """
    mask = df['year'] == season
    if cutoff:
        mask &= df['Date'].dt.date < date.fromisoformat(cutoff)
    sub = df[mask].copy()
    sub = sub.dropna(subset=['Home Score', 'Away Score'])
    sub = sub[sub['Home Score'].apply(lambda x: str(x).strip() not in ('', 'nan'))]
    sub = sub[sub['Away Score'].apply(lambda x: str(x).strip() not in ('', 'nan'))]
    sub['home_score'] = pd.to_numeric(sub['Home Score'], errors='coerce')
    sub['away_score'] = pd.to_numeric(sub['Away Score'], errors='coerce')
    sub = sub.dropna(subset=['home_score', 'away_score'])
    rows = []
    for _, row in sub.sort_values('Date').iterrows():
        rows.append({
            'match_date': row['Date'].strftime('%Y-%m-%d'),
            'home_team':  normalize_name(row['Home Team']),
            'away_team':  normalize_name(row['Away Team']),
            'home_score': int(row['home_score']),
            'away_score': int(row['away_score']),
        })
    return rows


# =============================================================================
# ELO engine
# =============================================================================

def process_season(matches: list, ratings: dict, season: int) -> dict:
    """
    Run ELO updates for one season's matches.

    Any team not already in ratings is initialised at STARTING_ELO.
    Returns the updated ratings dict.
    """
    # Ensure all teams in this season have a rating
    for m in matches:
        for team in (m['home_team'], m['away_team']):
            if team not in ratings:
                ratings[team] = STARTING_ELO
                print(f"  [new team] {team} initialised at {STARTING_ELO}")

    print(f"\n{'='*110}")
    print(f"Season {season}  —  {len(matches)} games  "
          f"(K={K_FACTOR}  reversion={REVERSION_RATE}  start from previous season / {STARTING_ELO})")
    print(f"{'='*110}")
    print(f"{'Date':>10}  {'Home':>35}  {'Away':>35}  {'Score':>7}  {'ΔHome':>7}  {'ΔAway':>7}")
    print("-" * 110)

    prev_date = None
    for m in matches:
        if prev_date and m['match_date'][:7] != prev_date[:7]:
            print()   # blank line between months for readability
        prev_date = m['match_date']

        h, a   = m['home_team'], m['away_team']
        r_h, r_a = ratings[h], ratings[a]
        hs, aws  = m['home_score'], m['away_score']

        e_h = expected_score(r_h, r_a)
        e_a = 1.0 - e_h

        if hs > aws:
            s_h, s_a = 1.0, 0.0
        elif hs < aws:
            s_h, s_a = 0.0, 1.0
        else:
            s_h, s_a = 0.5, 0.5

        delta_h = K_FACTOR * (s_h - e_h)
        delta_a = K_FACTOR * (s_a - e_a)

        ratings[h] = r_h + delta_h
        ratings[a] = r_a + delta_a

        print(
            f"{m['match_date']:>10}  {h:>35}  {a:>35}  "
            f"{hs:>3}-{aws:<3}  {delta_h:>+7.2f}  {delta_a:>+7.2f}"
        )

    return ratings


def print_season_table(ratings: dict, season: int, label: str = '') -> None:
    """Print a ranked ELO table for a season end/start state."""
    header = f"ELO ratings — {label} season {season}"
    print(f"\n{'-'*60}")
    print(header)
    print(f"  {'Team':>35}  {'ELO':>8}  {'Δ from start':>13}")
    print(f"  {'-'*35}  {'-'*8}  {'-'*13}")
    for name, elo in sorted(ratings.items(), key=lambda x: -x[1]):
        delta = elo - STARTING_ELO
        print(f"  {name:>35}  {elo:>8.1f}  {delta:>+13.1f}")


# =============================================================================
# DB write
# =============================================================================

def write_elo_to_db(
    conn: sqlite3.Connection,
    ratings: dict,
    name_to_id: dict,
    dry_run: bool,
) -> None:
    """
    UPDATE elo_rating in team_stats for WRITE_SEASON / AS_OF_DATE.
    """
    print(f"\n\n{'='*60}")
    if dry_run:
        print("DRY RUN — no writes to database")
    else:
        print(f"Writing multi-season ELO to team_stats "
              f"(season={WRITE_SEASON} as_of_date={AS_OF_DATE})")
    print(f"{'='*60}")

    for name, elo in sorted(ratings.items(), key=lambda x: -x[1]):
        team_id = name_to_id.get(name)
        if team_id is None:
            print(f"  WARNING: no team_id found for '{name}' — skipping")
            continue

        row = conn.execute(
            "SELECT team_stat_id FROM team_stats "
            "WHERE team_id=? AND season=? AND as_of_date=?",
            (team_id, WRITE_SEASON, AS_OF_DATE),
        ).fetchone()

        if row is None:
            print(f"  WARNING: no team_stats row for team_id={team_id} "
                  f"season={WRITE_SEASON} as_of_date={AS_OF_DATE} — skipping")
            continue

        if not dry_run:
            conn.execute(
                "UPDATE team_stats SET elo_rating=? WHERE team_stat_id=?",
                (round(elo, 2), row[0]),
            )

        marker = "(dry-run)" if dry_run else "written"
        print(f"  {name:<40}  elo={elo:>8.2f}  stat_id={row[0]}  {marker}")

    if not dry_run:
        conn.commit()
        print("\nCommitted.")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Multi-season ELO bootstrap: 2021 → 2022 → 2023'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Print audit trail but do not write to the database')
    parser.add_argument('--settings', default='config/settings.yaml',
                        help='Path to settings.yaml (default: config/settings.yaml)')
    parser.add_argument('--xlsx', default='/Users/elliotbladen/Downloads/nrl.xlsx',
                        help='Path to NRL source spreadsheet')
    args = parser.parse_args()

    settings_path = Path(args.settings)
    if not settings_path.exists():
        print(f"ERROR: settings file not found: {settings_path}", file=sys.stderr)
        sys.exit(1)

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        print(f"ERROR: xlsx file not found: {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    with open(settings_path) as f:
        settings = yaml.safe_load(f)

    db_path = settings.get('database', {}).get('path', 'data/model.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Build name → team_id lookup from DB
    name_to_id = {
        row['team_name']: row['team_id']
        for row in conn.execute("SELECT team_id, team_name FROM teams").fetchall()
    }

    # Load spreadsheet
    print(f"Loading {xlsx_path} ...")
    df = pd.read_excel(xlsx_path, header=1)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    df['year'] = df['Date'].dt.year

    # -------------------------------------------------------------------------
    # Multi-season ELO calculation
    # -------------------------------------------------------------------------
    ratings = {}   # team_name → elo (float)
    before_carryover = {}   # for printing the carryover table

    for i, season in enumerate(SEASONS):
        cutoff = CUTOFF_2023 if season == 2023 else None
        matches = load_xlsx_season(df, season, cutoff=cutoff)
        if not matches:
            print(f"ERROR: no matches found for season {season}", file=sys.stderr)
            sys.exit(1)

        if i == 0:
            # First season: everyone starts at STARTING_ELO
            print(f"\nAll teams start 2021 at ELO {STARTING_ELO}")
        else:
            # Subsequent seasons: carry over with reversion
            print(f"\n{'='*60}")
            print(f"Season boundary: end of {SEASONS[i-1]} → start of {season}")
            print(f"Reversion rate: {REVERSION_RATE} "
                  f"(new = prev × {1-REVERSION_RATE} + {STARTING_ELO} × {REVERSION_RATE})")
            print(f"{'='*60}")
            print(f"  {'Team':>35}  {'End {}'.format(SEASONS[i-1]):>10}  "
                  f"{'Start {}'.format(season):>10}  {'Δ':>7}")
            before_carryover = dict(ratings)
            ratings = apply_reversion(ratings)
            for name in sorted(ratings, key=lambda n: -ratings[n]):
                end_elo   = before_carryover.get(name, STARTING_ELO)
                start_elo = ratings[name]
                print(f"  {name:>35}  {end_elo:>10.1f}  {start_elo:>10.1f}  "
                      f"{start_elo - end_elo:>+7.1f}")

        ratings = process_season(matches, ratings, season)
        print_season_table(ratings, season, label='end of')

    # -------------------------------------------------------------------------
    # Final table entering Round 27, 2023
    # -------------------------------------------------------------------------
    print(f"\n\n{'='*60}")
    print(f"Final ELO entering Round 27, 2023 (as of {AS_OF_DATE})")
    print(f"3 seasons: 2021 + 2022 + 2023 Rounds 1–26")
    print(f"{'='*60}")
    print(f"  {'Team':>35}  {'ELO':>8}  {'Δ from 1500':>13}")
    print(f"  {'-'*35}  {'-'*8}  {'-'*13}")
    for name, elo in sorted(ratings.items(), key=lambda x: -x[1]):
        delta = elo - STARTING_ELO
        print(f"  {name:>35}  {elo:>8.1f}  {delta:>+13.1f}")

    # -------------------------------------------------------------------------
    # Compare with single-season ratings (from existing team_stats)
    # -------------------------------------------------------------------------
    print(f"\n\n{'='*60}")
    print("Comparison: single-season (current DB) vs multi-season")
    print(f"{'='*60}")
    print(f"  {'Team':>35}  {'Single-sea':>11}  {'Multi-sea':>10}  {'Δ':>7}")
    print(f"  {'-'*35}  {'-'*11}  {'-'*10}  {'-'*7}")
    db_elos = {
        row['team_name']: row['elo_rating']
        for row in conn.execute(
            "SELECT t.team_name, ts.elo_rating "
            "FROM team_stats ts JOIN teams t ON t.team_id = ts.team_id "
            "WHERE ts.season=? AND ts.as_of_date=?",
            (WRITE_SEASON, AS_OF_DATE)
        ).fetchall()
    }
    for name, elo in sorted(ratings.items(), key=lambda x: -x[1]):
        old = db_elos.get(name)
        old_str = f"{old:.1f}" if old else "n/a"
        delta_str = f"{elo - old:+.1f}" if old else "n/a"
        print(f"  {name:>35}  {old_str:>11}  {elo:>10.1f}  {delta_str:>7}")

    # -------------------------------------------------------------------------
    # Write to DB
    # -------------------------------------------------------------------------
    write_elo_to_db(conn, ratings, name_to_id, dry_run=args.dry_run)
    conn.close()


if __name__ == '__main__':
    main()
