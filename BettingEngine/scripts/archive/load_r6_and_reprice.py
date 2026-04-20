#!/usr/bin/env python3
"""
scripts/load_r6_and_reprice.py

One-off pipeline:
  Task 1 — Load R6 results from aussportsbetting xlsx into DB
  Task 2 — Load closing-line market snapshots (all 2026 rounds in xlsx)
  Task 3 — Rebuild team_stats (PF/PA/GP) + ELO through R6
  Task 4 — Price R7 Tier 1 only vs market closing line
  Task 5 — Price R8 Tier 1 only

USAGE
-----
    cd /path/to/Betting_model
    python scripts/load_r6_and_reprice.py [--dry-run]
"""

import argparse
import sqlite3
import sys
import yaml
import pandas as pd
from pathlib import Path
from datetime import date, datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from pricing.tier1_baseline import compute_baseline
from db.queries import get_team_stats, get_prior_season_stats

# ─── Constants ────────────────────────────────────────────────────────────────

XLSX_PATH    = Path.home() / 'Downloads' / 'nrl (3).xlsx'
SEASON       = 2026
NEW_AS_OF    = '2026-04-07'          # after R6 last game (2026-04-06), before R7

ELO_K        = 20.0
ELO_START    = 1500.0
PRIOR_ELO_DATE = '2026-03-24'       # existing ELO snapshot (through R4)
R5_START     = '2026-03-26'         # first R5 game — not included in prior ELOs

SOURCE_NAME  = 'aussportsbetting'

# Spreadsheet → canonical DB name
NAME_MAP = {
    'Canterbury Bulldogs':   'Canterbury-Bankstown Bulldogs',
    'Cronulla Sharks':       'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':      'Manly-Warringah Sea Eagles',
    'North QLD Cowboys':     'North Queensland Cowboys',
    'St George Dragons':     'St. George Illawarra Dragons',
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def canon(name: str) -> str:
    s = str(name).strip()
    return NAME_MAP.get(s, s)


def _expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))


def sep(char='─', n=90):
    print(char * n)


def header(title: str):
    print()
    sep('═')
    print(f'  {title}')
    sep('═')


# ─── Load xlsx ────────────────────────────────────────────────────────────────

def load_xlsx() -> pd.DataFrame:
    df = pd.read_excel(str(XLSX_PATH), sheet_name='Data', header=0)
    # Row 0 contains real column headers
    df.columns = df.iloc[0].tolist()
    df = df.iloc[1:].reset_index(drop=True)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df[df['Date'].dt.year == SEASON].copy()
    df = df.sort_values('Date').reset_index(drop=True)
    df['home_canon'] = df['Home Team'].apply(canon)
    df['away_canon'] = df['Away Team'].apply(canon)
    df['match_date_str'] = df['Date'].dt.strftime('%Y-%m-%d')
    return df


# ─── Task 1: Load results ─────────────────────────────────────────────────────

