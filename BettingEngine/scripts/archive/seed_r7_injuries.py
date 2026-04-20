"""
scripts/seed_r7_injuries.py

Load R7 2026 pre-aggregated injury totals (sourced from
nrl_injury_tier_manual_round6_v3_cap6.xlsx) into team_injury_totals.

Usage:
    python scripts/seed_r7_injuries.py [--dry-run]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'data' / 'model.db'

# Pre-aggregated injury burden per team for R7 2026.
# Values are "Total points out (capped 6)" from the spreadsheet.
R7_INJURY_TOTALS = {
    'Brisbane Broncos':                   5.75,
    'Canterbury-Bankstown Bulldogs':      3.00,
    'North Queensland Cowboys':           2.00,
    'Dolphins':                           3.50,
    'St. George Illawarra Dragons':       4.50,
    'Parramatta Eels':                    5.00,
    'Newcastle Knights':                  6.00,
    'Penrith Panthers':                   2.25,
    'South Sydney Rabbitohs':             3.25,
    'Canberra Raiders':                   2.25,
    'Sydney Roosters':                    2.75,
    'Manly-Warringah Sea Eagles':         1.00,
    'Cronulla-Sutherland Sharks':         3.00,
    'Melbourne Storm':                    2.50,
    'Gold Coast Titans':                  1.50,
    'New Zealand Warriors':               4.75,
    'Wests Tigers':                       3.75,
}

SEASON = 2026
ROUND = 7


def main():
    parser = argparse.ArgumentParser(description='Seed R7 injury totals')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Resolve match_id and team_id for every R7 match
    matches = conn.execute(
        """
        SELECT m.match_id, m.home_team_id, m.away_team_id,
               h.team_name AS home_name, a.team_name AS away_name
        FROM matches m
        JOIN teams h ON h.team_id = m.home_team_id
        JOIN teams a ON a.team_id = m.away_team_id
        WHERE m.season = ? AND m.round_number = ?
        """,
        (SEASON, ROUND),
    ).fetchall()

    if not matches:
        print(f'ERROR: no R{ROUND} matches found for season {SEASON}', file=sys.stderr)
        sys.exit(1)

    # Build team_name → team_id map from R7 matches
    team_id_map = {}
    for m in matches:
        team_id_map[m['home_name']] = m['home_team_id']
        team_id_map[m['away_name']] = m['away_team_id']

    # Build match lookup: team_id → match_id (a team plays once per round)
    team_match_map = {}
    for m in matches:
        team_match_map[m['home_team_id']] = m['match_id']
        team_match_map[m['away_team_id']] = m['match_id']

    rows_to_upsert = []
    for team_name, total_pts in sorted(R7_INJURY_TOTALS.items()):
        if team_name not in team_id_map:
            print(f'  WARN: team not in R7 matches: {team_name!r} — skipped')
            continue
        team_id = team_id_map[team_name]
        match_id = team_match_map[team_id]
        rows_to_upsert.append((match_id, team_id, total_pts))

    print(f'Seeding {len(rows_to_upsert)} injury total rows for R{ROUND} {SEASON}')
    for match_id, team_id, pts in rows_to_upsert:
        # Find team name for display
        tname = next(n for n, tid in team_id_map.items() if tid == team_id)
        print(f'  match={match_id}  team={team_id:3d}  {tname}: {pts}')

    if args.dry_run:
        print('[dry-run] no changes written')
        conn.close()
        return

    conn.executemany(
        """
        INSERT INTO team_injury_totals (match_id, team_id, total_injury_pts, source)
        VALUES (?, ?, ?, 'spreadsheet')
        ON CONFLICT(match_id, team_id) DO UPDATE SET
            total_injury_pts = excluded.total_injury_pts,
            source           = excluded.source,
            created_at       = CURRENT_TIMESTAMP
        """,
        rows_to_upsert,
    )
    conn.commit()
    print('Done.')
    conn.close()


if __name__ == '__main__':
    main()
