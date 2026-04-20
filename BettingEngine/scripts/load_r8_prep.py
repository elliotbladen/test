#!/usr/bin/env python3
"""
scripts/load_r8_prep.py

One-shot prep script for Round 8 2026.

Loads in order:
  1. R7 results from nrl (4).xlsx
  2. Updated team style stats from team_style_stats_r8.csv  (as_of_date=2026-04-13)
  3. R8 injury totals into team_injury_totals (pre-aggregated, cap=6)
  4. R8 referee assignments into weekly_ref_assignments

Usage:
    python scripts/load_r8_prep.py [--dry-run]
"""

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).parent.parent))
import yaml

ROOT     = Path(__file__).resolve().parent.parent
DB_PATH  = ROOT / 'data' / 'model.db'

NRL_XLSX         = Path('/Users/elliotbladen/Downloads/nrl (4).xlsx')
INJURIES_JSON    = Path('/Users/elliotbladen/Downloads/injuries_r8.json')
REFEREES_CSV     = Path('/Users/elliotbladen/Downloads/referees_r8.csv')
STYLE_STATS_CSV  = Path('/Users/elliotbladen/Downloads/team_style_stats_r8.csv')

SEASON      = 2026
R7          = 7
R8          = 8
STYLE_DATE  = '2026-04-13'   # stats through end of R7
INJURY_CAP  = 6.0

NAME_MAP = {
    'Canterbury Bulldogs':      'Canterbury-Bankstown Bulldogs',
    'Cronulla Sharks':          'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':         'Manly-Warringah Sea Eagles',
    'North QLD Cowboys':        'North Queensland Cowboys',
    'St George Dragons':        'St. George Illawarra Dragons',
    'St George Illawarra Dragons': 'St. George Illawarra Dragons',
    # style stats abbreviations
    'Broncos':   'Brisbane Broncos',
    'Dragons':   'St. George Illawarra Dragons',
    'Eels':      'Parramatta Eels',
    'Cowboys':   'North Queensland Cowboys',
    'Rabbitohs': 'South Sydney Rabbitohs',
    'Bulldogs':  'Canterbury-Bankstown Bulldogs',
    'Sea Eagles':'Manly-Warringah Sea Eagles',
    'Tigers':    'Wests Tigers',
    'Sharks':    'Cronulla-Sutherland Sharks',
    'Raiders':   'Canberra Raiders',
    'Roosters':  'Sydney Roosters',
    'Panthers':  'Penrith Panthers',
    'Storm':     'Melbourne Storm',
    'Knights':   'Newcastle Knights',
    'Dolphins':  'Dolphins',
    'Warriors':  'New Zealand Warriors',
    'Titans':    'Gold Coast Titans',
}


def canon(name: str) -> str:
    return NAME_MAP.get(name.strip(), name.strip())


def sep(n=80): print('─' * n)
def header(t): print(); sep(); print(f'  {t}'); sep()
def ok(m): print(f'  ✓  {m}')
def warn(m): print(f'  ⚠  {m}')
def err(m): print(f'  ✗  {m}')


# =============================================================================
# Step 1 — R7 results
# =============================================================================

# R7 results hardcoded from nrl (4).xlsx 2026 section
# Format: (home_canonical, away_canonical, home_score, away_score)
R7_RESULTS = [
    ('Canterbury-Bankstown Bulldogs', 'Penrith Panthers',         32, 16),
    ('St. George Illawarra Dragons',  'Manly-Warringah Sea Eagles', 18, 28),
    ('Brisbane Broncos',              'North Queensland Cowboys',   31, 35),
    ('South Sydney Rabbitohs',        'Canberra Raiders',           34, 36),
    ('Cronulla-Sutherland Sharks',    'Sydney Roosters',            22, 34),
    ('Melbourne Storm',               'New Zealand Warriors',       14, 38),
    ('Parramatta Eels',               'Gold Coast Titans',          10, 52),
    ('Wests Tigers',                  'Newcastle Knights',          42, 22),
]


