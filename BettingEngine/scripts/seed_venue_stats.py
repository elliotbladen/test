#!/usr/bin/env python3
"""
scripts/seed_venue_stats.py

Seed team_venue_stats and venue_profiles from 2023 + 2025 match results.

team_venue_stats:
    For each (team_id, venue_id) pair, computes avg_margin (team's signed
    perspective) across all games — both home and away — at that venue.
    venue_edge = avg_margin if games >= 3, else 0.0

venue_profiles:
    For each venue, computes avg_total_score across all 2023 + 2025 matches
    with results, plus total_edge = avg_total_score - league_avg_total.

USAGE
-----
    python3 scripts/seed_venue_stats.py [--dry-run]
    python3 scripts/seed_venue_stats.py --settings config/settings.yaml
"""

import argparse
import sqlite3
import sys
import yaml
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SEED_SEASONS = (2023, 2025)
LEAGUE_AVG_TOTAL = 47.0  # from tiers.yaml tier1_baseline.league_avg_total
MIN_GAMES_FOR_EDGE = 5


def load_settings(path: str) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def seed_venue_stats(conn: sqlite3.Connection, dry_run: bool) -> dict:
    """
    Compute and insert/replace team_venue_stats and venue_profiles.

    Returns a summary dict with counts for reporting.
    """
    season_placeholders = ', '.join('?' for _ in SEED_SEASONS)

    # Fetch all matches with results for seed seasons
    rows = conn.execute(f"""
        SELECT
            m.match_id,
            m.home_team_id,
            m.away_team_id,
            m.venue_id,
            m.season,
            r.home_score,
            r.away_score,
            r.total_score,
            r.margin
        FROM matches m
        JOIN results r ON m.match_id = r.match_id
        WHERE m.season IN ({season_placeholders})
          AND r.result_status = 'final'
        ORDER BY m.match_id
    """, list(SEED_SEASONS)).fetchall()

    print(f"  Loaded {len(rows)} completed matches from seasons {SEED_SEASONS}")

    # --- Accumulate team_venue_stats ---
    # Key: (team_id, venue_id) → list of signed margins from team's perspective
    team_venue_margins: dict[tuple, list] = defaultdict(list)

    for row in rows:
        home_tid = row['home_team_id']
        away_tid = row['away_team_id']
        venue_id = row['venue_id']
        margin   = row['margin']   # = home_score - away_score

        # Home team: signed margin is positive when they win
        team_venue_margins[(home_tid, venue_id)].append(float(margin))
        # Away team: signed margin is negative of home margin
        team_venue_margins[(away_tid, venue_id)].append(float(-margin))

    # --- Accumulate venue_profiles ---
    # Key: venue_id → list of total_scores
    venue_totals: dict[int, list] = defaultdict(list)

    for row in rows:
        venue_totals[row['venue_id']].append(float(row['total_score']))

    # --- Resolve venue names ---
    venue_names: dict[int, str] = {}
    for v_row in conn.execute("SELECT venue_id, venue_name FROM venues").fetchall():
        venue_names[v_row['venue_id']] = v_row['venue_name']

    # --- Build team_venue_stats records ---
    tvs_records = []
    for (team_id, venue_id), margins in sorted(team_venue_margins.items()):
        games = len(margins)
        avg_margin     = sum(margins) / games
        overall_margin = sum(margins)
        venue_edge     = avg_margin if games >= MIN_GAMES_FOR_EDGE else 0.0
        tvs_records.append({
            'team_id':        team_id,
            'venue_id':       venue_id,
            'games':          games,
            'avg_margin':     round(avg_margin, 4),
            'overall_margin': round(overall_margin, 2),
            'venue_edge':     round(venue_edge, 4),
        })

    # --- Build venue_profiles records ---
    vp_records = []
    for venue_id, totals in sorted(venue_totals.items()):
        games_in_sample = len(totals)
        avg_total_score = sum(totals) / games_in_sample
        total_edge      = (avg_total_score - LEAGUE_AVG_TOTAL) if games_in_sample >= MIN_GAMES_FOR_EDGE else 0.0
        vp_records.append({
            'venue_id':        venue_id,
            'venue_name':      venue_names.get(venue_id, f'venue_{venue_id}'),
            'avg_total_score': round(avg_total_score, 4),
            'league_avg_total': LEAGUE_AVG_TOTAL,
            'total_edge':      round(total_edge, 4),
            'games_in_sample': games_in_sample,
        })

    # --- Write to DB ---
    if not dry_run:
        for rec in tvs_records:
            conn.execute("""
                INSERT OR REPLACE INTO team_venue_stats
                    (team_id, venue_id, games, avg_margin, overall_margin, venue_edge, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                rec['team_id'], rec['venue_id'], rec['games'],
                rec['avg_margin'], rec['overall_margin'], rec['venue_edge'],
            ))

        for rec in vp_records:
            conn.execute("""
                INSERT OR REPLACE INTO venue_profiles
                    (venue_id, venue_name, avg_total_score, league_avg_total,
                     total_edge, games_in_sample, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                rec['venue_id'], rec['venue_name'], rec['avg_total_score'],
                rec['league_avg_total'], rec['total_edge'], rec['games_in_sample'],
            ))

        conn.commit()
        print(f"  Written {len(tvs_records)} team_venue_stats rows")
        print(f"  Written {len(vp_records)} venue_profiles rows")
    else:
        print(f"  DRY RUN: would write {len(tvs_records)} team_venue_stats rows")
        print(f"  DRY RUN: would write {len(vp_records)} venue_profiles rows")

    return {
        'tvs_records':   tvs_records,
        'vp_records':    vp_records,
        'venue_names':   venue_names,
    }