def task1_load_results(conn, df: pd.DataFrame, dry_run: bool):
    header('TASK 1 — Load Results into DB')

    # Build lookup: (home_team_id, away_team_id, match_date) → match_id
    name_to_id = {
        r['team_name']: r['team_id']
        for r in conn.execute('SELECT team_id, team_name FROM teams').fetchall()
    }

    print('\n  Team name mapping confirmation:')
    print(f"  {'Spreadsheet name':<35}  {'Canonical DB name':<45}  {'team_id':>8}")
    print(f"  {'-'*35}  {'-'*45}  {'-'*8}")
    seen = set()
    for _, row in df.iterrows():
        for nm in [row['home_canon'], row['away_canon']]:
            if nm not in seen:
                tid = name_to_id.get(nm)
                flag = '' if tid else '  *** NOT FOUND ***'
                orig = NAME_MAP.get(nm, nm)
                print(f"  {orig:<35}  {nm:<45}  {str(tid):>8}{flag}")
                seen.add(nm)

    # Match lookup
    db_matches = conn.execute('''
        SELECT match_id, match_date, home_team_id, away_team_id
        FROM matches WHERE season=?
    ''', (SEASON,)).fetchall()
    match_lookup = {
        (r['home_team_id'], r['away_team_id'], r['match_date']): r['match_id']
        for r in db_matches
    }

    print(f'\n  {"Round":>6}  {"Date":>10}  {"Home":>35}  {"Away":>35}  '
          f'{"Score":>7}  {"Action":>8}')
    print(f'  {"-"*6}  {"-"*10}  {"-"*35}  {"-"*35}  {"-"*7}  {"-"*8}')

    inserted = updated = skipped = unmatched = 0

    for _, row in df.iterrows():
        home_id = name_to_id.get(row['home_canon'])
        away_id = name_to_id.get(row['away_canon'])
        mdate   = row['match_date_str']

        if home_id is None or away_id is None:
            print(f'  WARNING: cannot map team — {row["home_canon"]} / {row["away_canon"]}')
            unmatched += 1
            continue

        match_id = match_lookup.get((home_id, away_id, mdate))
        if match_id is None:
            print(f'  WARNING: no match_id for {row["home_canon"]} vs {row["away_canon"]} on {mdate}')
            unmatched += 1
            continue

        try:
            hs  = int(row['Home Score'])
            aws = int(row['Away Score'])
        except (ValueError, TypeError):
            print(f'  WARNING: invalid scores for match_id={match_id} — skipping')
            skipped += 1
            continue

        # Determine result of each game from spreadsheet round (no round col in xlsx —
        # derive from match date position)
        existing = conn.execute(
            'SELECT result_id, home_score, away_score FROM results WHERE match_id=?',
            (match_id,)
        ).fetchone()

        # Find round number for display
        rn = conn.execute(
            'SELECT round_number FROM matches WHERE match_id=?', (match_id,)
        ).fetchone()['round_number']

        if existing is None:
            action = 'INSERT'
            if not dry_run:
                conn.execute('''
                    INSERT INTO results
                        (match_id, home_score, away_score, total_score, margin,
                         winning_team_id, result_status, captured_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'final', ?)
                ''', (
                    match_id, hs, aws, hs + aws, hs - aws,
                    home_id if hs > aws else (away_id if aws > hs else None),
                    mdate,
                ))
            inserted += 1
        else:
            if existing['home_score'] == hs and existing['away_score'] == aws:
                action = 'OK'
                skipped += 1
            else:
                action = 'UPDATE'
                if not dry_run:
                    conn.execute('''
                        UPDATE results
                        SET home_score=?, away_score=?, total_score=?, margin=?,
                            winning_team_id=?
                        WHERE match_id=?
                    ''', (
                        hs, aws, hs + aws, hs - aws,
                        home_id if hs > aws else (away_id if aws > hs else None),
                        match_id,
                    ))
                updated += 1

        print(f'  {rn:>6}  {mdate:>10}  {row["home_canon"]:>35}  {row["away_canon"]:>35}  '
              f'{hs:>3}-{aws:<3}  {action:>8}')

    if not dry_run:
        conn.commit()

    print(f'\n  Summary: {inserted} inserted  |  {updated} updated  |  '
          f'{skipped} already correct  |  {unmatched} unmatched')
    if dry_run:
        print('  DRY RUN — nothing written.')


# ─── Task 2: Load market snapshots ────────────────────────────────────────────

