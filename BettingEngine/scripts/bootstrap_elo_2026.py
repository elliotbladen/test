#!/usr/bin/env python3
"""
scripts/bootstrap_elo_2026.py

Multi-season ELO bootstrap: 2021 → 2022 → 2023 → 2024 → 2025 → 2026 (R1–R4).

Reads match results from two spreadsheets:
  --xlsx-hist   : nrl.xlsx     — expected to cover 2021–2024
  --xlsx-recent : nrl (2).xlsx — expected to cover 2025–2026

For each season in SEASONS, data is loaded from whichever file contains it.
Seasons with no data in either file are skipped with a warning.

FORMULA / CARRYOVER
-------------------
Identical to bootstrap_elo_multisea.py:
  K_FACTOR = 32, REVERSION_RATE = 0.25, STARTING_ELO = 1500.0

For 2026: only games strictly before CUTOFF_2026 ('2026-03-26') are used
(i.e. Rounds 1–4 only). This gives pre-Round-5 ELO ratings.

OUTPUT
------
Updates elo_rating in team_stats WHERE season=2026 AND as_of_date='2026-03-24'.
team_stats rows must already exist (run build_team_stats_2026.py first).

USAGE
-----
    cd /path/to/Betting_model
    python scripts/bootstrap_elo_2026.py [--dry-run] [--xlsx-hist PATH] [--xlsx-recent PATH]
"""

import argparse
import sqlite3
import sys
import yaml
import pandas as pd
from pathlib import Path
from datetime import date

STARTING_ELO    = 1500.0
K_FACTOR        = 20.0
REVERSION_RATE  = 0.25
SEASONS         = [2021, 2022, 2023, 2024, 2025, 2026]
CUTOFF_2026     = '2026-03-26'   # games strictly before this date for 2026
AS_OF_DATE      = '2026-03-24'
WRITE_SEASON    = 2026

XLSX_HIST_DEFAULT   = Path.home() / 'Downloads' / 'nrl.xlsx'
XLSX_RECENT_DEFAULT = Path.home() / 'Downloads' / 'nrl (2).xlsx'

# Spreadsheet team names → canonical DB team names
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
    return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 400.0))


def normalize_name(raw: str) -> str:
    return NAME_MAP.get(str(raw).strip(), str(raw).strip())


def apply_reversion(ratings: dict) -> dict:
    return {
        name: round(elo * (1.0 - REVERSION_RATE) + STARTING_ELO * REVERSION_RATE, 2)
        for name, elo in ratings.items()
    }


# =============================================================================
# Data loading
# =============================================================================

def load_df(xlsx_path: Path) -> pd.DataFrame:
    """Load an xlsx file into a DataFrame with Date parsed and year column added."""
    df = pd.read_excel(str(xlsx_path), header=1)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    df['year'] = df['Date'].dt.year
    return df


def load_season_matches(hist_dfs: list, recent_dfs: list, season: int, cutoff: str = None) -> list:
    """
    For seasons >= 2025 try recent files first (they have complete coverage).
    For earlier seasons try hist files first.
    Falls back to the other list if the preferred list has no data.
    """
    if season >= 2025:
        ordered = recent_dfs + hist_dfs
    else:
        ordered = hist_dfs + recent_dfs
    for df in ordered:
        rows = _extract_season(df, season, cutoff)
        if rows:
            return rows
    return []


def _extract_season(df: pd.DataFrame, season: int, cutoff: str = None) -> list:
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
    for m in matches:
        for team in (m['home_team'], m['away_team']):
            if team not in ratings:
                ratings[team] = STARTING_ELO
                print(f"  [new team] {team} initialised at {STARTING_ELO}")

    print(f"\n{'='*110}")
    print(f"Season {season}  —  {len(matches)} games  "
          f"(K={K_FACTOR}  reversion={REVERSION_RATE}  start from previous / {STARTING_ELO})")
    print(f"{'='*110}")
    print(f"{'Date':>10}  {'Home':>35}  {'Away':>35}  {'Score':>7}  {'ΔHome':>7}  {'ΔAway':>7}")
    print("-" * 110)

    prev_date = None
    for m in matches:
        if prev_date and m['match_date'][:7] != prev_date[:7]:
            print()
        prev_date = m['match_date']

        h, a     = m['home_team'], m['away_team']
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

