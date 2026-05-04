#!/usr/bin/env python3
"""
scripts/fetch_fox_teamstats.py
==============================
Fetches per-match team stats from the Fox Sports Stats API and stores them in:
  - ml/data/match_stats/{season}/NRL{year}{round:02d}{match:02d}.json  (raw JSON)
  - DB table: match_team_stats

API: statsapi.foxsports.com.au/3.0/api
Key: embedded in Fox Sports public JS bundle (public, read-only)

USAGE
-----
Full backfill (2022–current):
    python scripts/fetch_fox_teamstats.py --seasons 2022 2023 2024 2025 2026

Single season:
    python scripts/fetch_fox_teamstats.py --seasons 2026

Single round:
    python scripts/fetch_fox_teamstats.py --seasons 2026 --round 10

Dry run (fetch + save JSON only, no DB write):
    python scripts/fetch_fox_teamstats.py --seasons 2022 --dry-run

Skip already-fetched matches (default — checks if JSON exists):
    python scripts/fetch_fox_teamstats.py --seasons 2022 --skip-existing
"""

import argparse
import json
import os
import sqlite3
import time
import yaml
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FOX_API_KEY  = 'A00239D3-45F6-4A0A-810C-54A347F144C2'
FOX_BASE     = 'https://statsapi.foxsports.com.au/3.0/api'
SEASON_IDS   = {2022: 120, 2023: 121, 2024: 122, 2025: 123, 2026: 124}

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.yaml')
RAW_DIR       = os.path.join(os.path.dirname(__file__), '..', 'ml', 'data', 'match_stats')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept':     'application/json',
    'Referer':    'https://www.foxsports.com.au/',
}

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _get(session, url, retries=3):
    for attempt in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=15)
            return r
        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    return None


def get_rounds(session, season_id):
    """Return list of round dicts for a season."""
    url = f'{FOX_BASE}/sports/league/series/1/seasons/{season_id}/rounds.json?userkey={FOX_API_KEY}'
    r = _get(session, url)
    if r.status_code == 200:
        return r.json()
    return []


def get_teamstats(session, match_id):
    """Fetch teamstats JSON for a match. Returns (data_dict, status_code)."""
    url = f'{FOX_BASE}/sports/league/matches/{match_id}/teamstats.json?userkey={FOX_API_KEY}'
    r = _get(session, url)
    if r.status_code == 200:
        return r.json(), 200
    return None, r.status_code


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _pct_from_str(rate_str):
    """'36/43' -> 83.7"""
    try:
        num, den = rate_str.split('/')
        num, den = int(num.strip()), int(den.strip())
        return round(num / den * 100, 1) if den else None
    except (ValueError, AttributeError):
        return None


def parse_team(data, side, fox_match_id, season, round_number, match_number):
    """Extract a flat row dict from team_A or team_B block."""
    s = data.get('stats', {})
    cr_str = s.get('completion_rate', '')
    row = {
        'fox_match_id':    fox_match_id,
        'season':          season,
        'round_number':    round_number,
        'match_number':    match_number,
        'team_side':       side,
        'team_fox_id':     data.get('id'),
        'team_name':       data.get('name'),
        'team_code':       data.get('code'),

        # Attack
        'runs':                   s.get('runs'),
        'run_metres':             s.get('run_metres'),
        'post_contact_metres':    s.get('post_contact_metres'),
        'one_pass_runs':          s.get('one_pass_runs'),
        'dummy_half_runs':        s.get('dummy_half_runs'),
        'line_breaks':            s.get('line_breaks'),
        'line_break_assists':     s.get('line_break_assists'),
        'line_break_causes':      s.get('line_break_causes'),
        'tackle_busts':           s.get('tackle_busts'),
        'off_loads':              s.get('off_loads'),
        'effective_offloads':     s.get('effective_offloads'),
        'try_assists':            s.get('try_assists'),
        'tries':                  s.get('tries'),
        'points':                 s.get('points'),

        # Possession / sets
        'possession_percentage':  s.get('possession_percentage'),
        'territory':              s.get('territory'),
        'total_sets':             s.get('total_sets'),
        'complete_sets':          s.get('complete_sets'),
        'completion_rate_str':    cr_str,
        'completion_rate_pct':    _pct_from_str(cr_str),
        'errors':                 s.get('errors'),
        'in_complete_sets':       s.get('inCompleteSets'),

        # Kicks
        'kicks':                  s.get('kicks'),
        'kick_metres':            s.get('kick_metres'),
        'attacking_kicks':        s.get('attacking_kicks'),
        'long_kicks':             s.get('long_kicks'),
        'kicks_4020':             s.get('kicks_4020'),
        'kicks_2040':             s.get('kicks_2040'),
        'kicks_dead':             s.get('kicks_dead'),
        'drop_outs':              s.get('drop_outs'),
        'forced_drop_outs':       s.get('forced_drop_outs'),

        # Defence
        'tackles':                s.get('tackles'),
        'missed_tackles':         s.get('missed_tackles'),
        'tackles_one_on_one':     s.get('tackles_one_on_one'),
        'tackle_opp_half':        s.get('tackle_opp_half'),
        'tackled_opp_20':         s.get('tackledOpp20'),
        'line_engagements':       s.get('line_engagements'),

        # Discipline
        'penalties_conceded':     s.get('penalties_conceded'),
        'penalties_awarded':      s.get('penaltiesAwarded'),
        'sin_bins':               s.get('sin_bins'),
        'send_offs':              s.get('send_offs'),
        'set_restart_infringements_conceded': s.get('set_restart_infringements_conceded'),
        'set_restart_infringements_awarded':  s.get('set_restart_infringements_awarded'),
        'challenges':             s.get('challenges'),
        'correct_challenges':     s.get('correct_challenges'),
        'incorrect_challenges':   s.get('incorrect_challenges'),

        # General play
        'play_the_balls':         s.get('play_the_balls'),
        'general_play_pass':      s.get('general_play_pass'),
        'decoys':                 s.get('decoys'),
        'supports':               s.get('supports'),
        'options':                s.get('options'),

        # Goals / field goals
        'goal_rate_str':          s.get('goal_rate'),
        'goal_percentage':        s.get('goal_percentage'),
        'field_goals':            s.get('field_goals'),
        'field_goal_attempts':    s.get('field_goal_attempts'),
        'field_goal_misses':      s.get('field_goal_misses'),
        'two_point_field_goals':  s.get('two_point_field_goals'),

        # Misc
        'win_prediction_percentage': s.get('win_prediction_percentage'),
        'possession_time':           s.get('possession_time'),
        'territory_time':            s.get('territory_time'),

        'fetched_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'),
        'raw_json':   json.dumps(data),
    }
    return row


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def get_conn(settings_path):
    with open(settings_path) as fh:
        settings = yaml.safe_load(fh)
    db_path = settings.get('database', {}).get('path', 'data/betting_model.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def upsert_row(conn, row):
    cols   = [c for c in row if c != 'match_id']
    vals   = [row[c] for c in cols]
    ph     = ', '.join(['?'] * len(cols))
    colstr = ', '.join(cols)
    conn.execute(
        f'INSERT OR REPLACE INTO match_team_stats ({colstr}) VALUES ({ph})',
        vals
    )


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def raw_path(season, match_id):
    d = os.path.join(RAW_DIR, str(season))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f'{match_id}.json')