def task2_load_snapshots(conn, df: pd.DataFrame, dry_run: bool):
    header('TASK 2 — Load Closing-Line Market Snapshots (aussportsbetting)')

    # Ensure aussportsbetting bookmaker exists
    bm_row = conn.execute(
        "SELECT bookmaker_id FROM bookmakers WHERE bookmaker_code=?",
        (SOURCE_NAME,)
    ).fetchone()
    if bm_row is None:
        if not dry_run:
            conn.execute(
                "INSERT INTO bookmakers (bookmaker_name, bookmaker_code, priority_rank) "
                "VALUES (?, ?, ?)",
                ('Aus Sports Betting', SOURCE_NAME, 2)
            )
            conn.commit()
        bm_id = conn.execute(
            "SELECT bookmaker_id FROM bookmakers WHERE bookmaker_code=?",
            (SOURCE_NAME,)
        ).fetchone()
        if bm_id:
            bm_id = bm_id['bookmaker_id']
        else:
            bm_id = 99  # dry-run placeholder
        print(f'  Created bookmaker: {SOURCE_NAME} (id={bm_id})')
    else:
        bm_id = bm_row['bookmaker_id']
        print(f'  Bookmaker {SOURCE_NAME} already exists (id={bm_id})')

    name_to_id = {
        r['team_name']: r['team_id']
        for r in conn.execute('SELECT team_id, team_name FROM teams').fetchall()
    }
    db_matches = conn.execute(
        'SELECT match_id, match_date, home_team_id, away_team_id FROM matches WHERE season=?',
        (SEASON,)
    ).fetchall()
    match_lookup = {
        (r['home_team_id'], r['away_team_id'], r['match_date']): r['match_id']
        for r in db_matches
    }

    def _float(val):
        try:
            f = float(val)
            return None if pd.isna(f) else f
        except (ValueError, TypeError):
            return None

    print(f'\n  {"Date":>10}  {"Home":>30}  {"Away":>30}  '
          f'{"H2H(h/a)":>12}  {"Line(h)":>8}  {"Total":>7}  {"Action":>8}')
    print(f'  {"-"*10}  {"-"*30}  {"-"*30}  {"-"*12}  {"-"*8}  {"-"*7}  {"-"*8}')

    snap_inserted = snap_skipped = 0

    for _, row in df.iterrows():
        home_id = name_to_id.get(row['home_canon'])
        away_id = name_to_id.get(row['away_canon'])
        mdate   = row['match_date_str']
        if home_id is None or away_id is None:
            continue

        match_id = match_lookup.get((home_id, away_id, mdate))
        if match_id is None:
            continue

        # Check for existing aussportsbetting snapshots for this match
        existing_n = conn.execute(
            'SELECT COUNT(*) FROM market_snapshots WHERE match_id=? AND bookmaker_id=?',
            (match_id, bm_id)
        ).fetchone()[0]
        if existing_n > 0:
            snap_skipped += 1
            action = 'EXISTS'
        else:
            action = 'INSERT' if not dry_run else 'DRY'

        h2h_h_close  = _float(row.get('Home Odds Close'))
        h2h_a_close  = _float(row.get('Away Odds Close'))
        line_h_close = _float(row.get('Home Line Close'))
        line_a_close = _float(row.get('Away Line Close'))
        lo_h_close   = _float(row.get('Home Line Odds Close'))
        lo_a_close   = _float(row.get('Away Line Odds Close'))
        total_close  = _float(row.get('Total Score Close'))
        over_close   = _float(row.get('Total Score Over Close'))
        under_close  = _float(row.get('Total Score Under Close'))

        print(f'  {mdate:>10}  {row["home_canon"][:30]:>30}  {row["away_canon"][:30]:>30}  '
              f'{str(h2h_h_close)+"/"+(str(h2h_a_close) if h2h_a_close else ""):>12}  '
              f'{str(line_h_close) if line_h_close is not None else "n/a":>8}  '
              f'{str(total_close) if total_close is not None else "n/a":>7}  {action:>8}')

        if dry_run or existing_n > 0:
            if existing_n > 0:
                snap_skipped += 1 if action != 'EXISTS' else 0
            continue

        captured = f'{mdate} 23:59:00'

        # H2H closing
        for sel, odds in [('home', h2h_h_close), ('away', h2h_a_close)]:
            if odds is not None:
                conn.execute('''
                    INSERT INTO market_snapshots
                        (match_id, bookmaker_id, captured_at, market_type,
                         selection_name, line_value, odds_decimal,
                         is_opening, is_closing, source_url, source_method)
                    VALUES (?,?,?,?,?,?,?,0,1,?,?)
                ''', (match_id, bm_id, captured, 'h2h', sel,
                      None, odds, 'aussportsbetting.com.au', 'manual'))

        # Handicap closing
        for sel, line, odds in [
            ('home', line_h_close, lo_h_close),
            ('away', line_a_close, lo_a_close),
        ]:
            if line is not None and odds is not None:
                conn.execute('''
                    INSERT INTO market_snapshots
                        (match_id, bookmaker_id, captured_at, market_type,
                         selection_name, line_value, odds_decimal,
                         is_opening, is_closing, source_url, source_method)
                    VALUES (?,?,?,?,?,?,?,0,1,?,?)
                ''', (match_id, bm_id, captured, 'handicap', sel,
                      line, odds, 'aussportsbetting.com.au', 'manual'))

        # Totals closing
        for sel, odds in [('over', over_close), ('under', under_close)]:
            if total_close is not None and odds is not None:
                conn.execute('''
                    INSERT INTO market_snapshots
                        (match_id, bookmaker_id, captured_at, market_type,
                         selection_name, line_value, odds_decimal,
                         is_opening, is_closing, source_url, source_method)
                    VALUES (?,?,?,?,?,?,?,0,1,?,?)
                ''', (match_id, bm_id, captured, 'total', sel,
                      total_close, odds, 'aussportsbetting.com.au', 'manual'))

        snap_inserted += 1

    if not dry_run:
        conn.commit()

    print(f'\n  Summary: {snap_inserted} matches with new snapshots  |  '
          f'{snap_skipped} already had aussportsbetting data')