def print_summary(summary: dict) -> None:
    tvs_records = summary['tvs_records']
    vp_records  = summary['vp_records']
    venue_names = summary['venue_names']

    # Count combos with games >= MIN_GAMES_FOR_EDGE
    qualified = [r for r in tvs_records if r['games'] >= MIN_GAMES_FOR_EDGE]
    print(f"\n  team_venue_stats: {len(tvs_records)} total rows, "
          f"{len(qualified)} with games >= {MIN_GAMES_FOR_EDGE}")

    # Top 10 venue scoring edges
    sorted_vp = sorted(vp_records, key=lambda r: r['total_edge'], reverse=True)
    print(f"\n  Top 10 venues by total_edge (avg_total - {LEAGUE_AVG_TOTAL:.1f}):")
    print(f"  {'Venue':<35}  {'Games':>5}  {'AvgTotal':>9}  {'Edge':>7}")
    print(f"  {'─'*35}  {'─'*5}  {'─'*9}  {'─'*7}")
    for rec in sorted_vp[:10]:
        name = rec['venue_name'] or f"venue_{rec['venue_id']}"
        print(f"  {name:<35}  {rec['games_in_sample']:>5}  "
              f"{rec['avg_total_score']:>9.2f}  {rec['total_edge']:>+7.2f}")

    # Top 10 team/venue combos by |venue_edge| (games >= MIN_GAMES)
    q_sorted = sorted(qualified, key=lambda r: abs(r['venue_edge']), reverse=True)
    print(f"\n  Top 10 team_venue combos by |venue_edge| (games >= {MIN_GAMES_FOR_EDGE}):")

    # Need team names
    # We stored team_id — try to look up team names from the in-memory connection
    # (we'll pass the conn into this function or re-query at call time)
    print(f"  {'team_id':>8}  {'venue_id':>8}  {'Games':>5}  {'AvgMrg':>8}  {'VenueEdge':>10}")
    print(f"  {'─'*8}  {'─'*8}  {'─'*5}  {'─'*8}  {'─'*10}")
    for rec in q_sorted[:10]:
        print(f"  {rec['team_id']:>8}  {rec['venue_id']:>8}  {rec['games']:>5}  "
              f"{rec['avg_margin']:>+8.2f}  {rec['venue_edge']:>+10.2f}")


def main():
    parser = argparse.ArgumentParser(
        description='Seed team_venue_stats and venue_profiles from 2023+2025 results'
    )
    parser.add_argument('--settings',  default='config/settings.yaml')
    parser.add_argument('--dry-run',   action='store_true',
                        help='Compute and print without writing to DB')
    args = parser.parse_args()

    settings = load_settings(args.settings)

    conn = sqlite3.connect(settings['database']['path'])
    conn.row_factory = sqlite3.Row

    mode = 'DRY RUN' if args.dry_run else 'WRITE'
    print(f"\nSeeding venue stats from seasons {SEED_SEASONS}  [mode={mode}]")

    summary = seed_venue_stats(conn, dry_run=args.dry_run)
    print_summary(summary)

    conn.close()
    print()


if __name__ == '__main__':
    main()