def write_elo_to_db(conn, ratings: dict, name_to_id: dict, dry_run: bool) -> None:
    print(f"\n\n{'='*60}")
    if dry_run:
        print("DRY RUN — no writes to database")
    else:
        print(f"Writing ELO to team_stats "
              f"(season={WRITE_SEASON} as_of_date={AS_OF_DATE})")
    print(f"{'='*60}")

    written = 0
    skipped = 0
    for name, elo in sorted(ratings.items(), key=lambda x: -x[1]):
        team_id = name_to_id.get(name)
        if team_id is None:
            print(f"  WARNING: no team_id for '{name}' — skipping")
            skipped += 1
            continue

        row = conn.execute(
            "SELECT team_stat_id FROM team_stats "
            "WHERE team_id=? AND season=? AND as_of_date=?",
            (team_id, WRITE_SEASON, AS_OF_DATE),
        ).fetchone()

        if row is None:
            print(f"  WARNING: no team_stats row for team_id={team_id} "
                  f"season={WRITE_SEASON} as_of_date={AS_OF_DATE} — skipping. "
                  "Run build_team_stats_2026.py first.")
            skipped += 1
            continue

        if not dry_run:
            conn.execute(
                "UPDATE team_stats SET elo_rating=? WHERE team_stat_id=?",
                (round(elo, 2), row[0]),
            )
        marker = "(dry-run)" if dry_run else "written"
        print(f"  {name:<40}  elo={elo:>8.2f}  stat_id={row[0]}  {marker}")
        written += 1

    if not dry_run:
        conn.commit()
        print(f"\nCommitted {written} ELO ratings.  Skipped: {skipped}")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Multi-season ELO bootstrap: 2021 → 2026'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Print audit trail but do not write to the database')
    parser.add_argument('--settings', default='config/settings.yaml')
    parser.add_argument('--xlsx-hist',   default=str(XLSX_HIST_DEFAULT),
                        help=f'Historical xlsx covering 2021-2024 (default: {XLSX_HIST_DEFAULT})')
    parser.add_argument('--xlsx-recent', default=str(XLSX_RECENT_DEFAULT),
                        help=f'Recent xlsx covering 2025-2026 (default: {XLSX_RECENT_DEFAULT})')
    args = parser.parse_args()

    with open(args.settings) as f:
        settings = yaml.safe_load(f)
    db_path = settings.get('database', {}).get('path', 'data/model.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Build name → team_id lookup
    name_to_id = {
        row['team_name']: row['team_id']
        for row in conn.execute("SELECT team_id, team_name FROM teams").fetchall()
    }

    # Load spreadsheets into separate lists so season routing can pick the best source
    hist_dfs   = []
    recent_dfs = []
    for label, path_str, target_list in [
        ('hist',   args.xlsx_hist,   hist_dfs),
        ('recent', args.xlsx_recent, recent_dfs),
    ]:
        p = Path(path_str)
        if p.exists():
            print(f"Loading {label}: {p.name} ...")
            target_list.append(load_df(p))
        else:
            print(f"  WARNING: {label} xlsx not found: {p} — skipping")

    if not hist_dfs and not recent_dfs:
        print("ERROR: no xlsx files loaded", file=sys.stderr)
        conn.close()
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Multi-season ELO calculation
    # -------------------------------------------------------------------------
    ratings = {}

    for i, season in enumerate(SEASONS):
        cutoff = CUTOFF_2026 if season == 2026 else None
        matches = load_season_matches(hist_dfs, recent_dfs, season, cutoff=cutoff)

        if not matches:
            print(f"\nWARNING: no matches found for season {season} — skipping")
            continue

        if i == 0 or not ratings:
            print(f"\nAll teams start {season} at ELO {STARTING_ELO}")
        else:
            print(f"\n{'='*60}")
            print(f"Season boundary → start of {season}")
            print(f"Reversion: prev × {1-REVERSION_RATE} + {STARTING_ELO} × {REVERSION_RATE}")
            print(f"{'='*60}")
            before = dict(ratings)
            ratings = apply_reversion(ratings)
            print(f"  {'Team':>35}  {'End prev':>10}  {'Start {}'.format(season):>12}  {'Δ':>7}")
            for name in sorted(ratings, key=lambda n: -ratings[n]):
                end_elo   = before.get(name, STARTING_ELO)
                start_elo = ratings[name]
                print(f"  {name:>35}  {end_elo:>10.1f}  {start_elo:>12.1f}  "
                      f"{start_elo - end_elo:>+7.1f}")

        ratings = process_season(matches, ratings, season)
        print_season_table(ratings, season, label='end of')

    # -------------------------------------------------------------------------
    # Final table entering Round 5, 2026
    # -------------------------------------------------------------------------
    print(f"\n\n{'='*60}")
    print(f"Final ELO entering Round 5, 2026 (as of {AS_OF_DATE})")
    print(f"6 seasons: 2021 + 2022 + 2023 + 2024 + 2025 + 2026 R1–R4")
    print(f"{'='*60}")
    print(f"  {'Team':>35}  {'ELO':>8}  {'Δ from 1500':>13}")
    print(f"  {'-'*35}  {'-'*8}  {'-'*13}")
    for name, elo in sorted(ratings.items(), key=lambda x: -x[1]):
        delta = elo - STARTING_ELO
        print(f"  {name:>35}  {elo:>8.1f}  {delta:>+13.1f}")

    # -------------------------------------------------------------------------
    # Write to DB
    # -------------------------------------------------------------------------
    write_elo_to_db(conn, ratings, name_to_id, dry_run=args.dry_run)
    conn.close()
    print('\nDone.')


if __name__ == '__main__':
    main()