# ─── Task 3a: Rebuild team_stats through R6 ───────────────────────────────────

def task3a_rebuild_team_stats(conn, dry_run: bool):
    header('TASK 3A — Rebuild team_stats through R6')
    print(f'  as_of_date = {NEW_AS_OF}  (covers R1–R6)\n')

    rows = conn.execute('''
        SELECT m.home_team_id, m.away_team_id,
               r.home_score, r.away_score,
               m.match_date
        FROM matches m
        JOIN results r ON m.match_id=r.match_id
        WHERE m.season=? AND m.match_date <= ?
          AND r.home_score IS NOT NULL AND r.away_score IS NOT NULL
        ORDER BY m.match_date, m.match_id
    ''', (SEASON, '2026-04-06')).fetchall()

    print(f'  {len(rows)} matches with results through 2026-04-06')

    pf   = defaultdict(list)
    pa   = defaultdict(list)
    h_pf = defaultdict(list)
    h_pa = defaultdict(list)
    a_pf = defaultdict(list)
    a_pa = defaultdict(list)
    wins = defaultdict(int)

    for r in rows:
        hid = r['home_team_id']
        aid = r['away_team_id']
        hs  = r['home_score']
        aws = r['away_score']
        pf[hid].append(hs); pa[hid].append(aws)
        pf[aid].append(aws); pa[aid].append(hs)
        h_pf[hid].append(hs); h_pa[hid].append(aws)
        a_pf[aid].append(aws); a_pa[aid].append(hs)
        if hs > aws: wins[hid] += 1
        elif aws > hs: wins[aid] += 1

    name_map = {
        r['team_id']: r['team_name']
        for r in conn.execute('SELECT team_id, team_name FROM teams').fetchall()
    }

    def avg(lst): return round(sum(lst)/len(lst), 4) if lst else None

    stats = {}
    for tid in set(pf.keys()):
        gp = len(pf[tid])
        w  = wins[tid]
        stats[tid] = {
            'gp': gp, 'wins': w, 'losses': gp - w,
            'win_pct': round(w/gp, 4),
            'pf': avg(pf[tid]), 'pa': avg(pa[tid]),
            'h_pf': avg(h_pf[tid]), 'h_pa': avg(h_pa[tid]),
            'a_pf': avg(a_pf[tid]), 'a_pa': avg(a_pa[tid]),
            '_diff': sum(pf[tid]) - sum(pa[tid]),
        }

    ranked = sorted(stats, key=lambda t: (-stats[t]['wins'], -stats[t]['_diff']))
    for pos, tid in enumerate(ranked, 1):
        stats[tid]['pos'] = pos

    print(f'\n  {"#":>3}  {"Team":<42}  {"GP":>3}  {"W":>2}  {"L":>2}  '
          f'{"PF/g":>6}  {"PA/g":>6}  {"Diff":>6}  {"Action":>8}')
    print(f'  {"─"*3}  {"─"*42}  {"─"*3}  {"─"*2}  {"─"*2}  '
          f'{"─"*6}  {"─"*6}  {"─"*6}  {"─"*8}')

    for tid in ranked:
        s = stats[tid]
        name = name_map.get(tid, f'id={tid}')

        existing = conn.execute(
            'SELECT team_stat_id FROM team_stats WHERE team_id=? AND season=? AND as_of_date=?',
            (tid, SEASON, NEW_AS_OF)
        ).fetchone()
        action = 'UPDATE' if existing else 'INSERT'

        diff = round(s['_diff'] / s['gp'], 1) if s['gp'] else 0

        print(f'  {s["pos"]:>3}  {name:<42}  {s["gp"]:>3}  {s["wins"]:>2}  {s["losses"]:>2}  '
              f'{s["pf"]:>6.1f}  {s["pa"]:>6.1f}  {diff:>+6.1f}  '
              f'{"(dry)" if dry_run else action:>8}')

        if dry_run:
            continue

        if existing:
            conn.execute('''
                UPDATE team_stats SET
                    games_played=?, wins=?, losses=?, win_pct=?, ladder_position=?,
                    points_for_avg=?, points_against_avg=?,
                    home_points_for_avg=?, home_points_against_avg=?,
                    away_points_for_avg=?, away_points_against_avg=?
                WHERE team_stat_id=?
            ''', (s['gp'], s['wins'], s['losses'], s['win_pct'], s['pos'],
                  s['pf'], s['pa'], s['h_pf'], s['h_pa'], s['a_pf'], s['a_pa'],
                  existing['team_stat_id']))
        else:
            conn.execute('''
                INSERT INTO team_stats (
                    team_id, season, as_of_date,
                    games_played, wins, losses, win_pct, ladder_position,
                    points_for_avg, points_against_avg,
                    home_points_for_avg, home_points_against_avg,
                    away_points_for_avg, away_points_against_avg,
                    elo_rating, attack_rating, defence_rating, recent_form_rating,
                    run_metres_pg, post_contact_metres_pg, completion_rate,
                    errors_pg, penalties_pg, kick_metres_pg, ruck_speed_score
                ) VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                    NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL
                )
            ''', (tid, SEASON, NEW_AS_OF,
                  s['gp'], s['wins'], s['losses'], s['win_pct'], s['pos'],
                  s['pf'], s['pa'], s['h_pf'], s['h_pa'], s['a_pf'], s['a_pa']))

    if not dry_run:
        conn.commit()
        print(f'\n  Committed {len(stats)} team_stats rows at as_of_date={NEW_AS_OF}')


