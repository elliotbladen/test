#!/usr/bin/env python3
"""
scripts/compute_season_end_stats.py

Compute and insert season-end team_stats from match results already in the DB.
Useful for deriving 2025 (and any other past season with results loaded) stats
for use as prior-season priors in Tier 1 calibration.

USAGE
-----
    python scripts/compute_season_end_stats.py --season 2025
    python scripts/compute_season_end_stats.py --season 2025 --dry-run
"""

import argparse
import sqlite3
import sys
import yaml
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))


def compute_team_stats_from_results(conn, season: int) -> list[dict]:
    """
    Aggregate match results into per-team season-end stats.
    Returns a list of dicts ready for insertion into team_stats.
    """
    rows = conn.execute("""
        SELECT
            m.home_team_id, m.away_team_id,
            r.home_score,   r.away_score,
            m.match_date,   m.round_number,
            m.venue_id,     m.home_team_id = m.home_team_id AS is_home
        FROM matches m
        JOIN results r ON m.match_id = r.match_id
        WHERE m.season = ?
          AND r.home_score IS NOT NULL
          AND r.away_score IS NOT NULL
        ORDER BY m.match_date
    """, (season,)).fetchall()

    teams = {r['home_team_id'] for r in rows} | {r['away_team_id'] for r in rows}

    stats = defaultdict(lambda: {
        'gp': 0, 'wins': 0, 'losses': 0,
        'pf': 0, 'pa': 0,
        'h_pf': 0, 'h_pa': 0, 'h_gp': 0,
        'a_pf': 0, 'a_pa': 0, 'a_gp': 0,
        'last_date': None,
    })

    for r in rows:
        ht   = r['home_team_id']
        at   = r['away_team_id']
        hs   = r['home_score']
        aws  = r['away_score']
        date = r['match_date']

        # Home team
        s = stats[ht]
        s['gp']   += 1
        s['pf']   += hs
        s['pa']   += aws
        s['h_pf'] += hs
        s['h_pa'] += aws
        s['h_gp'] += 1
        s['wins']   += 1 if hs > aws else 0
        s['losses'] += 1 if hs < aws else 0
        if s['last_date'] is None or date > s['last_date']:
            s['last_date'] = date

        # Away team
        s = stats[at]
        s['gp']   += 1
        s['pf']   += aws
        s['pa']   += hs
        s['a_pf'] += aws
        s['a_pa'] += hs
        s['a_gp'] += 1
        s['wins']   += 1 if aws > hs else 0
        s['losses'] += 1 if aws < hs else 0
        if s['last_date'] is None or date > s['last_date']:
            s['last_date'] = date

    results = []
    for team_id, s in stats.items():
        gp = s['gp']
        if gp == 0:
            continue
        h_gp = s['h_gp']
        a_gp = s['a_gp']
        results.append({
            'team_id':                  team_id,
            'season':                   season,
            'as_of_date':               s['last_date'],
            'games_played':             gp,
            'wins':                     s['wins'],
            'losses':                   s['losses'],
            'win_pct':                  round(s['wins'] / gp, 4),
            'points_for_avg':           round(s['pf'] / gp, 4),
            'points_against_avg':       round(s['pa'] / gp, 4),
            'home_points_for_avg':      round(s['h_pf'] / h_gp, 4) if h_gp else None,
            'home_points_against_avg':  round(s['h_pa'] / h_gp, 4) if h_gp else None,
            'away_points_for_avg':      round(s['a_pf'] / a_gp, 4) if a_gp else None,
            'away_points_against_avg':  round(s['a_pa'] / a_gp, 4) if a_gp else None,
        })

    return sorted(results, key=lambda x: x['team_id'])


def upsert_team_stats(conn, row: dict, dry_run: bool) -> str:
    """Insert or replace a team_stats row. Returns 'inserted' or 'skipped'."""
    # Check if already exists
    existing = conn.execute(
        "SELECT rowid FROM team_stats WHERE team_id=? AND season=? AND as_of_date=?",
        (row['team_id'], row['season'], row['as_of_date'])
    ).fetchone()

    if existing:
        return 'skipped'

    if not dry_run:
        conn.execute("""
            INSERT INTO team_stats (
                team_id, season, as_of_date,
                games_played, wins, losses, win_pct,
                points_for_avg, points_against_avg,
                home_points_for_avg, home_points_against_avg,
                away_points_for_avg, away_points_against_avg
            ) VALUES (
                :team_id, :season, :as_of_date,
                :games_played, :wins, :losses, :win_pct,
                :points_for_avg, :points_against_avg,
                :home_points_for_avg, :home_points_against_avg,
                :away_points_for_avg, :away_points_against_avg
            )
        """, row)
    return 'inserted'


def main():
    parser = argparse.ArgumentParser(description='Compute season-end team_stats from results')
    parser.add_argument('--season',   type=int, required=True)
    parser.add_argument('--dry-run',  action='store_true')
    parser.add_argument('--settings', default='config/settings.yaml')
    args = parser.parse_args()

    settings = yaml.safe_load(open(args.settings))
    conn     = sqlite3.connect(settings['database']['path'])
    conn.row_factory = sqlite3.Row

    print(f"\nComputing season-end team_stats for season={args.season} "
          f"({'DRY RUN' if args.dry_run else 'WRITE'}) ...\n")

    rows = compute_team_stats_from_results(conn, args.season)

    if not rows:
        print("  No results found — nothing to compute.")
        conn.close()
        return

    # Print team name lookup for display
    team_names = {
        r['team_id']: r['team_name']
        for r in conn.execute("SELECT team_id, team_name FROM teams").fetchall()
    }

    inserted = skipped = 0
    print(f"  {'Team':<40} {'GP':>4} {'W':>3} {'L':>3} {'PF/g':>6} {'PA/g':>6}  status")
    print(f"  {'-'*40} {'-'*4} {'-'*3} {'-'*3} {'-'*6} {'-'*6}  ------")
    for row in rows:
        status = upsert_team_stats(conn, row, args.dry_run)
        if status == 'inserted':
            inserted += 1
        else:
            skipped += 1
        name = team_names.get(row['team_id'], f"team_id={row['team_id']}")
        print(f"  {name:<40} {row['games_played']:>4} {row['wins']:>3} {row['losses']:>3} "
              f"{row['points_for_avg']:>6.2f} {row['points_against_avg']:>6.2f}  {status}")

    if not args.dry_run:
        conn.commit()

    print(f"\n  Total: {inserted} inserted, {skipped} already exist")
    if args.dry_run:
        print("  DRY RUN — nothing written to DB")

    conn.close()


if __name__ == '__main__':
    main()