# ---------------------------------------------------------------------------
# Core fetch loop
# ---------------------------------------------------------------------------

def fetch_season(session, season, round_filter, skip_existing, dry_run, conn):
    season_id = SEASON_IDS.get(season)
    if not season_id:
        print(f'  Unknown season {season}')
        return 0, 0

    rounds = get_rounds(session, season_id)
    if not rounds:
        print(f'  No rounds found for {season}')
        return 0, 0

    fetched = skipped = errors = 0

    for rd in rounds:
        rnum  = rd['number']
        rname = rd.get('name', f'Round {rnum}')
        n_matches = rd.get('matches_in_round', 8)

        if round_filter and rnum != round_filter:
            continue

        for mnum in range(1, n_matches + 2):  # +2 buffer for occasional extra games
            match_id = f'NRL{season}{rnum:02d}{mnum:02d}'
            fpath    = raw_path(season, match_id)

            if skip_existing and os.path.exists(fpath):
                skipped += 1
                continue

            data, status = get_teamstats(session, match_id)

            if status == 404:
                # Past the last match in this round
                break
            elif status != 200 or data is None:
                print(f'    {match_id} -> HTTP {status} (skipping)')
                errors += 1
                continue

            # Save raw JSON
            with open(fpath, 'w') as fh:
                json.dump(data, fh)

            if not dry_run and conn:
                ta = parse_team(data['team_A'], 'home', match_id, season, rnum, mnum)
                tb = parse_team(data['team_B'], 'away', match_id, season, rnum, mnum)
                upsert_row(conn, ta)
                upsert_row(conn, tb)
                conn.commit()

            fetched += 1
            name_a = data['team_A'].get('name', '?')
            name_b = data['team_B'].get('name', '?')
            pts_a  = data['team_A'].get('stats', {}).get('points', '?')
            pts_b  = data['team_B'].get('stats', {}).get('points', '?')
            lb_a   = data['team_A'].get('stats', {}).get('line_breaks', '?')
            lb_b   = data['team_B'].get('stats', {}).get('line_breaks', '?')
            print(f'    {match_id}  {name_a} {pts_a}-{pts_b} {name_b}  '
                  f'(LB {lb_a}v{lb_b})')

            time.sleep(0.15)  # polite rate limit

        print(f'  {rname}: {fetched} fetched so far (this season)')

    return fetched, errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Fetch NRL team stats from Fox Sports API')
    parser.add_argument('--seasons', nargs='+', type=int, default=[2022, 2023, 2024, 2025, 2026])
    parser.add_argument('--round',   type=int, default=None, dest='round_filter',
                        help='Only fetch a specific round number')
    parser.add_argument('--skip-existing', action='store_true',
                        help='Skip matches where JSON already exists on disk')
    parser.add_argument('--dry-run', action='store_true',
                        help='Save JSON files only — do not write to DB')
    parser.add_argument('--settings', default=SETTINGS_PATH)
    args = parser.parse_args()

    conn = None
    if not args.dry_run:
        conn = get_conn(args.settings)
        # Apply migration if table doesn't exist
        mig_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'migrations',
                                '022_match_team_stats.sql')
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='match_team_stats'"
        ).fetchone()
        if not existing:
            with open(mig_path) as fh:
                sql = fh.read()
            for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass
            conn.commit()
            print('Created match_team_stats table.')

    session  = requests.Session()
    total_f  = total_e = 0

    for season in sorted(args.seasons):
        print(f'\n=== Season {season} ===')
        f, e = fetch_season(session, season, args.round_filter,
                             args.skip_existing, args.dry_run, conn)
        total_f += f
        total_e += e

    if conn:
        conn.close()

    print(f'\nDone. Fetched: {total_f}  Errors: {total_e}')
    print(f'Raw JSON → {RAW_DIR}/')


if __name__ == '__main__':
    main()