# ─── Task 3b: Update ELO through R6 ──────────────────────────────────────────

def task3b_update_elo(conn, dry_run: bool):
    header('TASK 3B — Update ELO through R6')
    print(f'  Strategy: load existing R4 ELOs → apply R5+R6 results (K={ELO_K})\n')

    # Load existing ELO ratings from prior snapshot (through R4)
    prior_rows = conn.execute('''
        SELECT ts.team_id, ts.elo_rating, t.team_name
        FROM team_stats ts
        JOIN teams t ON ts.team_id=t.team_id
        WHERE ts.season=? AND ts.as_of_date=?
          AND ts.elo_rating IS NOT NULL
    ''', (SEASON, PRIOR_ELO_DATE)).fetchall()

    ratings = {r['team_id']: r['elo_rating'] for r in prior_rows}
    id_to_name = {r['team_id']: r['team_name'] for r in prior_rows}

    print(f'  Loaded {len(ratings)} team ELOs from {PRIOR_ELO_DATE} (R4 entry):')
    for tid, elo in sorted(ratings.items(), key=lambda x: -x[1]):
        print(f'    {id_to_name[tid]:<42}  {elo:.2f}')

    # Load R5 + R6 results
    new_games = conn.execute('''
        SELECT m.match_id, m.match_date, m.home_team_id, m.away_team_id,
               r.home_score, r.away_score,
               th.team_name as home_team, ta.team_name as away_team,
               m.round_number
        FROM matches m
        JOIN results r ON m.match_id=r.match_id
        JOIN teams th ON m.home_team_id=th.team_id
        JOIN teams ta ON m.away_team_id=ta.team_id
        WHERE m.season=? AND m.match_date >= ? AND m.match_date <= ?
          AND r.home_score IS NOT NULL
        ORDER BY m.match_date ASC, m.match_id ASC
    ''', (SEASON, R5_START, '2026-04-06')).fetchall()

    print(f'\n  Applying {len(new_games)} R5+R6 games:\n')
    print(f'  {"Rnd":>4}  {"Date":>10}  {"Home":>35}  {"Away":>35}  '
          f'{"Score":>7}  {"ΔHome":>7}  {"ΔAway":>7}')
    print(f'  {"─"*4}  {"─"*10}  {"─"*35}  {"─"*35}  {"─"*7}  {"─"*7}  {"─"*7}')

    for g in new_games:
        hid = g['home_team_id']
        aid = g['away_team_id']
        hs  = g['home_score']
        aws = g['away_score']

        # New teams default to starting ELO
        if hid not in ratings:
            ratings[hid] = ELO_START
            id_to_name[hid] = g['home_team']
        if aid not in ratings:
            ratings[aid] = ELO_START
            id_to_name[aid] = g['away_team']

        r_h = ratings[hid]
        r_a = ratings[aid]
        e_h = _expected(r_h, r_a)
        s_h = 1.0 if hs > aws else (0.0 if hs < aws else 0.5)
        s_a = 1.0 - s_h

        d_h = ELO_K * (s_h - e_h)
        d_a = ELO_K * (s_a - (1.0 - e_h))

        ratings[hid] = r_h + d_h
        ratings[aid] = r_a + d_a

        print(f'  {g["round_number"]:>4}  {g["match_date"]:>10}  '
              f'{g["home_team"]:>35}  {g["away_team"]:>35}  '
              f'{hs:>3}-{aws:<3}  {d_h:>+7.2f}  {d_a:>+7.2f}')

    # Print final ELO table
    print(f'\n  Final ELO ratings (R7 entry):\n')
    print(f'  {"#":>3}  {"Team":<42}  {"ELO":>8}  {"Δ from 1500":>12}')
    print(f'  {"─"*3}  {"─"*42}  {"─"*8}  {"─"*12}')
    for pos, (tid, elo) in enumerate(sorted(ratings.items(), key=lambda x: -x[1]), 1):
        delta = elo - ELO_START
        print(f'  {pos:>3}  {id_to_name.get(tid, f"id={tid}"):<42}  '
              f'{elo:>8.2f}  {delta:>+12.2f}')

    # Write ELOs to the new team_stats rows
    if not dry_run:
        written = 0
        for tid, elo in ratings.items():
            row = conn.execute(
                'SELECT team_stat_id FROM team_stats WHERE team_id=? AND season=? AND as_of_date=?',
                (tid, SEASON, NEW_AS_OF)
            ).fetchone()
            if row:
                conn.execute(
                    'UPDATE team_stats SET elo_rating=? WHERE team_stat_id=?',
                    (round(elo, 2), row['team_stat_id'])
                )
                written += 1
            else:
                print(f'  WARNING: no team_stats row at {NEW_AS_OF} for team_id={tid} — ELO not written')
        conn.commit()
        print(f'\n  ELO written to {written} team_stats rows at as_of_date={NEW_AS_OF}')
    else:
        print('\n  DRY RUN — ELO not written.')


