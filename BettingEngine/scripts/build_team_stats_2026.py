#!/usr/bin/env python3
"""
scripts/build_team_stats_2026.py

Build 2026 pre-Round-5 team_stats rows from DB match results.

Reads all 2026 matches with match_date < R5_CUTOFF from the DB,
computes per-team stats, and upserts to team_stats with
as_of_date='2026-03-24', season=2026.

Fields computed:
  games_played, wins, losses, win_pct
  points_for_avg, points_against_avg
  home_points_for_avg, home_points_against_avg
  away_points_for_avg, away_points_against_avg
  ladder_position  (ranked by wins desc, then points_diff desc)

Fields NOT set here (set by bootstrap_elo_2026.py):
  elo_rating

USAGE:
  cd /path/to/Betting_model
  python scripts/build_team_stats_2026.py [--dry-run]
"""

import argparse
import sqlite3
import sys
import yaml
from collections import defaultdict
from pathlib import Path

SEASON     = 2026
AS_OF_DATE = '2026-03-24'
R5_CUTOFF  = '2026-03-26'   # games strictly before this date only


def load_matches(conn) -> list:
    rows = conn.execute(
        """
        SELECT
            m.match_id,
            m.match_date,
            m.home_team_id,
            m.away_team_id,
            r.home_score,
            r.away_score,
            th.team_name AS home_team,
            ta.team_name AS away_team
        FROM   matches m
        JOIN   results r  ON r.match_id   = m.match_id
        JOIN   teams   th ON th.team_id   = m.home_team_id
        JOIN   teams   ta ON ta.team_id   = m.away_team_id
        WHERE  m.season = ?
          AND  m.match_date < ?
        ORDER  BY m.match_date ASC, m.match_id ASC
        """,
        (SEASON, R5_CUTOFF),
    ).fetchall()
    return [dict(r) for r in rows]


def compute_stats(matches: list) -> dict:
    """
    Returns dict of team_id → stats dict.
    """
    # Accumulate raw game-by-game data
    pf   = defaultdict(list)   # points for
    pa   = defaultdict(list)   # points against
    h_pf = defaultdict(list)   # home points for
    h_pa = defaultdict(list)   # home points against
    a_pf = defaultdict(list)   # away points for
    a_pa = defaultdict(list)   # away points against
    wins = defaultdict(int)
    names = {}

    for m in matches:
        hid = m['home_team_id']
        aid = m['away_team_id']
        hs  = m['home_score']
        aws = m['away_score']

        names[hid] = m['home_team']
        names[aid] = m['away_team']

        pf[hid].append(hs);   pa[hid].append(aws)
        pf[aid].append(aws);  pa[aid].append(hs)
        h_pf[hid].append(hs); h_pa[hid].append(aws)
        a_pf[aid].append(aws);a_pa[aid].append(hs)

        if hs > aws:
            wins[hid] += 1
        elif aws > hs:
            wins[aid] += 1
        else:
            # Draw — count 0.5 for each, stored later as int truncated
            pass

    # Determine all teams that played
    all_teams = set(pf.keys())

    def _avg(lst):
        return round(sum(lst) / len(lst), 4) if lst else None

    stats = {}
    for tid in all_teams:
        gp   = len(pf[tid])
        w    = wins[tid]
        l    = gp - w
        diff = sum(pf[tid]) - sum(pa[tid])
        stats[tid] = {
            'team_name':             names[tid],
            'games_played':          gp,
            'wins':                  w,
            'losses':                l,
            'win_pct':               round(w / gp, 4) if gp else None,
            'points_for_avg':        _avg(pf[tid]),
            'points_against_avg':    _avg(pa[tid]),
            'home_points_for_avg':   _avg(h_pf[tid]) if h_pf[tid] else None,
            'home_points_against_avg': _avg(h_pa[tid]) if h_pa[tid] else None,
            'away_points_for_avg':   _avg(a_pf[tid]) if a_pf[tid] else None,
            'away_points_against_avg': _avg(a_pa[tid]) if a_pa[tid] else None,
            '_points_diff':          diff,
        }

    # Compute ladder position: rank by wins desc, then points_diff desc
    ranked = sorted(stats.keys(),
                    key=lambda t: (-stats[t]['wins'], -stats[t]['_points_diff']))
    for pos, tid in enumerate(ranked, start=1):
        stats[tid]['ladder_position'] = pos

    return stats