def step1_load_r7_results(conn, dry_run: bool):
    header('STEP 1 — Load R7 results')

    name_to_id = {r['team_name']: r['team_id']
                  for r in conn.execute('SELECT team_id, team_name FROM teams').fetchall()}

    now = datetime.utcnow().isoformat()
    written = skipped = errors = 0

    print(f'\n  {"Matchup":<60}  {"Score":>7}  {"Winner":<32}  Action')
    print(f'  {"─"*60}  {"─"*7}  {"─"*32}  {"─"*8}')

    for home_name, away_name, hs, aw in R7_RESULTS:
        home_id = name_to_id.get(home_name)
        away_id = name_to_id.get(away_name)

        if not home_id or not away_id:
            err(f'Team not found: {home_name} or {away_name}')
            errors += 1
            continue

        match_row = conn.execute('''
            SELECT match_id FROM matches
            WHERE season=? AND round_number=?
              AND home_team_id=? AND away_team_id=?
        ''', (SEASON, R7, home_id, away_id)).fetchone()

        if not match_row:
            err(f'Match not found: {home_name} vs {away_name} R{R7}')
            errors += 1
            continue

        match_id = match_row['match_id']

        # Check if already loaded
        existing = conn.execute(
            'SELECT result_id, result_status FROM results WHERE match_id=?', (match_id,)
        ).fetchone()

        if existing and existing['result_status'] == 'final':
            print(f'  {home_name + " vs " + away_name:<60}  {hs}-{aw:>2}  {"(already loaded)":<32}  SKIP')
            skipped += 1
            continue

        total = hs + aw
        margin = hs - aw
        winner_id = home_id if hs > aw else (away_id if aw > hs else None)
        winner_name = home_name if hs > aw else (away_name if aw > hs else 'Draw')

        print(f'  {home_name + " vs " + away_name:<60}  {hs}-{aw:>2}  {winner_name:<32}  {"DRY-RUN" if dry_run else "WRITE"}')

        if not dry_run:
            if existing:
                conn.execute('''
                    UPDATE results SET
                        home_score=?, away_score=?, total_score=?, margin=?,
                        winning_team_id=?, result_status='final', captured_at=?
                    WHERE match_id=?
                ''', (hs, aw, total, margin, winner_id, now, match_id))
            else:
                conn.execute('''
                    INSERT INTO results
                        (match_id, home_score, away_score, total_score, margin,
                         winning_team_id, result_status, captured_at)
                    VALUES (?,?,?,?,?,?,'final',?)
                ''', (match_id, hs, aw, total, margin, winner_id, now))
            written += 1

    if not dry_run:
        conn.commit()

    print()
    ok(f'R7 results: written={written}  skipped={skipped}  errors={errors}')
    return errors == 0


# =============================================================================
# Step 2 — Update team style stats
# =============================================================================

# Confirmed column mapping from CSV to DB
STYLE_COL_MAP = {
    'ERR':    'errors_pg',
    'PA':     'penalties_pg',
    'RMC':    'run_metres_pg',
    'LBC':    'lbc_pg',
    'MT':     'mt_pg',
    'KM':     'kick_metres_pg',
    'FDO':    'fdo_pg',
    'LB':     'lb_pg',
    'TB':     'tb_pg',
    'KRM':    'krm_pg',
    'CR_pct': 'completion_rate',   # divide by 100
}


def step2_update_style_stats(conn, dry_run: bool):
    header('STEP 2 — Update team style stats')

    name_to_id = {r['team_name']: r['team_id']
                  for r in conn.execute('SELECT team_id, team_name FROM teams').fetchall()}

    with open(STYLE_STATS_CSV, newline='') as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    print(f'\n  as_of_date={STYLE_DATE}  ({len(rows)} teams)\n')
    print(f'  {"Team":<42}  {"ERR":>5}  {"PA":>5}  {"CR":>5}  {"KM":>5}  {"RM":>6}  '
          f'{"LB":>5}  {"TB":>5}  {"MT":>5}  {"LBC":>5}  {"FDO":>5}  {"KRM":>5}  Action')
    print(f'  {"─"*42}  {"─"*5}  {"─"*5}  {"─"*5}  {"─"*5}  {"─"*6}  '
          f'{"─"*5}  {"─"*5}  {"─"*5}  {"─"*5}  {"─"*5}  {"─"*5}  {"─"*8}')

    written = skipped = errors = 0

    for row in rows:
        team_raw  = row.get('team', '').strip()
        team_name = canon(team_raw)
        team_id   = name_to_id.get(team_name)

        if not team_id:
            warn(f'Team not found: "{team_raw}" (→ "{team_name}")')
            errors += 1
            continue

        updates = {}
        for csv_col, db_col in STYLE_COL_MAP.items():
            val = row.get(csv_col, '').strip()
            if not val:
                continue
            try:
                f = float(val)
                if db_col == 'completion_rate' and f > 1.0:
                    f = f / 100.0
                updates[db_col] = round(f, 4)
            except ValueError:
                warn(f'{team_name}: cannot parse {csv_col}={val!r}')

        if not updates:
            warn(f'{team_name}: no values parsed — skipping')
            skipped += 1
            continue

        existing = conn.execute(
            'SELECT style_stat_id FROM team_style_stats WHERE team_id=? AND season=? AND as_of_date=?',
            (team_id, SEASON, STYLE_DATE)
        ).fetchone()

        action = 'UPDATE' if existing else 'INSERT'
        err_v   = updates.get('errors_pg',       '—')
        pen_v   = updates.get('penalties_pg',     '—')
        cr_v    = updates.get('completion_rate',  '—')
        km_v    = updates.get('kick_metres_pg',   '—')
        rm_v    = updates.get('run_metres_pg',    '—')
        lb_v    = updates.get('lb_pg',            '—')
        tb_v    = updates.get('tb_pg',            '—')
        mt_v    = updates.get('mt_pg',            '—')
        lbc_v   = updates.get('lbc_pg',           '—')
        fdo_v   = updates.get('fdo_pg',           '—')
        krm_v   = updates.get('krm_pg',           '—')

        marker = 'DRY-RUN' if dry_run else action
        print(f'  {team_name:<42}  {str(err_v):>5}  {str(pen_v):>5}  {str(cr_v):>5}  '
              f'{str(km_v):>5}  {str(rm_v):>6}  {str(lb_v):>5}  {str(tb_v):>5}  '
              f'{str(mt_v):>5}  {str(lbc_v):>5}  {str(fdo_v):>5}  {str(krm_v):>5}  {marker}')

        if not dry_run:
            if existing:
                set_clause = ', '.join(f'{col}=?' for col in updates)
                vals = list(updates.values()) + [existing['style_stat_id']]
                conn.execute(f'UPDATE team_style_stats SET {set_clause} WHERE style_stat_id=?', vals)
            else:
                cols = ['team_id', 'season', 'as_of_date'] + list(updates.keys())
                vals = [team_id, SEASON, STYLE_DATE] + list(updates.values())
                conn.execute(
                    f'INSERT INTO team_style_stats ({",".join(cols)}) VALUES ({",".join("?"*len(vals))})',
                    vals
                )
            written += 1

    if not dry_run:
        conn.commit()

    print()
    ok(f'Style stats: written={written}  skipped={skipped}  errors={errors}')
    return errors == 0