# ─── T1-only pricing helper ───────────────────────────────────────────────────

def price_t1_only(conn, round_number: int, tiers_cfg: dict) -> list:
    """Compute T1 baseline for every match in a given round. Returns list of dicts."""
    t1_cfg = tiers_cfg.get('tier1_baseline', {})

    matches = conn.execute('''
        SELECT m.match_id, m.match_date, m.round_number, m.season,
               m.home_team_id, m.away_team_id,
               h.team_name as home_team, a.team_name as away_team
        FROM matches m
        JOIN teams h ON m.home_team_id=h.team_id
        JOIN teams a ON m.away_team_id=a.team_id
        WHERE m.season=? AND m.round_number=?
        ORDER BY m.match_date, m.match_id
    ''', (SEASON, round_number)).fetchall()

    results = []
    for m in matches:
        hs = get_team_stats(conn, m['home_team_id'], SEASON, m['match_date']) or {}
        as_ = get_team_stats(conn, m['away_team_id'], SEASON, m['match_date']) or {}
        hp  = get_prior_season_stats(conn, m['home_team_id'], SEASON)
        ap  = get_prior_season_stats(conn, m['away_team_id'], SEASON)

        t1 = compute_baseline(hs, as_, {}, t1_cfg,
                              home_prior_stats=hp, away_prior_stats=ap)

        # Fetch closing handicap line from market_snapshots
        mkt = conn.execute('''
            SELECT ms.selection_name, ms.line_value, ms.odds_decimal,
                   b.bookmaker_name
            FROM market_snapshots ms
            JOIN bookmakers b ON ms.bookmaker_id=b.bookmaker_id
            WHERE ms.match_id=? AND ms.market_type='handicap' AND ms.is_closing=1
            ORDER BY b.priority_rank ASC, ms.snapshot_id DESC
        ''', (m['match_id'],)).fetchall()

        mkt_h2h = conn.execute('''
            SELECT ms.selection_name, ms.odds_decimal, b.bookmaker_name
            FROM market_snapshots ms
            JOIN bookmakers b ON ms.bookmaker_id=b.bookmaker_id
            WHERE ms.match_id=? AND ms.market_type='h2h' AND ms.is_closing=1
            ORDER BY b.priority_rank ASC, ms.snapshot_id DESC
        ''', (m['match_id'],)).fetchall()

        # Extract home handicap line
        market_line = None
        market_source = None
        for r in mkt:
            if r['selection_name'] == 'home' and r['line_value'] is not None:
                market_line   = r['line_value']
                market_source = r['bookmaker_name']
                break

        h2h_home = h2h_away = None
        for r in mkt_h2h:
            if r['selection_name'] == 'home': h2h_home = r['odds_decimal']
            if r['selection_name'] == 'away': h2h_away = r['odds_decimal']

        results.append({
            'match_id':      m['match_id'],
            'round':         m['round_number'],
            'date':          m['match_date'],
            'home':          m['home_team'],
            'away':          m['away_team'],
            't1_margin':     t1['baseline_margin'],
            't1_home_pts':   t1['baseline_home_points'],
            't1_away_pts':   t1['baseline_away_points'],
            'market_line':   market_line,
            'market_source': market_source,
            'h2h_home':      h2h_home,
            'h2h_away':      h2h_away,
        })
    return results


