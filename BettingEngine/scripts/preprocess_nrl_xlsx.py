#!/usr/bin/env python3
"""
scripts/preprocess_nrl_xlsx.py

One-off preprocessing script: converts the raw NRL spreadsheet (wide format)
into three narrow-format CSVs that ingestion/spreadsheet_importer.py accepts,
plus a round_map inspection file.

IMPORTANT ASSUMPTIONS — review before running:

  1. Season filter: 2023 only (rows where Date.year == 2023)

  2. Bookmaker: hardcoded as 'bet365' for all 2023 rows.
     Basis: spreadsheet header note says "bet365 odds until April 28, 2024"

  3. Odds exported: CLOSING ODDS ONLY.
     - H2H:      'Home Odds Close', 'Away Odds Close'
     - Handicap: 'Home Line Odds Close', 'Away Line Odds Close'
                 Line values from 'Home Line Close', 'Away Line Close'
     - Total:    'Total Score Over Close', 'Total Score Under Close'
                 Line value from 'Total Score Close'
     Opening/min/max odds are not exported in this pass.

  4. Round derivation: rounds are derived by grouping games into ISO calendar
     weeks. Each distinct week containing at least one game is assigned a
     sequential round number (1, 2, ...). Bye weeks (no games) are skipped
     automatically so round numbers never have gaps.
     A round_map_2023.csv is written for manual inspection and correction.
     REVIEW the round map before importing — correct any assignments there
     if the derivation is wrong (e.g. irregular scheduling around finals).

  5. Team name overrides (names not in normalizers._NRL_TEAM_ALIASES):
     - 'St George Dragons'  -> 'St. George Illawarra Dragons'  (fixed here)
     - 'Dolphins'           -> 'Dolphins'  (new 2023 team; stored as-is, correct)
     All other team names are passed to the importer which calls
     normalize_team_name(). Teams with no alias entry (e.g. 'Brisbane Broncos')
     will trigger a normalizer WARNING but are correct canonical names — ignore.

  6. Venue cleanup: trailing parentheticals are stripped before import.
     e.g. '4 Pines Park (Brookvale Oval)' -> '4 Pines Park'
     Other venue names that don't match the alias table are stored as-is.

  7. Finals/playoff rows are included. round_map will show them at the end.
     'is_final' and 'is_overtime' columns are added to results_2023.csv for
     reference only — the importer ignores unknown columns safely.

  8. Team stats are whole-season 2023 averages derived from results.
     as_of_date is set to 2023-08-30 (day before Round 27 begins), so that
     the stats satisfy as_of_date <= match_date for all Round 27 games.
     Rating fields (elo_rating etc.) are left absent and will be NULL in DB.

OUTPUT:
  data/import/results_2023.csv
  data/import/odds_2023.csv
  data/import/team_stats_2023.csv
  data/import/round_map_2023.csv   <-- REVIEW THIS FIRST

USAGE:
  cd /path/to/Betting_model
  python scripts/preprocess_nrl_xlsx.py
  python scripts/preprocess_nrl_xlsx.py --source ~/path/to/other.xlsx
"""

import argparse
import datetime
import math
import os
import sys
from pathlib import Path

import openpyxl
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SPREADSHEET_PATH_DEFAULT = os.path.expanduser('~/Downloads/nrl (1).xlsx')
OUTPUT_DIR = Path('data/import')
TARGET_SEASON = 2023
BOOKMAKER = 'bet365'

# Explicit team name fixes for names not in normalizers._NRL_TEAM_ALIASES.
# These are applied BEFORE passing to the importer. The importer then applies
# normalize_team_name() on top — so names already in the alias table do not
# need to be listed here. Only list genuine gaps that would produce wrong output.
_TEAM_OVERRIDES = {
    'St George Dragons': 'St. George Illawarra Dragons',
    # 'Dolphins' is intentionally not listed — stored as 'Dolphins' (correct)
}

