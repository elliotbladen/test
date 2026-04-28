#!/usr/bin/env python3
"""
scripts/prepare_round.py

Single entry point for all pre-round pricing.

Runs in this order:
  1  Verify previous round results exist in DB
  2  Rebuild team_stats from DB results through previous round
  3  Rebuild ELO from latest prior snapshot through previous round
  4  Load injuries from --injury-json into injury_reports
  5  Load referees from --referee-csv into weekly_ref_assignments
  6  Validate all required data is present for every game
  7  Run full-model pricing and print tables

Fails loudly at the first missing dependency.

USAGE
-----
    python scripts/prepare_round.py --season 2026 --round 8 \\
        --injury-json data/import/injuries_r8.json \\
        --referee-csv data/import/referees_r8.csv

    # Dry-run (no DB writes, pricing still runs)
    python scripts/prepare_round.py --season 2026 --round 8 \\
        --injury-json data/import/injuries_r8.json \\
        --referee-csv data/import/referees_r8.csv \\
        --dry-run

    # Skip injury/referee loading if already loaded
    python scripts/prepare_round.py --season 2026 --round 8 --skip-load

REFEREE CSV FORMAT
------------------
    home_team,away_team,referee
    Brisbane Broncos,North Queensland Cowboys,Ashley Klein
    Melbourne Storm,New Zealand Warriors,Todd Smith

INJURY JSON FORMAT
------------------
    [
      {"season":2026,"round":8,"team":"Brisbane Broncos",
       "player":"Adam Reynolds","role":"halfback",
       "importance_tier":"elite","status":"out","notes":"hamstring"},
      ...
    ]
    Valid roles:    fullback, halfback, five_eighth, hooker, pack, other
    Valid tiers:    elite, key, rotation
    Valid statuses: out, doubtful, managed, available
"""

import argparse
import csv
import json
import sqlite3
import sys
import yaml
from collections import defaultdict
from datetime import datetime, timedelta, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pricing.tier1_baseline import compute_baseline
from pricing.tier2_matchup import (
    compute_family_a, compute_family_b, compute_family_c, compute_family_d,
)
from pricing.tier3_situational import compute_situational_adjustments
from pricing.tier4_venue import compute_venue_adjustments
from pricing.tier5_injury import compute_injury_adjustments
from pricing.tier6_referee import get_ref_context, compute_referee_adjustments
from pricing.tier7_emotional import compute_emotional_adjustments
from pricing.tier8_weather import compute_weather_adjustments
from pricing.engine import derive_final_prices
from db.queries import (
    get_team_stats, get_prior_season_stats,
    get_team_style_stats, get_style_league_norms,
    get_situational_context,
    get_team_venue_edge, get_venue_total_edge, get_venue_name,
    get_team_injury_pts,
    get_emotional_flags,
    get_weather_conditions,
    get_or_create_referee,
    insert_tier2_performance, update_tier2_results,
)

MODEL_VERSION  = '1.0.0-abc'
TOTALS_FLOOR   = 30.0
TOTALS_CEILING = 70.0
ELO_K          = 20.0
ELO_START      = 1500.0

# Canonical team name mapping
NAME_MAP = {
    'Canterbury Bulldogs':      'Canterbury-Bankstown Bulldogs',
    'Cronulla Sharks':          'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':         'Manly-Warringah Sea Eagles',
    'North QLD Cowboys':        'North Queensland Cowboys',
    'St George Dragons':        'St. George Illawarra Dragons',
    'Broncos':                  'Brisbane Broncos',
    'Bulldogs':                 'Canterbury-Bankstown Bulldogs',
    'Cowboys':                  'North Queensland Cowboys',
    'Dolphins':                 'Dolphins',
    'Dragons':                  'St. George Illawarra Dragons',
    'Eels':                     'Parramatta Eels',
    'Knights':                  'Newcastle Knights',
    'Panthers':                 'Penrith Panthers',
    'Rabbitohs':                'South Sydney Rabbitohs',
    'Raiders':                  'Canberra Raiders',
    'Roosters':                 'Sydney Roosters',
    'Sea Eagles':               'Manly-Warringah Sea Eagles',
    'Sharks':                   'Cronulla-Sutherland Sharks',
    'Storm':                    'Melbourne Storm',
    'Titans':                   'Gold Coast Titans',
    'Warriors':                 'New Zealand Warriors',
    'Wests Tigers':             'Wests Tigers',
}

VALID_ROLES    = {'fullback', 'halfback', 'five_eighth', 'hooker', 'pack', 'other'}
VALID_TIERS    = {'elite', 'key', 'rotation'}
VALID_STATUSES = {'out', 'doubtful', 'managed', 'available'}

_INJURY_PTS = {'elite': 3.0, 'key': 1.5, 'rotation': 0.5}


# =============================================================================
# Utilities
# =============================================================================

def canon(name: str) -> str:
    return NAME_MAP.get(name.strip(), name.strip())


def sep(char='─', n=100):
    print(char * n)


def header(title: str, char='═'):
    print()
    sep(char)
    print(f'  {title}')
    sep(char)


def die(msg: str):
    print(f'\n  ✗ FATAL: {msg}', file=sys.stderr)
    sys.exit(1)


def warn(msg: str):
    print(f'  ⚠  WARNING: {msg}')


def ok(msg: str):
    print(f'  ✓  {msg}')


# =============================================================================
# Step 1 — Verify previous round results
# =============================================================================

def step1_verify_results(conn, season: int, prev_round: int) -> str:
    """
    Check that every game in prev_round has a final result in the DB.
    Returns the date of the last game in prev_round (used as cutoff for stats).
    Calls die() if any game is missing a result.
    """
    header(f'STEP 1 — Verify R{prev_round} results in DB')

    matches = conn.execute('''
        SELECT m.match_id, m.match_date, m.round_number,
               h.team_name AS home, a.team_name AS away,
               r.home_score, r.away_score, r.result_status
        FROM   matches m
        JOIN   teams h ON h.team_id = m.home_team_id
        JOIN   teams a ON a.team_id = m.away_team_id
        LEFT   JOIN results r ON r.match_id = m.match_id
        WHERE  m.season = ? AND m.round_number = ?
        ORDER  BY m.match_date, m.match_id
    ''', (season, prev_round)).fetchall()

    if not matches:
        die(f'No fixtures found for season={season} round={prev_round}. '
            f'Fixtures must be loaded before running prepare_round.')

    missing = []
    last_date = None
    print(f'\n  {"Date":>10}  {"Home":<34}  {"Away":<34}  {"Score":>7}  Status')
    print(f'  {"─"*10}  {"─"*34}  {"─"*34}  {"─"*7}  {"─"*10}')

    for m in matches:
        score = f'{m["home_score"]}-{m["away_score"]}' if m['home_score'] is not None else '?'
        status = m['result_status'] or 'MISSING'
        flag = '' if m['result_status'] == 'final' else '  ← MISSING'
        print(f'  {m["match_date"]:>10}  {m["home"]:<34}  {m["away"]:<34}  '
              f'{score:>7}  {status}{flag}')
        if m['result_status'] != 'final':
            missing.append(f'{m["home"]} vs {m["away"]} ({m["match_date"]})')
        else:
            if last_date is None or m['match_date'] > last_date:
                last_date = m['match_date']

    if missing:
        die(f'R{prev_round} results missing for {len(missing)} game(s):\n'
            + '\n'.join(f'    • {g}' for g in missing)
            + '\n\n  Load results before running prepare_round.')

    ok(f'All {len(matches)} R{prev_round} results confirmed.')
    return last_date