def print_pricing_table(records: list, title: str):
    print(f'\n  {"Matchup":<52}  {"T1 Mrg":>7}  {"Mkt Line":>9}  '
          f'{"Diff":>6}  {"H2H":>10}  {"Source"}')
    print(f'  {"─"*52}  {"─"*7}  {"─"*9}  {"─"*6}  {"─"*10}  {"─"*20}')

    for r in records:
        t1  = r['t1_margin']
        mkt = r['market_line']
        diff_str = f'{t1 - mkt:>+6.1f}' if mkt is not None else '   n/a'
        mkt_str  = f'{mkt:>+9.1f}' if mkt is not None else '      n/a'
        h2h_str  = f'{r["h2h_home"]}/{r["h2h_away"]}' if r['h2h_home'] else 'n/a'
        src      = r['market_source'] or '—'
        label    = f'{r["home"][:24]} vs {r["away"][:24]}'
        print(f'  {label:<52}  {t1:>+7.1f}  {mkt_str}  {diff_str}  {h2h_str:>10}  {src}')


# ─── Task 4: Price R7 T1 only ─────────────────────────────────────────────────

def task4_price_r7(conn, tiers_cfg: dict):
    header('TASK 4 — Round 7 Tier 1 Only (vs Market Closing Line)')
    print('  T2 and T3 disabled — raw Tier 1 baseline only.\n')

    records = price_t1_only(conn, 7, tiers_cfg)

    if not any(r['market_line'] for r in records):
        print('  NOTE: No closing-line handicap data found for R7 in market_snapshots.')
        print('        R7 games start 2026-04-10; closing lines are not in the R1-R6 xlsx.')
        print('        Showing T1 margins only — load R7 market data to complete the comparison.\n')

    print_pricing_table(records, 'Round 7')

    # Summary stats where market data exists
    with_market = [r for r in records if r['market_line'] is not None]
    if with_market:
        diffs = [r['t1_margin'] - r['market_line'] for r in with_market]
        avg_diff = sum(diffs) / len(diffs)
        abs_avg  = sum(abs(d) for d in diffs) / len(diffs)
        print(f'\n  Games with market data: {len(with_market)}/{len(records)}')
        print(f'  Mean T1 vs market diff:  {avg_diff:>+.2f} pts')
        print(f'  Mean absolute diff:       {abs_avg:>.2f} pts')


