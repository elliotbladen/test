#!/usr/bin/env python3
"""
scripts/load_seasons_2025_2026.py

Load 2025 (full season) and 2026 Rounds 1-5 match results and betting odds
from nrl (2).xlsx into the database.

Steps:
  1. Read nrl (2).xlsx — filters for years 2025 and 2026
  2. Derive round numbers using ISO calendar weeks (same method as preprocess_nrl_xlsx.py)
  3. Write intermediate CSVs to data/import/ for auditability
  4. Import results (matches + results table) via spreadsheet_importer
  5. Import odds (market_snapshots) via spreadsheet_importer

IDEMPOTENCY:
  - Matches are deduplicated on (season, round, home_team_id, away_team_id)
  - Odds import is skipped if closing snapshots already exist for that season
    (market_snapshots is append-only — re-running without this guard creates duplicates)

USAGE:
  cd /path/to/Betting_model
  python scripts/load_seasons_2025_2026.py [--dry-run] [--xlsx PATH]
"""

import argparse
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import yaml

SPREADSHEET_DEFAULT = Path.home() / 'Downloads' / 'nrl (2).xlsx'
OUTPUT_DIR          = Path('data/import')
TARGET_SEASONS      = [2025, 2026]
BOOKMAKER           = 'bet365'

# Explicit overrides for names not in the normalizer alias table
_TEAM_OVERRIDES = {
    'St George Dragons':    'St. George Illawarra Dragons',
    'North QLD Cowboys':    'North Queensland Cowboys',
    'Cronulla Sharks':      'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':     'Manly-Warringah Sea Eagles',
    'Canterbury Bulldogs':  'Canterbury-Bankstown Bulldogs',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_team(raw) -> str:
    s = str(raw).strip() if raw else ''
    return _TEAM_OVERRIDES.get(s, s)


def _clean_venue(raw) -> str:
    if not raw:
        return ''
    s = str(raw).strip()
    return s[:s.index('(')].strip() if '(' in s else s


def _safe_float(val):
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _safe_int(val):
    if val is None:
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Load + derive rounds
# ---------------------------------------------------------------------------

def load_xlsx(xlsx_path: Path) -> list:
    df = pd.read_excel(str(xlsx_path), header=1)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    df = df[df['Date'].dt.year.isin(TARGET_SEASONS)].copy()
    rows = df.to_dict('records')
    print(f'  Loaded {len(rows)} rows for seasons {TARGET_SEASONS} from {xlsx_path.name}')
    return rows


def derive_rounds(rows: list) -> list:
    """
    Assign round numbers within each season using ISO calendar weeks.
    Each distinct (iso_year, iso_week) pair gets a sequential round number,
    restarting at 1 for each season.
    """
    from collections import defaultdict
    season_groups = defaultdict(list)
    for r in rows:
        season_groups[int(r['Date'].year)].append(r)

    result = []
    for season in sorted(season_groups):
        s_rows = season_groups[season]
        week_set = set()
        for r in s_rows:
            iso = r['Date'].isocalendar()
            week_set.add((iso[0], iso[1]))
        sorted_weeks = sorted(week_set)
        week_to_round = {wk: i + 1 for i, wk in enumerate(sorted_weeks)}
        for r in s_rows:
            iso = r['Date'].isocalendar()
            r['_round']  = week_to_round[(iso[0], iso[1])]
            r['_season'] = season
            result.append(r)
        print(f'  Season {season}: {len(s_rows)} games → {len(sorted_weeks)} rounds '
              f'(R1={sorted_weeks[0]}, R{len(sorted_weeks)}={sorted_weeks[-1]})')
    return result


# ---------------------------------------------------------------------------
# Build DataFrames
# ---------------------------------------------------------------------------

def build_results_df(rows: list) -> pd.DataFrame:
    records = []
    for r in rows:
        hs  = _safe_int(r.get('Home Score'))
        aws = _safe_int(r.get('Away Score'))
        if hs is None or aws is None:
            continue
        dt = r['Date']
        ko = r.get('Kick-off (local)')
        if hasattr(ko, 'strftime'):
            ko_str = ko.strftime('%H:%M')
        elif ko and str(ko).strip() not in ('', 'nan'):
            ko_str = str(ko).strip()[:5]
        else:
            ko_str = ''
        records.append({
            'season':       r['_season'],
            'round':        r['_round'],
            'match_date':   dt.strftime('%Y-%m-%d'),
            'kickoff_time': ko_str,
            'home_team':    _clean_team(r.get('Home Team')),
            'away_team':    _clean_team(r.get('Away Team')),
            'venue':        _clean_venue(r.get('Venue')),
            'home_score':   hs,
            'away_score':   aws,
            'is_final':     1 if r.get('Play Off Game?') else 0,
            'is_overtime':  1 if r.get('Over Time?') else 0,
        })
    return pd.DataFrame(records)


def build_odds_df(rows: list) -> pd.DataFrame:
    COLS = {
        'h2h_home':     'Home Odds Close',
        'h2h_away':     'Away Odds Close',
        'hcp_home_o':   'Home Line Odds Close',
        'hcp_away_o':   'Away Line Odds Close',
        'hcp_home_l':   'Home Line Close',
        'hcp_away_l':   'Away Line Close',
        'tot_over':     'Total Score Over Close',
        'tot_under':    'Total Score Under Close',
        'tot_line':     'Total Score Close',
    }
    records = []
    skipped = 0
    for r in rows:
        dt   = r['Date']
        home = _clean_team(r.get('Home Team'))
        away = _clean_team(r.get('Away Team'))
        base = dict(
            season=r['_season'], round=r['_round'],
            match_date=dt.strftime('%Y-%m-%d'),
            home_team=home, away_team=away,
            bookmaker=BOOKMAKER, is_closing=1, is_opening=0,
        )

        def add(mtype, sel, o_key, l_key=None):
            nonlocal skipped
            odds = _safe_float(r.get(COLS[o_key]))
            if odds is None:
                skipped += 1
                return
            row = {**base, 'market_type': mtype, 'selection': sel, 'odds': odds}
            if l_key:
                line = _safe_float(r.get(COLS[l_key]))
                row['line'] = line if line is not None else ''
            records.append(row)

        add('h2h', 'home', 'h2h_home')
        add('h2h', 'away', 'h2h_away')
        add('handicap', 'home', 'hcp_home_o', 'hcp_home_l')
        add('handicap', 'away', 'hcp_away_o', 'hcp_away_l')
        add('total',    'over',  'tot_over',   'tot_line')
        add('total',    'under', 'tot_under',  'tot_line')

    if skipped:
        print(f'  Odds rows skipped: {skipped} (None closing values)')
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# DB state check
# ---------------------------------------------------------------------------

def db_state(conn, season: int) -> dict:
    m = conn.execute('SELECT COUNT(*) FROM matches WHERE season=?', (season,)).fetchone()[0]
    s = conn.execute(
        'SELECT COUNT(*) FROM market_snapshots ms '
        'JOIN matches m ON m.match_id=ms.match_id WHERE m.season=?', (season,)
    ).fetchone()[0]
    return {'matches': m, 'snapshots': s}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Load 2025+2026 NRL data into DB')
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse and validate only — no DB writes')
    parser.add_argument('--xlsx', default=str(SPREADSHEET_DEFAULT),
                        help=f'Path to xlsx (default: {SPREADSHEET_DEFAULT})')
    parser.add_argument('--settings', default='config/settings.yaml')
    parser.add_argument('--force', action='store_true',
                        help='Re-import results even if already in DB')
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        print(f'ERROR: xlsx not found: {xlsx_path}', file=sys.stderr)
        sys.exit(1)

    with open(args.settings) as f:
        settings = yaml.safe_load(f)
    db_path = settings.get('database', {}).get('path', 'data/model.db')
    conn    = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # --- Current state ---
    print('=== Current DB state ===')
    for s in TARGET_SEASONS:
        st = db_state(conn, s)
        print(f'  {s}: {st["matches"]} matches, {st["snapshots"]} market_snapshots')

    # --- Load + process ---
    print(f'\nLoading xlsx ...')
    rows = load_xlsx(xlsx_path)
    rows = derive_rounds(rows)

    print('\nBuilding DataFrames ...')
    results_df = build_results_df(rows)
    odds_df    = build_odds_df(rows)

    # --- Write CSVs ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for season in TARGET_SEASONS:
        tag = f'2026_r1_r5' if season == 2026 else str(season)
        r_sub = results_df[results_df['season'] == season]
        o_sub = odds_df[odds_df['season'] == season]
        rp = OUTPUT_DIR / f'results_{tag}.csv'
        op = OUTPUT_DIR / f'odds_{tag}.csv'
        r_sub.to_csv(rp, index=False)
        o_sub.to_csv(op, index=False)
        print(f'  {season}: {len(r_sub)} results → {rp}  |  {len(o_sub)} odds → {op}')

    if args.dry_run:
        print('\nDRY RUN — no DB imports performed')

        # Show league avg for info
        for season in TARGET_SEASONS:
            sub = results_df[results_df['season'] == season]
            if len(sub):
                all_scores = list(sub['home_score']) + list(sub['away_score'])
                avg = sum(all_scores) / len(all_scores)
                print(f'  {season} league avg per team: {avg:.2f}  (total avg: {avg*2:.2f})')
        conn.close()
        return

    # --- Import ---
    sys.path.insert(0, '.')
    from ingestion.spreadsheet_importer import (
        import_historical_results,
        import_historical_odds,
    )

    for season in TARGET_SEASONS:
        tag  = f'2026_r1_r5' if season == 2026 else str(season)
        rp   = OUTPUT_DIR / f'results_{tag}.csv'
        op   = OUTPUT_DIR / f'odds_{tag}.csv'
        st   = db_state(conn, season)

        # Results
        if st['matches'] > 0 and not args.force:
            print(f'\n  {season}: {st["matches"]} matches already loaded — skip results (--force to override)')
        else:
            print(f'\nImporting results for {season} ...')
            res = import_historical_results(conn, str(rp))
            print(f'  imported={res["imported"]}  skipped={res["skipped"]}  errors={res["errors"]}')
            for e in res.get('error_detail', [])[:5]:
                print(f'    ERROR: {e}')
            conn.commit()

        # Odds (append-only guard)
        st2 = db_state(conn, season)
        if st2['snapshots'] > 0:
            print(f'\n  {season}: {st2["snapshots"]} market_snapshots already loaded — skip odds')
        else:
            print(f'\nImporting odds for {season} ...')
            res = import_historical_odds(conn, str(op))
            print(f'  imported={res["imported"]}  skipped={res["skipped"]}  errors={res["errors"]}')
            for e in res.get('error_detail', [])[:5]:
                print(f'    ERROR: {e}')
            conn.commit()

    # --- Final state ---
    print('\n=== Final DB state ===')
    for s in TARGET_SEASONS:
        st = db_state(conn, s)
        print(f'  {s}: {st["matches"]} matches, {st["snapshots"]} market_snapshots')

    conn.close()
    print('\nDone.')


if __name__ == '__main__':
    main()