# =============================================================================
# Step 2 — Rebuild team_stats
# =============================================================================

def step2_rebuild_team_stats(conn, season: int, as_of_date: str,
                              cutoff_date: str, dry_run: bool):
    """
    Recompute team_stats from all results through cutoff_date.
    Upserts a single snapshot at as_of_date.
    """
    header(f'STEP 2 — Rebuild team_stats  (as_of={as_of_date}, cutoff≤{cutoff_date})')

    rows = conn.execute('''
        SELECT m.home_team_id, m.away_team_id,
               r.home_score, r.away_score, m.match_date
        FROM   matches m
        JOIN   results r ON r.match_id = m.match_id
        WHERE  m.season = ? AND m.match_date <= ?
          AND  r.result_status = 'final'
        ORDER  BY m.match_date, m.match_id
    ''', (season, cutoff_date)).fetchall()

    print(f'\n  {len(rows)} results through {cutoff_date}\n')
    if not rows:
        die('No results found — cannot rebuild team_stats.')

    pf   = defaultdict(list); pa   = defaultdict(list)
    h_pf = defaultdict(list); h_pa = defaultdict(list)
    a_pf = defaultdict(list); a_pa = defaultdict(list)
    wins = defaultdict(int)

    for r in rows:
        hid, aid = r['home_team_id'], r['away_team_id']
        hs,  aws = r['home_score'],   r['away_score']
        pf[hid].append(hs);  pa[hid].append(aws)
        pf[aid].append(aws); pa[aid].append(hs)
        h_pf[hid].append(hs); h_pa[hid].append(aws)
        a_pf[aid].append(aws); a_pa[aid].append(hs)
        if hs > aws:  wins[hid] += 1
        elif aws > hs: wins[aid] += 1

    name_map = {r['team_id']: r['team_name']
                for r in conn.execute('SELECT team_id, team_name FROM teams').fetchall()}

    def avg(lst): return round(sum(lst) / len(lst), 4) if lst else None

    stats = {}
    for tid in set(pf.keys()):
        gp = len(pf[tid]); w = wins[tid]
        stats[tid] = {
            'gp': gp, 'wins': w, 'losses': gp - w,
            'win_pct': round(w / gp, 4),
            'pf': avg(pf[tid]), 'pa': avg(pa[tid]),
            'h_pf': avg(h_pf[tid]), 'h_pa': avg(h_pa[tid]),
            'a_pf': avg(a_pf[tid]), 'a_pa': avg(a_pa[tid]),
            '_diff': sum(pf[tid]) - sum(pa[tid]),
        }

    ranked = sorted(stats, key=lambda t: (-stats[t]['wins'], -stats[t]['_diff']))
    for pos, tid in enumerate(ranked, 1):
        stats[tid]['pos'] = pos

    print(f'  {"#":>3}  {"Team":<42}  {"GP":>3}  {"W":>2}  {"L":>2}  '
          f'{"PF/g":>6}  {"PA/g":>6}  {"Diff":>6}  {"Action":>8}')
    print(f'  {"─"*3}  {"─"*42}  {"─"*3}  {"─"*2}  {"─"*2}  '
          f'{"─"*6}  {"─"*6}  {"─"*6}  {"─"*8}')

    for tid in ranked:
        s = stats[tid]
        name = name_map.get(tid, f'id={tid}')
        existing = conn.execute(
            'SELECT team_stat_id FROM team_stats '
            'WHERE team_id=? AND season=? AND as_of_date=?',
            (tid, season, as_of_date)
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
            ''', (tid, season, as_of_date,
                  s['gp'], s['wins'], s['losses'], s['win_pct'], s['pos'],
                  s['pf'], s['pa'], s['h_pf'], s['h_pa'], s['a_pf'], s['a_pa']))

    if not dry_run:
        conn.commit()
        ok(f'Wrote {len(stats)} team_stats rows at as_of_date={as_of_date}.')
    else:
        ok(f'DRY RUN — would write {len(stats)} team_stats rows.')


# =============================================================================
# Step 3 — Rebuild ELO
# =============================================================================

def step3_rebuild_elo(conn, season: int, as_of_date: str,
                      cutoff_date: str, dry_run: bool):
    """
    Find the most recent ELO snapshot in team_stats.
    Apply all results between that snapshot and cutoff_date.
    Write updated ELOs into the team_stats row at as_of_date.
    """
    header(f'STEP 3 — Rebuild ELO  (as_of={as_of_date}, cutoff≤{cutoff_date})')

    # Find most recent ELO snapshot
    prior = conn.execute('''
        SELECT ts.team_id, ts.elo_rating, ts.as_of_date, t.team_name
        FROM   team_stats ts
        JOIN   teams t ON t.team_id = ts.team_id
        WHERE  ts.season = ? AND ts.elo_rating IS NOT NULL
          AND  ts.as_of_date < ?
        ORDER  BY ts.as_of_date DESC
    ''', (season, as_of_date)).fetchall()

    if not prior:
        die('No prior ELO snapshot found in team_stats. '
            'Run bootstrap_elo_2026.py first to establish a baseline.')

    prior_date = prior[0]['as_of_date']
    ratings    = {r['team_id']: r['elo_rating'] for r in prior}
    id_to_name = {r['team_id']: r['team_name']  for r in prior}

    print(f'\n  Prior ELO snapshot: as_of_date={prior_date} ({len(ratings)} teams)')

    # Games to apply: after prior_date through cutoff_date
    new_games = conn.execute('''
        SELECT m.match_id, m.match_date, m.round_number,
               m.home_team_id, m.away_team_id,
               r.home_score, r.away_score,
               h.team_name AS home_team, a.team_name AS away_team
        FROM   matches m
        JOIN   results r  ON r.match_id    = m.match_id
        JOIN   teams h    ON h.team_id     = m.home_team_id
        JOIN   teams a    ON a.team_id     = m.away_team_id
        WHERE  m.season = ?
          AND  m.match_date > ? AND m.match_date <= ?
          AND  r.result_status = 'final'
        ORDER  BY m.match_date, m.match_id
    ''', (season, prior_date, cutoff_date)).fetchall()

    print(f'  Applying {len(new_games)} games from {prior_date} → {cutoff_date}:\n')
    print(f'  {"Rnd":>4}  {"Date":>10}  {"Home":>34}  {"Away":>34}  '
          f'{"Score":>7}  {"ΔHome":>7}  {"ΔAway":>7}')
    print(f'  {"─"*4}  {"─"*10}  {"─"*34}  {"─"*34}  {"─"*7}  {"─"*7}  {"─"*7}')

    for g in new_games:
        hid, aid = g['home_team_id'], g['away_team_id']
        hs,  aws = g['home_score'],   g['away_score']
        if hid not in ratings:
            ratings[hid]    = ELO_START
            id_to_name[hid] = g['home_team']
        if aid not in ratings:
            ratings[aid]    = ELO_START
            id_to_name[aid] = g['away_team']

        e_h = 1.0 / (1.0 + 10.0 ** ((ratings[aid] - ratings[hid]) / 400.0))
        s_h = 1.0 if hs > aws else (0.0 if aws > hs else 0.5)
        delta_h = ELO_K * (s_h - e_h)
        delta_a = -delta_h

        ratings[hid] += delta_h
        ratings[aid] += delta_a
        print(f'  {g["round_number"]:>4}  {g["match_date"]:>10}  '
              f'{g["home_team"]:>34}  {g["away_team"]:>34}  '
              f'{hs:>3}-{aws:<3}  {delta_h:>+7.2f}  {delta_a:>+7.2f}')

    print(f'\n  Final ELO standings entering this round:')
    print(f'  {"Team":<42}  {"ELO":>8}  {"Δ1500":>7}')
    print(f'  {"─"*42}  {"─"*8}  {"─"*7}')
    for tid, elo in sorted(ratings.items(), key=lambda x: -x[1]):
        name = id_to_name.get(tid, f'id={tid}')
        print(f'  {name:<42}  {elo:>8.1f}  {elo - ELO_START:>+7.1f}')

    if not dry_run:
        written = 0
        for tid, elo in ratings.items():
            row = conn.execute(
                'SELECT team_stat_id FROM team_stats '
                'WHERE team_id=? AND season=? AND as_of_date=?',
                (tid, season, as_of_date)
            ).fetchone()
            if row:
                conn.execute(
                    'UPDATE team_stats SET elo_rating=? WHERE team_stat_id=?',
                    (round(elo, 2), row['team_stat_id'])
                )
                written += 1
            else:
                warn(f'No team_stats row at as_of_date={as_of_date} for team_id={tid} — ELO not written')
        conn.commit()
        ok(f'Wrote ELO for {written} teams into as_of_date={as_of_date}.')
    else:
        ok(f'DRY RUN — would write ELO for {len(ratings)} teams.')


# =============================================================================
# Step 4 — Load injuries
# =============================================================================

def step4_load_injuries(conn, season: int, round_number: int,
                        injury_json_path: str, dry_run: bool) -> int:
    """Load injury_reports from JSON. Returns number of players loaded."""
    header(f'STEP 4 — Load injuries for R{round_number}')

    if not injury_json_path:
        warn('No --injury-json provided — T5 handicap and totals will be 0.0 for all games.')
        return 0

    p = Path(injury_json_path)
    if not p.exists():
        die(f'Injury JSON not found: {p}')

    items = json.loads(p.read_text())
    if not isinstance(items, list):
        die('Injury JSON must be an array of player objects.')

    name_to_id = {r['team_name']: r['team_id']
                  for r in conn.execute('SELECT team_id, team_name FROM teams').fetchall()}

    now = datetime.utcnow().isoformat()
    ok_count = errors = 0

    print(f'\n  {"Team":<32}  {"Player":<22}  {"Role":<14}  {"Tier":<10}  {"Status":<10}  {"Pts":>4}  Result')
    print(f'  {"─"*32}  {"─"*22}  {"─"*14}  {"─"*10}  {"─"*10}  {"─"*4}  {"─"*8}')

    for item in items:
        item_season = int(item.get('season', season))
        item_round  = int(item.get('round',  round_number))
        team_name   = str(item.get('team',   '')).strip()
        player      = str(item.get('player', '')).strip()
        role        = str(item.get('role',   'other')).strip().lower()
        tier        = str(item.get('importance_tier', 'rotation')).strip().lower()
        status      = str(item.get('status', 'out')).strip().lower()
        notes       = item.get('notes')

        if not team_name or not player:
            warn(f'Skipping entry with missing team/player: {item}')
            errors += 1
            continue

        if role   not in VALID_ROLES:    role   = 'other'
        if tier   not in VALID_TIERS:    tier   = 'rotation'
        if status not in VALID_STATUSES:
            warn(f'Invalid status "{status}" for {player} — skipping')
            errors += 1
            continue

        team_id = name_to_id.get(canon(team_name))
        if team_id is None:
            warn(f'Team not found: "{team_name}"')
            errors += 1
            continue

        match_row = conn.execute('''
            SELECT match_id FROM matches
            WHERE  season=? AND round_number=?
              AND  (home_team_id=? OR away_team_id=?)
        ''', (item_season, item_round, team_id, team_id)).fetchone()

        if match_row is None:
            warn(f'No match found for {canon(team_name)} R{item_round} — skipping {player}')
            errors += 1
            continue

        match_id = match_row['match_id']
        pts_base = _INJURY_PTS.get(tier, 0.5)
        pts_eff  = pts_base * (0.5 if status == 'doubtful' else 1.0)

        if not dry_run:
            conn.execute('''
                INSERT INTO injury_reports
                    (match_id, team_id, player_name, player_role, importance_tier,
                     status, notes, captured_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(match_id, team_id, player_name) DO UPDATE SET
                    player_role     = excluded.player_role,
                    importance_tier = excluded.importance_tier,
                    status          = excluded.status,
                    notes           = excluded.notes,
                    captured_at     = excluded.captured_at
            ''', (match_id, team_id, player, role, tier, status, notes, now))
            result_str = 'WRITTEN'
        else:
            result_str = 'DRY-RUN'

        print(f'  {canon(team_name):<32}  {player:<22}  {role:<14}  {tier:<10}  '
              f'{status:<10}  {pts_eff:>4.1f}  {result_str}')
        ok_count += 1

    if not dry_run:
        conn.commit()

    print()
    ok(f'{ok_count} injury records loaded, {errors} errors.')
    return ok_count


# =============================================================================
# Step 5 — Load referees
# =============================================================================

def step5_load_referees(conn, season: int, round_number: int,
                        referee_csv_path: str, dry_run: bool) -> int:
    """Load weekly_ref_assignments from CSV. Returns number of assignments loaded."""
    header(f'STEP 5 — Load referee assignments for R{round_number}')

    if not referee_csv_path:
        warn('No --referee-csv provided — T6 will be 0.0 for all games.')
        return 0

    p = Path(referee_csv_path)
    if not p.exists():
        die(f'Referee CSV not found: {p}')

    with open(p, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    if not rows:
        warn('Referee CSV is empty.')
        return 0

    now = datetime.utcnow().isoformat()
    ok_count = errors = 0

    print(f'\n  {"Matchup":<54}  {"Referee":<26}  {"Bucket":<16}  Result')
    print(f'  {"─"*54}  {"─"*26}  {"─"*16}  {"─"*8}')

    for row in rows:
        home_name = str(row.get('home_team', '')).strip()
        away_name = str(row.get('away_team', '')).strip()
        ref_name  = str(row.get('referee',   '')).strip()

        if not home_name or not away_name or not ref_name:
            warn(f'Skipping incomplete CSV row: {row}')
            errors += 1
            continue

        home_can = canon(home_name)
        away_can = canon(away_name)
        matchup  = f'{home_can} vs {away_can}'

        match_row = conn.execute('''
            SELECT m.match_id, m.home_team_id, m.away_team_id
            FROM   matches m
            JOIN   teams h ON h.team_id = m.home_team_id
            JOIN   teams a ON a.team_id = m.away_team_id
            WHERE  m.season=? AND m.round_number=?
              AND  h.team_name=? AND a.team_name=?
        ''', (season, round_number, home_can, away_can)).fetchone()

        if match_row is None:
            print(f'  {matchup:<54}  {ref_name:<26}  {"?":16}  ERROR (match not found)')
            errors += 1
            continue

        match_id = match_row['match_id']
        ref_id   = get_or_create_referee(conn, ref_name)

        bucket_row = conn.execute(
            'SELECT bucket FROM referee_profiles WHERE referee_id=?', (ref_id,)
        ).fetchone()
        bucket = bucket_row['bucket'] if bucket_row else 'neutral'

        if not dry_run:
            conn.execute('''
                INSERT INTO weekly_ref_assignments
                    (match_id, referee_id, season, round_number, source, created_at)
                VALUES (?,?,?,?,'prepare_round',?)
                ON CONFLICT(match_id) DO UPDATE SET
                    referee_id   = excluded.referee_id,
                    source       = excluded.source,
                    season       = excluded.season,
                    round_number = excluded.round_number
            ''', (match_id, ref_id, season, round_number, now))
            conn.execute(
                'UPDATE matches SET referee_id=? WHERE match_id=?',
                (ref_id, match_id)
            )
            result_str = 'WRITTEN'
        else:
            result_str = 'DRY-RUN'

        print(f'  {matchup:<54}  {ref_name:<26}  {bucket:<16}  {result_str}')
        ok_count += 1

    if not dry_run:
        conn.commit()

    print()
    ok(f'{ok_count} referee assignments loaded, {errors} errors.')
    return ok_count


# =============================================================================
# Step 6 — Validate
# =============================================================================

def step6_validate(conn, season: int, round_number: int, strict_injuries: bool):
    """
    Check every game in the target round has:
      - team_stats for both teams
      - ELO for both teams
      - referee assignment (die if missing)
      - injury report (warn if missing; die only if strict_injuries=True)
    """
    header(f'STEP 6 — Validate data completeness for R{round_number}')

    matches = conn.execute('''
        SELECT m.match_id, m.match_date, m.round_number,
               m.home_team_id, m.away_team_id,
               h.team_name AS home, a.team_name AS away
        FROM   matches m
        JOIN   teams h ON h.team_id = m.home_team_id
        JOIN   teams a ON a.team_id = m.away_team_id
        WHERE  m.season=? AND m.round_number=?
        ORDER  BY m.match_date, m.match_id
    ''', (season, round_number)).fetchall()

    if not matches:
        die(f'No fixtures found for season={season} round={round_number}.')

    errors   = []
    warnings = []

    print(f'\n  {"Matchup":<54}  {"Stats":>6}  {"ELO":>6}  {"Ref":>6}  {"Inj":>6}')
    print(f'  {"─"*54}  {"─"*6}  {"─"*6}  {"─"*6}  {"─"*6}')

    for m in matches:
        matchup = f'{m["home"]} vs {m["away"]}'
        mdate   = m['match_date']

        h_stats = get_team_stats(conn, m['home_team_id'], season, mdate)
        a_stats = get_team_stats(conn, m['away_team_id'], season, mdate)
        stats_ok = bool(h_stats and a_stats)

        h_elo = (h_stats or {}).get('elo_rating')
        a_elo = (a_stats or {}).get('elo_rating')
        elo_ok = bool(h_elo and a_elo)

        ref_row = conn.execute(
            'SELECT referee_id FROM weekly_ref_assignments WHERE match_id=?',
            (m['match_id'],)
        ).fetchone()
        ref_ok = bool(ref_row)

        h_inj = get_team_injury_pts(conn, m['match_id'], m['home_team_id'])
        a_inj = get_team_injury_pts(conn, m['match_id'], m['away_team_id'])
        # Check both injury_reports (individual) and team_injury_totals (pre-aggregated)
        inj_loaded = conn.execute(
            'SELECT COUNT(*) FROM injury_reports WHERE match_id=?',
            (m['match_id'],)
        ).fetchone()[0]
        inj_totals = conn.execute(
            'SELECT COUNT(*) FROM team_injury_totals WHERE match_id=?',
            (m['match_id'],)
        ).fetchone()[0]
        inj_ok = (inj_loaded > 0) or (inj_totals > 0)

        def tick(flag): return '✓' if flag else '✗'
        print(f'  {matchup:<54}  {tick(stats_ok):>6}  {tick(elo_ok):>6}  '
              f'{tick(ref_ok):>6}  {tick(inj_ok):>6}')

        if not stats_ok:
            errors.append(f'{matchup}: team_stats missing (date={mdate})')
        if not elo_ok:
            errors.append(f'{matchup}: ELO missing')
        if not ref_ok:
            errors.append(f'{matchup}: no referee assignment')
        if not inj_ok:
            msg = f'{matchup}: no injury report (T5 will be 0 — assuming no outs)'
            if strict_injuries:
                errors.append(msg)
            else:
                warnings.append(msg)

    if warnings:
        print()
        for w in warnings:
            warn(w)

    if errors:
        print()
        die('Validation failed:\n' + '\n'.join(f'    • {e}' for e in errors))

    print()
    ok(f'All {len(matches)} games validated.')


# =============================================================================
# Step 7 — Price
# =============================================================================

def _get_family_label(result: dict, direction: str) -> str:
    d = result.get('debug', {})
    key = 'h_attacks_a_label' if direction == 'h' else 'a_attacks_h_label'
    return d.get(key, 'none')


def price_match(conn, match_row, tier2_cfg, tiers_cfg) -> dict:
    match_id   = match_row['match_id']
    home_tid   = match_row['home_team_id']
    away_tid   = match_row['away_team_id']
    venue_id   = match_row['venue_id']
    match_date = match_row['match_date']
    season     = match_row['season']
    home_name  = match_row['home_team']
    away_name  = match_row['away_team']

    t1_cfg     = tiers_cfg.get('tier1_baseline', {})
    home_stats = get_team_stats(conn, home_tid, season, match_date) or {}
    away_stats = get_team_stats(conn, away_tid, season, match_date) or {}
    home_prior = get_prior_season_stats(conn, home_tid, season)
    away_prior = get_prior_season_stats(conn, away_tid, season)

    t1 = compute_baseline(home_stats, away_stats, {}, t1_cfg,
                          home_prior_stats=home_prior, away_prior_stats=away_prior)
    t1_home   = t1['baseline_home_points']
    t1_away   = t1['baseline_away_points']
    t1_mrg    = t1['baseline_margin']
    totals_T1 = t1.get('totals_T1', t1['baseline_total'])

    home_style = get_team_style_stats(conn, home_tid, season, match_date) or {}
    away_style = get_team_style_stats(conn, away_tid, season, match_date) or {}
    as_of      = home_style.get('as_of_date') or away_style.get('as_of_date') or match_date
    norms      = get_style_league_norms(conn, season, as_of)

    fa = compute_family_a(home_style, away_style, norms, tier2_cfg)
    fc = compute_family_c(home_style, away_style, norms, tier2_cfg)
    fd = compute_family_d(home_style, away_style, norms, tier2_cfg,
                          home_2a_delta=fa['home_delta'], away_2a_delta=fa['away_delta'])
    fb = compute_family_b(home_style, away_style, norms, tier2_cfg)

    t2a_h = fa['home_delta']; t2b_h = fb['home_delta']
    t2c_h = fc['home_delta']; t2d_h = fd['home_delta']
    raw_home_t2 = t2a_h + t2b_h + t2c_h + t2d_h
    raw_away_t2 = fa['away_delta'] + fb['away_delta'] + fc['away_delta'] + fd['away_delta']
    raw_totals_T2 = (fa.get('totals_delta', 0.0) + fb.get('totals_delta', 0.0)
                     + fc.get('totals_delta', 0.0) + fd.get('totals_delta', 0.0))
    totals_T2 = round(max(-3.0, min(3.0, raw_totals_T2)), 3)

    cap_t2 = float(tier2_cfg.get('max_home_points_delta', 4.0))
    scale_t2 = 1.0
    if abs(raw_home_t2) > cap_t2 and raw_home_t2 != 0.0:
        scale_t2 = min(scale_t2, cap_t2 / abs(raw_home_t2))
    if abs(raw_away_t2) > cap_t2 and raw_away_t2 != 0.0:
        scale_t2 = min(scale_t2, cap_t2 / abs(raw_away_t2))
    t2_capped_home = round(raw_home_t2 * scale_t2, 3)
    t2_capped_away = round(raw_away_t2 * scale_t2, 3)

    fired = []
    if t2a_h or fa['away_delta']: fired.append('A')
    if t2b_h or fb['away_delta']: fired.append('B')
    if t2c_h or fc['away_delta']: fired.append('C')
    if t2d_h or fd['away_delta']: fired.append('D')

    sit_ctx = get_situational_context(conn, match_id, home_tid, away_tid, venue_id, match_date, season)
    t3      = compute_situational_adjustments(sit_ctx, tiers_cfg)
    t3_home = t3['home_delta_capped']
    t3_away = t3['away_delta_capped']
    totals_T3 = t3.get('totals_delta', 0.0)

    t5_cfg       = tiers_cfg.get('tier5_injury', {})
    h_injury_pts = get_team_injury_pts(conn, match_id, home_tid)
    a_injury_pts = get_team_injury_pts(conn, match_id, away_tid)
    t5 = compute_injury_adjustments(h_injury_pts, a_injury_pts, t5_cfg)
    t5_handicap_delta = t5['handicap_delta']
    totals_T5         = t5['totals_delta']

    t4_cfg = tiers_cfg.get('tier4_venue', {})
    home_v_edge    = get_team_venue_edge(conn, home_tid, venue_id)
    away_v_edge    = get_team_venue_edge(conn, away_tid, venue_id)
    venue_tot_edge = get_venue_total_edge(conn, venue_id)
    venue_name_str = get_venue_name(conn, venue_id)
    if t4_cfg.get('enabled', True):
        t4 = compute_venue_adjustments(home_tid, away_tid, venue_id,
                                       home_v_edge, away_v_edge, venue_tot_edge, t4_cfg)
        t4_handicap_delta = t4['handicap_delta']
        totals_T4         = t4['totals_delta']
    else:
        t4_handicap_delta = totals_T4 = 0.0

    t6_cfg = tiers_cfg.get('tier6_referee', {})
    t6_ctx = get_ref_context(conn, match_id, home_tid, away_tid, season)
    if t6_ctx and t6_cfg.get('enabled', True):
        t6 = compute_referee_adjustments(t6_ctx['home_bucket_edge'],
                                         t6_ctx['away_bucket_edge'],
                                         t6_ctx['bucket'], t6_cfg)
        t6_handicap_delta = t6['handicap_delta']
        totals_T6         = t6['totals_delta']
        t6_bucket         = t6_ctx['bucket']
        t6_referee_name   = t6_ctx['referee_name']
    else:
        t6_handicap_delta = totals_T6 = 0.0
        t6_bucket = t6_referee_name = None

    # --- Tier 7 emotional ---
    t7_cfg         = tiers_cfg.get('tier7_emotional', {})
    home_e_flags   = get_emotional_flags(conn, match_id, home_tid)
    away_e_flags   = get_emotional_flags(conn, match_id, away_tid)
    t7 = compute_emotional_adjustments(home_e_flags, away_e_flags, t7_cfg)
    t7_handicap_delta = t7['handicap_delta']
    totals_T7         = t7['totals_delta']

    # --- Tier 8 weather (game-day pricing — 0.0 if not yet fetched) ---
    t8_cfg      = tiers_cfg.get('tier8_weather', {})
    kickoff_dt  = match_row['kickoff_datetime'] or ''
    weather_row = get_weather_conditions(conn, match_id)
    t8 = compute_weather_adjustments(weather_row, kickoff_dt, t8_cfg)
    totals_T8          = t8['totals_delta']
    t8_condition_type  = t8['condition_type']
    t8_dew_risk        = int(t8['dew_risk'])

    final_home = round(t1_home + t2_capped_home + t3_home, 3)
    final_away = round(t1_away + t2_capped_away + t3_away, 3)
    final_mrg  = round(final_home - final_away
                       + t4_handicap_delta + t5_handicap_delta
                       + t6_handicap_delta + t7_handicap_delta, 3)

    raw_final_total = totals_T1 + totals_T2 + totals_T3 + totals_T4 + totals_T5 + totals_T6 + totals_T7 + totals_T8
    final_total     = round(max(TOTALS_FLOOR, min(TOTALS_CEILING, raw_final_total)), 2)
    pred_home_score = round((final_total + final_mrg) / 2.0, 1)
    pred_away_score = round((final_total - final_mrg) / 2.0, 1)

    prices = derive_final_prices(pred_home_score, pred_away_score, t1_cfg)

    return {
        'match_id': match_id, 'model_version': MODEL_VERSION,
        'season': season, 'round_number': match_row['round_number'],
        'match_date': match_date,
        'home_team_id': home_tid, 'away_team_id': away_tid,
        'home_name': home_name, 'away_name': away_name,

        't1_margin':    round(t1_mrg, 3),
        't1_home_pts':  round(t1_home, 3),
        't1_away_pts':  round(t1_away, 3),
        't2_net_hcap':  round(t2_capped_home - t2_capped_away, 3),
        't3_net_hcap':  round(t3_home - t3_away, 3),
        't4_handicap_delta': t4_handicap_delta,
        't5_handicap_delta': t5_handicap_delta,
        't6_handicap_delta': t6_handicap_delta,
        't7_handicap_delta': t7_handicap_delta,
        'final_margin': final_mrg,

        'totals_T1': round(totals_T1, 2),
        'totals_T2': totals_T2,
        'totals_T3': round(totals_T3, 3),
        'totals_T4': totals_T4,
        'totals_T5': totals_T5,
        'totals_T6': totals_T6,
        'totals_T7': totals_T7,
        'totals_T8': totals_T8,
        'final_total': final_total,
        'pred_home_score': pred_home_score,
        'pred_away_score': pred_away_score,

        'fair_home_odds':       prices['fair_home_odds'],
        'fair_away_odds':       prices['fair_away_odds'],
        'home_win_probability': prices['home_win_probability'],
        'away_win_probability': prices['away_win_probability'],
        'fair_handicap_line':   prices['fair_handicap_line'],
        'fair_total_line':      prices['fair_total_line'],
        'h2h_home_105':         round(prices['fair_home_odds'] / 1.05, 3),
        'h2h_away_105':         round(prices['fair_away_odds'] / 1.05, 3),

        't4_venue_name':     venue_name_str,
        't6_referee_name':   t6_referee_name,
        't6_bucket':         t6_bucket,
        't5_home_injury_pts': h_injury_pts,
        't5_away_injury_pts': a_injury_pts,

        # For performance table
        't2a_home_delta': t2a_h, 't2b_home_delta': t2b_h, 't2c_home_delta': t2c_h,
        't2_raw_total': round(raw_home_t2, 3), 't2_capped_total': t2_capped_home,
        't2_scale_applied': round(scale_t2, 4) if scale_t2 < 1.0 else None,
        't2a_label_h': _get_family_label(fa, 'h'), 't2a_label_a': _get_family_label(fa, 'a'),
        't2b_label_h': _get_family_label(fb, 'h'), 't2b_label_a': _get_family_label(fb, 'a'),
        't2c_label_h': _get_family_label(fc, 'h'), 't2c_label_a': _get_family_label(fc, 'a'),
        'fired_families': ','.join(fired),
        'final_home_pts': final_home, 'final_away_pts': final_away,
        'raw_final_total': round(raw_final_total, 2),
        '_t3_home_delta': t3_home, '_t3_away_delta': t3_away,
        '_t3_3a': t3.get('3a_home_delta', 0.0), '_t3_3b': t3.get('3b_home_delta', 0.0),
        '_t3_3c_home': t3.get('3c_home_delta', 0.0), '_t3_3c_away': t3.get('3c_away_delta', 0.0),
        '_t3_home_rest': sit_ctx.get('home_rest_days'), '_t3_away_rest': sit_ctx.get('away_rest_days'),
        '_t3_home_km': sit_ctx.get('home_travel_km'), '_t3_away_km': sit_ctx.get('away_travel_km'),
        '_t5_debug': t5['_debug'],
        't4_home_edge': home_v_edge, 't4_away_edge': away_v_edge,
        '_t2d_home_delta': t2d_h, '_t2d_away_delta': fd['away_delta'],
        '_t2d_label_h': _get_family_label(fd, 'h'), '_t2d_label_a': _get_family_label(fd, 'a'),
        '_t2d_2a_agree': fd['debug'].get('_2a_same_direction'),
        '_t7_home_flags': len(home_e_flags),
        '_t7_away_flags': len(away_e_flags),
        '_t7_debug': t7['_debug'],
        't7_condition_type': t8_condition_type,
        't7_dew_risk': t8_dew_risk,
    }


def step6a_fetch_weather(conn, season: int, round_number: int,
                         dry_run: bool, skip: bool):
    """
    Step 6a — Fetch T8 weather conditions for every match in the round.

    Uses Open-Meteo for Australian venues and MetService for Auckland.
    Falls back to clear (0.0) on any API failure so pricing always completes.

    --skip-weather: skip this step (weather already loaded or not needed).
    --dry-run:      fetch and classify but do not write to DB.
    """
    from scripts.fetch_weather import (
        fetch_weather_for_match, build_weather_row, upsert_weather,
        _mock_clear_row, AUCKLAND_VENUE_IDS,
    )
    header(f'STEP 6a — Fetch weather for R{round_number}')

    if skip:
        ok('Step 6a skipped (--skip-weather).')
        return

    matches = conn.execute(
        '''
        SELECT m.match_id, m.venue_id, m.kickoff_datetime,
               v.venue_name, v.lat, v.lng
        FROM matches m
        LEFT JOIN venues v ON v.venue_id = m.venue_id
        WHERE m.season = ? AND m.round_number = ?
        ORDER BY m.match_date, m.match_id
        ''',
        (season, round_number),
    ).fetchall()

    ok_count = 0
    for m in matches:
        mid     = m['match_id']
        vid     = m['venue_id']
        vname   = m['venue_name'] or f'venue_id={vid}'
        lat     = m['lat']
        lng     = m['lng']
        kickoff = m['kickoff_datetime']

        if lat is None or lng is None:
            print(f'  match={mid}  {vname}: SKIP — no lat/lng, assuming clear')
            row = _mock_clear_row(mid, vid, kickoff)
            upsert_weather(conn, row, dry_run=dry_run)
            ok_count += 1
            continue

        try:
            raw = fetch_weather_for_match(mid, vid, vname, lat, lng, kickoff)
            row = build_weather_row(mid, vid, kickoff, raw)
        except Exception as exc:
            print(f'  match={mid}  {vname}: API error ({exc}) — defaulting to clear')
            row = _mock_clear_row(mid, vid, kickoff)

        upsert_weather(conn, row, dry_run=dry_run)
        dew_str = ' [dew]' if row['dew_risk'] else ''
        print(f'  match={mid}  {vname:<32}  '
              f'{row["condition_type"]:<20}  '
              f'T={row["temp_c"]}°C  W={row["wind_kmh"]}km/h  '
              f'P={row["precipitation_mm"]}mm  '
              f'Δtot={row["totals_delta"]:+.1f}{dew_str}  '
              f'[{row["data_source"]}]')
        ok_count += 1

    if not dry_run:
        conn.commit()
    ok(f'{ok_count}/{len(matches)} weather rows {"staged" if dry_run else "written"}.')


def step7_price(conn, season: int, round_number: int,
                tiers_cfg: dict, dry_run: bool):
    header(f'STEP 7 — Pricing  season={season}  R{round_number}  '
           f'[{"DRY RUN" if dry_run else "WRITE"}]')

    tier2_cfg = tiers_cfg.get('tier2_matchup', {})

    matches = conn.execute('''
        SELECT m.match_id, m.match_date, m.round_number, m.season,
               m.home_team_id, m.away_team_id, m.venue_id,
               m.kickoff_datetime,
               h.team_name AS home_team, a.team_name AS away_team
        FROM   matches m
        JOIN   teams h ON m.home_team_id = h.team_id
        JOIN   teams a ON m.away_team_id = a.team_id
        WHERE  m.season=? AND m.round_number=?
        ORDER  BY m.match_date, m.match_id
    ''', (season, round_number)).fetchall()

    records = []
    for m in matches:
        rec = price_match(conn, m, tier2_cfg, tiers_cfg)
        records.append(rec)

    def short(name, n=28):
        return name if len(name) <= n else name[:n-1] + '…'

    # ── Handicap build-up ───────────────────────────────���────────────────────
    W1 = 178
    print(f'\n{"═"*W1}')
    print(f'  HANDICAP BUILD-UP  (home perspective)   |   H2H at 105% book')
    print(f'{"─"*W1}')
    print(f'  {"Matchup":<46}  '
          f'{"T1mrg":>6}  {"T2h":>6}  {"T3h":>6}  {"T4h":>6}  {"T5h":>6}  {"T6h":>6}  '
          f'{"Margin":>7}  {"Hcap":>6}  '
          f'{"H%":>5}  {"H(fair)":>8}  {"A(fair)":>8}  {"H@105":>7}  {"A@105":>7}  {"Score":>11}')
    print(f'{"─"*W1}')
    for rec in records:
        matchup = f'{short(rec["home_name"])} vs {short(rec["away_name"])}'
        score   = f'({rec["pred_home_score"]:.1f}-{rec["pred_away_score"]:.1f})'
        hpct    = rec['home_win_probability'] * 100
        t5_flag = f'*' if rec['t5_handicap_delta'] != 0.0 else ' '
        t6_flag = f'*' if rec['t6_handicap_delta'] != 0.0 else ' '
        print(f'  {matchup:<46}  '
              f'{rec["t1_margin"]:>+6.1f}  '
              f'{rec["t2_net_hcap"]:>+6.1f}  '
              f'{rec["t3_net_hcap"]:>+6.1f}  '
              f'{rec["t4_handicap_delta"]:>+6.1f}  '
              f'{rec["t5_handicap_delta"]:>+6.1f}{t5_flag} '
              f'{rec["t6_handicap_delta"]:>+6.1f}{t6_flag} '
              f'{rec["final_margin"]:>+7.1f}  '
              f'{rec["fair_handicap_line"]:>+6.1f}  '
              f'{hpct:>4.1f}%  '
              f'{rec["fair_home_odds"]:>8.3f}  '
              f'{rec["fair_away_odds"]:>8.3f}  '
              f'{rec["h2h_home_105"]:>7.3f}  '
              f'{rec["h2h_away_105"]:>7.3f}  '
              f'{score:>11}')
    print(f'{"═"*W1}')
    print(f'  * = T5/T6 fired (injury or referee data present)')

    # ── Totals build-up ──────────────────────────────────────────────────────
    W2 = 185
    print(f'\n{"═"*W2}')
    print(f'  TOTALS BUILD-UP')
    print(f'{"─"*W2}')
    print(f'  {"Matchup":<46}  '
          f'{"T1tot":>6}  {"T2t":>6}  {"T3t":>6}  {"T4t":>6}  {"T5t":>6}  {"T6t":>6}  {"T7t":>6}  '
          f'{"Total":>6}  {"Score":>11}  {"Referee":<26}  {"Bucket":<14}  {"Weather"}')
    print(f'{"─"*W2}')
    for rec in records:
        matchup  = f'{short(rec["home_name"])} vs {short(rec["away_name"])}'
        score    = f'({rec["pred_home_score"]:.1f}-{rec["pred_away_score"]:.1f})'
        ref_col  = rec.get('t6_referee_name') or '—'
        bkt_col  = rec.get('t6_bucket') or '—'
        dew_flag = ' [dew]' if rec.get('t7_dew_risk') else ''
        wx_col   = f'{rec.get("t7_condition_type", "clear")}{dew_flag}'
        print(f'  {matchup:<46}  '
              f'{rec["totals_T1"]:>6.1f}  '
              f'{rec["totals_T2"]:>+6.2f}  '
              f'{rec["totals_T3"]:>+6.2f}  '
              f'{rec["totals_T4"]:>+6.2f}  '
              f'{rec["totals_T5"]:>+6.2f}  '
              f'{rec["totals_T6"]:>+6.2f}  '
              f'{rec["totals_T7"]:>+6.2f}  '
              f'{rec["final_total"]:>6.1f}  '
              f'{score:>11}  '
              f'{ref_col:<26}  {bkt_col:<14}  {wx_col}')
    print(f'{"═"*W2}')

    # ── T5/T6 fire check ─────────────────────────────────────────────────────
    print(f'\n  T5 Injury check:')
    for rec in records:
        h_pts = rec['t5_home_injury_pts']
        a_pts = rec['t5_away_injury_pts']
        if h_pts > 0 or a_pts > 0:
            print(f'    {rec["home_name"]:<34} home_pts={h_pts:.1f}  '
                  f'away_pts={a_pts:.1f}  '
                  f'hcap_delta={rec["t5_handicap_delta"]:+.3f}  '
                  f'totals_delta={rec["totals_T5"]:+.3f}')
        else:
            print(f'    {rec["home_name"]:<34} vs {rec["away_name"]:<34}  no injury data')

    print(f'\n  T6 Referee check:')
    for rec in records:
        ref = rec.get('t6_referee_name') or '—'
        bkt = rec.get('t6_bucket') or '—'
        print(f'    {rec["home_name"]:<34} ref={ref:<26}  bucket={bkt:<16}  '
              f'totals_delta={rec["totals_T6"]:+.3f}  '
              f'hcap_delta={rec["t6_handicap_delta"]:+.3f}')

    print(f'\n  T7 Weather check:')
    for rec in records:
        ct       = rec.get('t7_condition_type') or 'clear'
        dew_str  = '  [dew]' if rec.get('t7_dew_risk') else ''
        t7t      = rec.get('totals_T7', 0.0)
        print(f'    {rec["home_name"]:<34} condition={ct:<28}  '
              f'totals_delta={t7t:+.2f}{dew_str}')

    if not dry_run:
        for rec in records:
            insert_tier2_performance(conn, rec)
        n = update_tier2_results(conn, season, MODEL_VERSION)
        print(f'\n  {len(records)} rows written to tier2_performance.')
        if n:
            print(f'  {n} rows updated with actual results.')

    ok(f'Pricing complete for R{round_number}.')


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Prepare and price a round — single entry point.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--season',       type=int, default=2026)
    parser.add_argument('--round',        type=int, required=True,
                        help='Round number to price')
    parser.add_argument('--injury-json',  default=None,
                        help='JSON file of player injury data for this round')
    parser.add_argument('--referee-csv',  default=None,
                        help='CSV file of referee assignments for this round')
    parser.add_argument('--dry-run',      action='store_true',
                        help='Run all steps but write nothing to DB')
    parser.add_argument('--skip-load',    action='store_true',
                        help='Skip steps 4+5 (injuries/refs already loaded)')
    parser.add_argument('--skip-weather', action='store_true',
                        help='Skip step 6a (weather already fetched or mock-clear preferred)')
    parser.add_argument('--strict-injuries', action='store_true',
                        help='Treat missing injury data as a fatal error')
    parser.add_argument('--settings',     default='config/settings.yaml')
    args = parser.parse_args()

    settings  = yaml.safe_load(open(args.settings))
    tiers_cfg = yaml.safe_load(open('config/tiers.yaml'))

    conn = sqlite3.connect(settings['database']['path'])
    conn.row_factory = sqlite3.Row

    season      = args.season
    round_num   = args.round
    prev_round  = round_num - 1

    print(f'\n{"═"*80}')
    print(f'  prepare_round  season={season}  round={round_num}')
    print(f'  mode={"DRY RUN" if args.dry_run else "WRITE"}')
    print(f'{"═"*80}')

    # ── Step 1: Verify previous round results ────────────────────────��────
    if prev_round >= 1:
        last_result_date = step1_verify_results(conn, season, prev_round)
    else:
        print('\n  Round 1 — no previous round to verify.')
        last_result_date = None

    # ── Step 2 & 3: Rebuild stats and ELO ────────────────────────────────
    if last_result_date:
        # as_of_date = day before first game of this round
        first_game_row = conn.execute('''
            SELECT MIN(match_date) AS first_date FROM matches
            WHERE season=? AND round_number=?
        ''', (season, round_num)).fetchone()

        if not first_game_row or not first_game_row['first_date']:
            die(f'No fixtures found for season={season} round={round_num}.')

        first_game_date = first_game_row['first_date']
        as_of_date = (
            datetime.strptime(first_game_date, '%Y-%m-%d') - timedelta(days=1)
        ).strftime('%Y-%m-%d')

        step2_rebuild_team_stats(conn, season, as_of_date, last_result_date, args.dry_run)
        step3_rebuild_elo(conn, season, as_of_date, last_result_date, args.dry_run)
    else:
        print('\n  Skipping team_stats/ELO rebuild (round 1).')

    # ── Step 4: Load injuries ─────────────────────────────────────────────
    if not args.skip_load:
        step4_load_injuries(conn, season, round_num, args.injury_json, args.dry_run)
    else:
        ok('Step 4 skipped (--skip-load).')

    # ── Step 5: Load referees ─────────────────────────────────────────────
    if not args.skip_load:
        step5_load_referees(conn, season, round_num, args.referee_csv, args.dry_run)
    else:
        ok('Step 5 skipped (--skip-load).')

    # ── Step 6: Validate ──────────────────────────────────────────────────
    step6_validate(conn, season, round_num, strict_injuries=args.strict_injuries)

    # ── Step 6a: Fetch weather (T7) ───────────────────────────────────────
    step6a_fetch_weather(conn, season, round_num, args.dry_run, args.skip_weather)

    # ── Step 7: Price ─────────────────────────────────────────────────────
    step7_price(conn, season, round_num, tiers_cfg, args.dry_run)

    conn.close()
    print()


if __name__ == '__main__':
    main()
