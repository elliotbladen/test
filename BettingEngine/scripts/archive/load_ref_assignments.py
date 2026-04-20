#!/usr/bin/env python3
"""
scripts/load_ref_assignments.py

Load weekly referee assignments from JSON into the database.

For each item:
  1. Resolve home_team + away_team → match_id
  2. Resolve referee name → referee_id (get_or_create_referee)
  3. Insert/update weekly_ref_assignments (ON CONFLICT DO UPDATE)
  4. Update matches.referee_id

Prints a summary table per game.

USAGE
-----
    python scripts/load_ref_assignments.py --input assignments.json [--dry-run]
    python scripts/load_ref_assignments.py --json '[{"season":2026,...}]' [--dry-run]

JSON FORMAT
-----------
Array of objects:
    [
      {
        "season": 2026,
        "round": 7,
        "home_team": "Brisbane Broncos",
        "away_team": "North Queensland Cowboys",
        "referee": "Gerard Sutton"
      }
    ]
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from db.queries import get_or_create_referee

# Canonical team name mapping
NAME_MAP = {
    'Canterbury Bulldogs':      'Canterbury-Bankstown Bulldogs',
    'Cronulla Sharks':          'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':         'Manly-Warringah Sea Eagles',
    'North QLD Cowboys':        'North Queensland Cowboys',
    'St George Dragons':        'St. George Illawarra Dragons',
}


def canonical(name: str) -> str:
    """Map alternate team names to canonical DB names."""
    return NAME_MAP.get(name.strip(), name.strip())


def resolve_match(conn: sqlite3.Connection, season: int, round_number: int,
                  home_name: str, away_name: str):
    """
    Look up match_id by season, round_number, home/away team names.
    Returns (match_id, home_team_id, away_team_id) or (None, None, None).
    """
    home_can = canonical(home_name)
    away_can = canonical(away_name)

    row = conn.execute(
        """
        SELECT m.match_id, m.home_team_id, m.away_team_id
        FROM matches m
        JOIN teams ht ON ht.team_id = m.home_team_id
        JOIN teams at ON at.team_id = m.away_team_id
        WHERE m.season = ?
          AND m.round_number = ?
          AND ht.team_name = ?
          AND at.team_name = ?
        """,
        (season, round_number, home_can, away_can)
    ).fetchone()

    if row:
        return row['match_id'], row['home_team_id'], row['away_team_id']
    return None, None, None


def get_referee_bucket(conn: sqlite3.Connection, referee_id: int) -> str:
    """Return bucket string for a referee, or 'unknown' if no profile exists."""
    row = conn.execute(
        "SELECT bucket FROM referee_profiles WHERE referee_id = ?",
        (referee_id,)
    ).fetchone()
    return row['bucket'] if row else 'unknown'


def process_assignments(conn: sqlite3.Connection, items: list, dry_run: bool) -> None:
    """Process a list of assignment dicts and write to DB."""
    now = datetime.utcnow().isoformat()

    print(f"\n{'─'*100}")
    print(f"  {'Round':>5}  {'Matchup':<54}  {'Referee':<26}  {'Bucket':<16}  Status")
    print(f"{'─'*100}")

    ok = 0
    errors = 0

    for item in items:
        season      = int(item.get('season', 2026))
        round_num   = int(item.get('round', 0))
        home_name   = str(item.get('home_team', '')).strip()
        away_name   = str(item.get('away_team', '')).strip()
        ref_name    = str(item.get('referee', '')).strip()

        matchup = f"{canonical(home_name)} vs {canonical(away_name)}"

        if not round_num or not home_name or not away_name or not ref_name:
            print(f"  {'?':>5}  {matchup:<54}  {ref_name:<26}  {'?':<16}  SKIP (missing fields)")
            errors += 1
            continue

        match_id, _, _ = resolve_match(conn, season, round_num, home_name, away_name)
        if match_id is None:
            print(f"  {round_num:>5}  {matchup:<54}  {ref_name:<26}  {'?':<16}  ERROR (match not found)")
            errors += 1
            continue

        ref_id = get_or_create_referee(conn, ref_name)
        bucket = get_referee_bucket(conn, ref_id)

        if not dry_run:
            # Insert/update weekly_ref_assignments
            conn.execute(
                """
                INSERT INTO weekly_ref_assignments
                    (match_id, referee_id, season, round_number, source, created_at)
                VALUES (?, ?, ?, ?, 'json_loader', ?)
                ON CONFLICT(match_id) DO UPDATE SET
                    referee_id   = excluded.referee_id,
                    source       = excluded.source,
                    season       = excluded.season,
                    round_number = excluded.round_number
                """,
                (match_id, ref_id, season, round_num, now)
            )

            # Update matches.referee_id
            conn.execute(
                "UPDATE matches SET referee_id = ? WHERE match_id = ?",
                (ref_id, match_id)
            )
            conn.commit()
            status = 'WRITTEN'
        else:
            status = 'DRY-RUN'

        print(f"  {round_num:>5}  {matchup:<54}  {ref_name:<26}  {bucket:<16}  {status}")
        ok += 1

    print(f"{'─'*100}")
    print(f"  {ok} assignments processed, {errors} errors.")


def main():
    parser = argparse.ArgumentParser(description='Load weekly referee assignments from JSON')
    parser.add_argument('--settings',  default='config/settings.yaml')
    parser.add_argument('--input',     default=None,
                        help='Path to JSON file with assignment array')
    parser.add_argument('--json',      default=None,
                        help='Inline JSON string (alternative to --input)')
    parser.add_argument('--season',    type=int, default=2026,
                        help='Default season if not specified in items (default: 2026)')
    parser.add_argument('--dry-run',   action='store_true')
    args = parser.parse_args()

    if not args.input and not args.json:
        print("ERROR: provide --input <file.json> or --json '<array>'")
        sys.exit(1)

    settings = yaml.safe_load(open(args.settings))
    db_path  = settings['database']['path']

    if args.json:
        items = json.loads(args.json)
    else:
        items = json.loads(Path(args.input).read_text())

    if not isinstance(items, list):
        print("ERROR: JSON must be an array of assignment objects")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    mode = 'DRY RUN' if args.dry_run else 'WRITE'
    print(f"\nLoad referee assignments — mode={mode}")
    print(f"DB: {db_path}  |  {len(items)} items")

    process_assignments(conn, items, args.dry_run)

    conn.close()


if __name__ == '__main__':
    main()