def upsert_stats(conn, stats: dict, dry_run: bool) -> None:
    """
    Upsert stats to team_stats for each team.
    elo_rating is intentionally omitted — set by bootstrap_elo_2026.py.
    """
    print(f"\n{'='*70}")
    if dry_run:
        print(f"DRY RUN — team_stats for season={SEASON} as_of_date={AS_OF_DATE}")
    else:
        print(f"Writing team_stats: season={SEASON} as_of_date={AS_OF_DATE}")
    print(f"{'='*70}")
    print(f"  {'Team':40}  {'GP':>3}  {'W':>3}  {'L':>3}  {'Win%':>6}  "
          f"{'PF':>5}  {'PA':>5}  {'Pos':>3}")
    print(f"  {'-'*40}  {'---':>3}  {'---':>3}  {'---':>3}  {'------':>6}  "
          f"{'-----':>5}  {'-----':>5}  {'---':>3}")

    for tid, s in sorted(stats.items(), key=lambda x: x[1]['ladder_position']):
        print(
            f"  {s['team_name']:40}  {s['games_played']:>3}  {s['wins']:>3}  "
            f"{s['losses']:>3}  {s['win_pct']:>6.3f}  "
            f"{s['points_for_avg']:>5.1f}  {s['points_against_avg']:>5.1f}  "
            f"{s['ladder_position']:>3}"
        )

        if dry_run:
            continue

        conn.execute(
            """
            INSERT INTO team_stats (
                team_id, season, as_of_date,
                games_played, wins, losses, win_pct, ladder_position,
                points_for_avg, points_against_avg,
                home_points_for_avg, home_points_against_avg,
                away_points_for_avg, away_points_against_avg,
                elo_rating, attack_rating, defence_rating, recent_form_rating,
                run_metres_pg, post_contact_metres_pg,
                completion_rate, errors_pg, penalties_pg,
                kick_metres_pg, ruck_speed_score
            ) VALUES (
                ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                NULL, NULL, NULL, NULL,
                NULL, NULL,
                NULL, NULL, NULL,
                NULL, NULL
            )
            ON CONFLICT(team_id, season, as_of_date) DO UPDATE SET
                games_played            = excluded.games_played,
                wins                    = excluded.wins,
                losses                  = excluded.losses,
                win_pct                 = excluded.win_pct,
                ladder_position         = excluded.ladder_position,
                points_for_avg          = excluded.points_for_avg,
                points_against_avg      = excluded.points_against_avg,
                home_points_for_avg     = excluded.home_points_for_avg,
                home_points_against_avg = excluded.home_points_against_avg,
                away_points_for_avg     = excluded.away_points_for_avg,
                away_points_against_avg = excluded.away_points_against_avg
            """,
            (
                tid, SEASON, AS_OF_DATE,
                s['games_played'], s['wins'], s['losses'],
                s['win_pct'], s['ladder_position'],
                s['points_for_avg'], s['points_against_avg'],
                s['home_points_for_avg'], s['home_points_against_avg'],
                s['away_points_for_avg'], s['away_points_against_avg'],
            ),
        )

    if not dry_run:
        conn.commit()
        print(f"\nCommitted {len(stats)} team_stats rows.")


def main():
    parser = argparse.ArgumentParser(
        description=f'Build 2026 pre-R5 team_stats (as_of_date={AS_OF_DATE})'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Print stats only — no DB writes')
    parser.add_argument('--settings', default='config/settings.yaml')
    args = parser.parse_args()

    with open(args.settings) as f:
        settings = yaml.safe_load(f)
    db_path = settings.get('database', {}).get('path', 'data/model.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print(f"Loading 2026 matches before {R5_CUTOFF} ...")
    matches = load_matches(conn)
    if not matches:
        print(f"ERROR: no 2026 matches found before {R5_CUTOFF}. "
              "Run load_seasons_2025_2026.py first.", file=sys.stderr)
        conn.close()
        sys.exit(1)

    print(f"  Found {len(matches)} matches across "
          f"{len(set(m['home_team_id'] for m in matches) | set(m['away_team_id'] for m in matches))} "
          f"teams")

    stats = compute_stats(matches)
    upsert_stats(conn, stats, dry_run=args.dry_run)

    conn.close()
    if args.dry_run:
        print('\nDRY RUN — no writes performed.')
    else:
        print('Done.')


if __name__ == '__main__':
    main()