# =============================================================================
# Step 3 — R8 injury totals
# =============================================================================

def step3_load_injury_totals(conn, dry_run: bool):
    header('STEP 3 — Load R8 injury totals into team_injury_totals')

    with open(INJURIES_JSON) as fh:
        players = json.load(fh)

    name_to_id = {r['team_name']: r['team_id']
                  for r in conn.execute('SELECT team_id, team_name FROM teams').fetchall()}

    # Aggregate per-team, then cap at INJURY_CAP
    from collections import defaultdict
    raw_totals: dict[str, float] = defaultdict(float)
    for p in players:
        team_raw   = p.get('team', '').strip()
        team_canon = canon(team_raw)
        pts = float(p.get('injury_points', 0))
        raw_totals[team_canon] += pts

    capped = {team: min(total, INJURY_CAP) for team, total in raw_totals.items()}

    # Fetch R8 match info
    matches = conn.execute('''
        SELECT m.match_id, m.home_team_id, m.away_team_id,
               h.team_name AS home_name, a.team_name AS away_name
        FROM   matches m
        JOIN   teams h ON h.team_id = m.home_team_id
        JOIN   teams a ON a.team_id = m.away_team_id
        WHERE  m.season=? AND m.round_number=?
    ''', (SEASON, R8)).fetchall()

    now = datetime.utcnow().isoformat()
    written = 0

    print(f'\n  {"Matchup":<60}  {"H_pts":>6}  {"A_pts":>6}  Action')
    print(f'  {"─"*60}  {"─"*6}  {"─"*6}  {"─"*8}')

    for m in matches:
        matchup  = f'{m["home_name"]} vs {m["away_name"]}'
        h_pts = capped.get(m['home_name'], 0.0)
        a_pts = capped.get(m['away_name'], 0.0)

        print(f'  {matchup:<60}  {h_pts:>6.2f}  {a_pts:>6.2f}  {"DRY-RUN" if dry_run else "WRITE"}')

        if not dry_run:
            for team_id, pts in [(m['home_team_id'], h_pts), (m['away_team_id'], a_pts)]:
                existing = conn.execute(
                    'SELECT id FROM team_injury_totals WHERE match_id=? AND team_id=?',
                    (m['match_id'], team_id)
                ).fetchone()
                if existing:
                    conn.execute(
                        'UPDATE team_injury_totals SET total_injury_pts=?, source=? WHERE id=?',
                        (pts, 'load_r8_prep', existing['id'])
                    )
                else:
                    conn.execute(
                        'INSERT INTO team_injury_totals (match_id, team_id, total_injury_pts, source) VALUES (?,?,?,?)',
                        (m['match_id'], team_id, pts, 'load_r8_prep')
                    )
            written += 1

    if not dry_run:
        conn.commit()

    print()
    # Show any teams with no injury data (zero pts)
    all_r8_teams = set()
    for m in matches:
        all_r8_teams.add(m['home_name'])
        all_r8_teams.add(m['away_name'])
    zero_inj = sorted(t for t in all_r8_teams if t not in capped)
    if zero_inj:
        print(f'  Zero injury pts (clean bill of health):')
        for t in zero_inj:
            print(f'    {t}')

    ok(f'Injury totals: {written * 2} rows written (2 per match, cap={INJURY_CAP})')
    return True