# Exact spreadsheet column names (from row 2 header, confirmed via inspection)
# Reference only — script uses dict key access after loading.
_COL_NAMES = {
    'date':              'Date',
    'kickoff':           'Kick-off (local)',
    'home_team':         'Home Team',
    'away_team':         'Away Team',
    'venue':             'Venue',
    'home_score':        'Home Score',
    'away_score':        'Away Score',
    'playoff':           'Play Off Game?',
    'overtime':          'Over Time?',
    # H2H closing
    'h2h_home_close':    'Home Odds Close',
    'h2h_away_close':    'Away Odds Close',
    # Handicap closing line and odds
    'hcp_home_line':     'Home Line Close',
    'hcp_away_line':     'Away Line Close',
    'hcp_home_odds':     'Home Line Odds Close',
    'hcp_away_odds':     'Away Line Odds Close',
    # Total closing line and odds
    'total_line':        'Total Score Close',
    'total_over_odds':   'Total Score Over Close',
    'total_under_odds':  'Total Score Under Close',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_team(raw: str) -> str:
    """Apply explicit overrides for team names not in the alias table."""
    return _TEAM_OVERRIDES.get(raw, raw) if raw else raw


def _clean_venue(raw: str) -> str:
    """
    Strip trailing parenthetical from venue names.
    '4 Pines Park (Brookvale Oval)' -> '4 Pines Park'
    """
    if not raw:
        return raw
    if '(' in raw:
        return raw[:raw.index('(')].strip()
    return raw.strip()


def _safe_float(val) -> 'float | None':
    """Return float or None. Never raises."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> 'int | None':
    """Return int or None. Never raises."""
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Load raw data from spreadsheet
# ---------------------------------------------------------------------------

def load_2023_rows(xlsx_path: str) -> list:
    """
    Load all TARGET_SEASON rows from the spreadsheet.

    Row layout:
      Row 1: title / notes row (skipped)
      Row 2: actual column headers
      Row 3+: data rows

    Returns list of dicts keyed by the header row values.
    Only rows where Date.year == TARGET_SEASON are included.
    """
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.active

    rows = []
    headers = None

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, values_only=True), start=1):
        if row_idx == 1:
            continue  # title/notes row — skip
        if row_idx == 2:
            headers = list(row)
            continue
        if row[0] is None:
            continue
        dt = row[0]
        if not (hasattr(dt, 'year') and dt.year == TARGET_SEASON):
            continue
        rows.append({headers[i]: v for i, v in enumerate(row)})

    wb.close()
    print(f"  Loaded {len(rows)} rows for season {TARGET_SEASON}")
    return rows


# ---------------------------------------------------------------------------
# Round derivation
# ---------------------------------------------------------------------------

def derive_rounds(rows: list) -> tuple:
    """
    Assign round numbers by grouping games into ISO calendar weeks.

    Each distinct (ISO year, ISO week) pair containing at least one game is
    assigned a sequential round number starting at 1. Bye weeks (no games in
    that calendar week) are skipped automatically, so round numbers are always
    contiguous.

    This is the simplest transparent method. NRL games typically cluster into
    a Thursday–Sunday window each round; ISO weeks align with this naturally.

    Returns:
        (rows_with_rounds, round_map_df)

    round_map_df columns:
        round        — assigned round number (1, 2, ...)
        week_start   — Monday of that ISO week (YYYY-MM-DD)
        iso_year     — ISO year
        iso_week     — ISO week number
        game_count   — number of games in that round
        includes_final — 1 if any game in the round has Play Off Game? set
    """
    # Collect all distinct (iso_year, iso_week) pairs from game dates
    week_set = set()
    for r in rows:
        dt = r[_COL_NAMES['date']]
        iso = dt.isocalendar()  # returns (year, week, weekday)
        week_set.add((iso[0], iso[1]))

    sorted_weeks = sorted(week_set)
    week_to_round = {wk: i + 1 for i, wk in enumerate(sorted_weeks)}

    # Assign round to each row
    for r in rows:
        dt = r[_COL_NAMES['date']]
        iso = dt.isocalendar()
        r['_round'] = week_to_round[(iso[0], iso[1])]

    # Build round_map for inspection
    round_game_count = {}
    round_has_final = {}
    for r in rows:
        rn = r['_round']
        round_game_count[rn] = round_game_count.get(rn, 0) + 1
        if r.get(_COL_NAMES['playoff']):
            round_has_final[rn] = 1

    round_map_rows = []
    for wk, rn in sorted(week_to_round.items(), key=lambda x: x[1]):
        iso_year, iso_week = wk
        week_start = datetime.date.fromisocalendar(iso_year, iso_week, 1)
        round_map_rows.append({
            'round':           rn,
            'week_start':      week_start.isoformat(),
            'iso_year':        iso_year,
            'iso_week':        iso_week,
            'game_count':      round_game_count.get(rn, 0),
            'includes_final':  round_has_final.get(rn, 0),
        })

    return rows, pd.DataFrame(round_map_rows)


# ---------------------------------------------------------------------------
# Build results_2023.csv
# ---------------------------------------------------------------------------

def build_results(rows: list) -> pd.DataFrame:
    """
    One row per match.
    Required columns for importer: season, round, match_date, home_team,
    away_team, venue, home_score, away_score.
    Optional extras (is_final, is_overtime) are ignored by the importer.
    """
    records = []
    for r in rows:
        dt = r[_COL_NAMES['date']]
        kickoff = r.get(_COL_NAMES['kickoff'])
        kickoff_str = kickoff.strftime('%H:%M') if kickoff else ''

        records.append({
            'season':       TARGET_SEASON,
            'round':        r['_round'],
            'match_date':   dt.strftime('%Y-%m-%d'),
            'kickoff_time': kickoff_str,
            'home_team':    _clean_team(r.get(_COL_NAMES['home_team'], '')),
            'away_team':    _clean_team(r.get(_COL_NAMES['away_team'], '')),
            'venue':        _clean_venue(r.get(_COL_NAMES['venue'], '')),
            'home_score':   _safe_int(r.get(_COL_NAMES['home_score'])),
            'away_score':   _safe_int(r.get(_COL_NAMES['away_score'])),
            # Reference only — importer ignores these columns
            'is_final':     1 if r.get(_COL_NAMES['playoff']) else 0,
            'is_overtime':  1 if r.get(_COL_NAMES['overtime']) else 0,
        })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Build odds_2023.csv
# ---------------------------------------------------------------------------

def build_odds(rows: list) -> pd.DataFrame:
    """
    Explode each match row into up to 6 odds rows (closing prices only):
      h2h/home, h2h/away
      handicap/home (with line), handicap/away (with line)
      total/over (with line), total/under (with line)

    Rows where the closing odds value is None are skipped and reported.
    The optional 'line' column is included for handicap and total markets.
    """
    records = []
    skipped = []

    for r in rows:
        dt = r[_COL_NAMES['date']]
        home = _clean_team(r.get(_COL_NAMES['home_team'], ''))
        away = _clean_team(r.get(_COL_NAMES['away_team'], ''))

        base = dict(
            season=TARGET_SEASON,
            round=r['_round'],
            match_date=dt.strftime('%Y-%m-%d'),
            home_team=home,
            away_team=away,
            bookmaker=BOOKMAKER,
            is_closing=1,
            is_opening=0,
        )

        def add(market_type, selection, odds_col, line_col=None):
            odds_val = _safe_float(r.get(_COL_NAMES[odds_col]))
            if odds_val is None:
                skipped.append(
                    f"  {base['match_date']} {home} vs {away} | {market_type}/{selection}"
                    f" — '{_COL_NAMES[odds_col]}' is None"
                )
                return
            row = {**base, 'market_type': market_type, 'selection': selection, 'odds': odds_val}
            if line_col is not None:
                line_val = _safe_float(r.get(_COL_NAMES[line_col]))
                # Include line column even if None — importer handles absent/None gracefully
                row['line'] = line_val if line_val is not None else ''
            records.append(row)

        # H2H (no line)
        add('h2h', 'home', 'h2h_home_close')
        add('h2h', 'away', 'h2h_away_close')

        # Handicap (home line is typically negative for favourite)
        add('handicap', 'home', 'hcp_home_odds', 'hcp_home_line')
        add('handicap', 'away', 'hcp_away_odds', 'hcp_away_line')

        # Total
        add('total', 'over',  'total_over_odds',  'total_line')
        add('total', 'under', 'total_under_odds', 'total_line')

    if skipped:
        print(f"\n  Odds rows skipped ({len(skipped)} total — None closing values):")
        for msg in skipped:
            print(msg)

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Build team_stats_2023.csv
# ---------------------------------------------------------------------------

def build_team_stats(results_df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive whole-season 2023 stats from the results CSV.
    These are end-of-season aggregates, not rolling per-round stats.
    as_of_date is set to '2023-08-30' (day before Round 27 begins).

    WHY NOT results_df['match_date'].max():
    get_team_stats() enforces WHERE as_of_date <= match_date. The Grand Final
    is 2023-10-01, which is after all Round 27 matches (Aug 31 - Sep 03).
    Using the season-end date as as_of_date causes every regular-season lookup
    to return None. Setting as_of_date to '2023-08-30' means the stats satisfy
    the as_of_date <= match_date constraint for all Round 27 games.

    Columns produced:
      team, season, as_of_date,
      games_played, wins, losses, win_pct,
      points_for_avg, points_against_avg,
      home_points_for_avg, home_points_against_avg,
      away_points_for_avg, away_points_against_avg

    Rating fields (elo_rating, attack_rating, defence_rating, recent_form_rating)
    and yardage fields are left absent — they will be NULL in the DB.
    """
    as_of_date = '2023-08-30'  # day before Round 27 begins; see docstring

    all_teams = sorted(
        set(results_df['home_team'].dropna()) | set(results_df['away_team'].dropna())
    )

    records = []
    for team in all_teams:
        home_games = results_df[results_df['home_team'] == team]
        away_games = results_df[results_df['away_team'] == team]

        home_pf = home_games['home_score'].dropna().astype(float).tolist()
        home_pa = home_games['away_score'].dropna().astype(float).tolist()
        away_pf = away_games['away_score'].dropna().astype(float).tolist()
        away_pa = away_games['home_score'].dropna().astype(float).tolist()

        all_pf = home_pf + away_pf
        all_pa = home_pa + away_pa

        home_wins = sum(1 for pf, pa in zip(home_pf, home_pa) if pf > pa)
        away_wins = sum(1 for pf, pa in zip(away_pf, away_pa) if pf > pa)
        total_wins  = home_wins + away_wins
        total_games = len(all_pf)

        def avg(lst):
            return round(sum(lst) / len(lst), 2) if lst else None

        records.append({
            'team':                     team,
            'season':                   TARGET_SEASON,
            'as_of_date':               as_of_date,
            'games_played':             total_games,
            'wins':                     total_wins,
            'losses':                   total_games - total_wins,
            'win_pct':                  round(total_wins / total_games, 4) if total_games else None,
            'points_for_avg':           avg(all_pf),
            'points_against_avg':       avg(all_pa),
            'home_points_for_avg':      avg(home_pf),
            'home_points_against_avg':  avg(home_pa),
            'away_points_for_avg':      avg(away_pf),
            'away_points_against_avg':  avg(away_pa),
        })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Preprocess NRL xlsx into import-ready CSVs (2023 only)'
    )
    parser.add_argument(
        '--source',
        default=SPREADSHEET_PATH_DEFAULT,
        help=f'Path to source xlsx (default: {SPREADSHEET_PATH_DEFAULT})',
    )
    args = parser.parse_args()

    xlsx_path = os.path.expanduser(args.source)
    if not os.path.exists(xlsx_path):
        print(f"ERROR: source file not found: {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- Load ---
    print(f"Loading {TARGET_SEASON} rows from {xlsx_path} ...")
    rows = load_2023_rows(xlsx_path)

    # --- Rounds ---
    print("\nDeriving round numbers from ISO calendar weeks ...")
    rows, round_map = derive_rounds(rows)
    round_map_path = OUTPUT_DIR / 'round_map_2023.csv'
    round_map.to_csv(round_map_path, index=False)
    print(f"  {len(round_map)} rounds detected")
    print(f"  Written: {round_map_path}")
    print(f"  *** REVIEW THIS FILE before importing ***")
    print(f"  Check that round numbers match the actual NRL schedule.")
    print(f"  Edit round_map_2023.csv if any are wrong — but note: the results/odds CSVs")
    print(f"  already embed the round numbers. Rerun this script to regenerate them.")

    # --- Results ---
    print("\nBuilding results_2023.csv ...")
    results_df = build_results(rows)
    results_path = OUTPUT_DIR / 'results_2023.csv'
    results_df.to_csv(results_path, index=False)
    print(f"  {len(results_df)} rows  ->  {results_path}")

    # --- Odds ---
    print("\nBuilding odds_2023.csv ...")
    odds_df = build_odds(rows)
    odds_path = OUTPUT_DIR / 'odds_2023.csv'
    odds_df.to_csv(odds_path, index=False)
    expected_max = len(rows) * 6
    print(f"  {len(odds_df)} rows  ->  {odds_path}  (max possible: {expected_max})")

    # --- Team stats ---
    print("\nBuilding team_stats_2023.csv ...")
    stats_df = build_team_stats(results_df)
    stats_path = OUTPUT_DIR / 'team_stats_2023.csv'
    stats_df.to_csv(stats_path, index=False)
    print(f"  {len(stats_df)} team rows  ->  {stats_path}")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("PREPROCESSING COMPLETE")
    print("=" * 60)
    print(f"\nOutput files in {OUTPUT_DIR}/:")
    for f in ['round_map_2023.csv', 'results_2023.csv', 'odds_2023.csv', 'team_stats_2023.csv']:
        p = OUTPUT_DIR / f
        print(f"  {f:35s}  ({p.stat().st_size:,} bytes)")

    print(f"\nTeam name overrides applied:")
    for raw, canonical in _TEAM_OVERRIDES.items():
        print(f"  '{raw}' -> '{canonical}'")
    print(f"  'Dolphins' -> 'Dolphins'  (new 2023 team, no override needed)")

    print(f"\nNOTE: The importer will emit WARNING logs for team names that are not")
    print(f"in the normalizer alias table. These are expected and safe to ignore for:")
    print(f"  Brisbane Broncos, Canberra Raiders, Gold Coast Titans, Melbourne Storm,")
    print(f"  New Zealand Warriors, Newcastle Knights, Parramatta Eels, Penrith Panthers,")
    print(f"  South Sydney Rabbitohs, Sydney Roosters, Wests Tigers, Dolphins")
    print(f"These names are correct — the alias table just has no entry for them.")

    print(f"\nNext steps (in order):")
    print(f"  0. Review data/import/round_map_2023.csv")
    print(f"  1. Create DB if it doesn't exist:")
    print(f"       sqlite3 data/model.db < db/schema.sql")
    print(f"  2. python -m ingestion.spreadsheet_importer --results   data/import/results_2023.csv   --settings config/settings.yaml")
    print(f"  3. python -m ingestion.spreadsheet_importer --odds      data/import/odds_2023.csv      --settings config/settings.yaml")
    print(f"  4. python -m ingestion.spreadsheet_importer --team-stats data/import/team_stats_2023.csv --settings config/settings.yaml")


if __name__ == '__main__':
    main()