# ─── Task 5: Price R8 T1 only ─────────────────────────────────────────────────

def task5_price_r8(conn, tiers_cfg: dict):
    header('TASK 5 — Round 8 Tier 1 Only')
    print('  T2 and T3 disabled — raw Tier 1 baseline only.\n')
    records = price_t1_only(conn, 8, tiers_cfg)
    print_pricing_table(records, 'Round 8')


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Load R6 results, rebuild ratings, reprice R7/R8')
    parser.add_argument('--dry-run',  action='store_true')
    parser.add_argument('--settings', default='config/settings.yaml')
    args = parser.parse_args()

    settings  = yaml.safe_load(open(args.settings))
    tiers_cfg = yaml.safe_load(open('config/tiers.yaml'))
    db_path   = settings.get('database', {}).get('path', 'data/model.db')

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')

    mode = 'DRY RUN' if args.dry_run else 'WRITE'
    print(f'\n{"═"*90}')
    print(f'  load_r6_and_reprice.py   mode={mode}   db={db_path}')
    print(f'{"═"*90}')

    # Load spreadsheet once
    print(f'\n  Loading xlsx: {XLSX_PATH.name} ...')
    df = load_xlsx()
    print(f'  {len(df)} 2026 rows found (R1–R6)')

    task1_load_results(conn, df, args.dry_run)
    task2_load_snapshots(conn, df, args.dry_run)
    task3a_rebuild_team_stats(conn, args.dry_run)
    task3b_update_elo(conn, args.dry_run)
    task4_price_r7(conn, tiers_cfg)
    task5_price_r8(conn, tiers_cfg)

    conn.close()
    print(f'\n{"═"*90}')
    print(f'  Done.  {"(DRY RUN — nothing written)" if args.dry_run else "All writes committed."}')
    print(f'{"═"*90}\n')


if __name__ == '__main__':
    main()