# =============================================================================
# Step 4 — R8 referee assignments
# =============================================================================

def step4_load_referees(conn, dry_run: bool):
    header('STEP 4 — Load R8 referee assignments')

    with open(REFEREES_CSV, newline='') as fh:
        rows = list(csv.DictReader(fh))

    now    = datetime.utcnow().isoformat()
    ok_cnt = errors = 0

    print(f'\n  {"Matchup":<60}  {"Referee":<26}  {"Bucket":<16}  Action')
    print(f'  {"─"*60}  {"─"*26}  {"─"*16}  {"─"*8}')

    for row in rows:
        home_can = canon(row.get('home_team', '').strip())
        away_can = canon(row.get('away_team', '').strip())
        ref_name = row.get('referee', '').strip()
        matchup  = f'{home_can} vs {away_can}'

        if not home_can or not away_can or not ref_name:
            warn(f'Incomplete row: {row}')
            errors += 1
            continue

        match_row = conn.execute('''
            SELECT m.match_id, m.home_team_id, m.away_team_id
            FROM   matches m
            JOIN   teams h ON h.team_id = m.home_team_id
            JOIN   teams a ON a.team_id = m.away_team_id
            WHERE  m.season=? AND m.round_number=?
              AND  h.team_name=? AND a.team_name=?
        ''', (SEASON, R8, home_can, away_can)).fetchone()

        if not match_row:
            err(f'Match not found: {matchup}')
            errors += 1
            continue

        match_id = match_row['match_id']

        # Get or create referee
        ref_row = conn.execute(
            "SELECT referee_id FROM referees WHERE referee_name=?", (ref_name,)
        ).fetchone()
        if ref_row:
            ref_id = ref_row['referee_id']
        else:
            if not dry_run:
                conn.execute(
                    "INSERT INTO referees (referee_name) VALUES (?)", (ref_name,)
                )
                ref_id = conn.execute(
                    "SELECT referee_id FROM referees WHERE referee_name=?", (ref_name,)
                ).fetchone()['referee_id']
            else:
                ref_id = None

        # Look up bucket
        bucket = 'neutral'
        if ref_id:
            bp = conn.execute(
                'SELECT bucket FROM referee_profiles WHERE referee_id=?', (ref_id,)
            ).fetchone()
            if bp:
                bucket = bp['bucket']

        tbc_flag = ' (TBC — neutral bucket)' if ref_name == 'TBC' else ''
        print(f'  {matchup:<60}  {ref_name:<26}  {bucket:<16}  {"DRY-RUN" if dry_run else "WRITE"}{tbc_flag}')

        if not dry_run and ref_id:
            conn.execute('''
                INSERT INTO weekly_ref_assignments
                    (match_id, referee_id, season, round_number, source, created_at)
                VALUES (?,?,?,?,'load_r8_prep',?)
                ON CONFLICT(match_id) DO UPDATE SET
                    referee_id=excluded.referee_id, source=excluded.source
            ''', (match_id, ref_id, SEASON, R8, now))
            conn.execute(
                'UPDATE matches SET referee_id=? WHERE match_id=?', (ref_id, match_id)
            )
            ok_cnt += 1

    if not dry_run:
        conn.commit()

    print()
    ok(f'Referee assignments: {ok_cnt} written, {errors} errors')
    return errors == 0


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='R8 2026 prep — load results, stats, injuries, refs')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--settings', default='config/settings.yaml')
    args = parser.parse_args()

    settings = yaml.safe_load(open(args.settings))
    conn = sqlite3.connect(settings['database']['path'])
    conn.row_factory = sqlite3.Row

    print(f'\n{"═"*80}')
    print(f'  R8 prep  season={SEASON}  mode={"DRY RUN" if args.dry_run else "WRITE"}')
    print(f'{"═"*80}')

    all_ok = True
    all_ok &= step1_load_r7_results(conn, args.dry_run)
    all_ok &= step2_update_style_stats(conn, args.dry_run)
    all_ok &= step3_load_injury_totals(conn, args.dry_run)
    all_ok &= step4_load_referees(conn, args.dry_run)

    conn.close()
    print()
    if all_ok:
        ok('All prep steps complete. Run:')
        print('    python scripts/prepare_round.py --season 2026 --round 8 --skip-load --skip-weather')
    else:
        print('  ✗  Some steps had errors — check output above before running prepare_round.')


if __name__ == '__main__':
    main()
