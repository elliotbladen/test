#!/usr/bin/env python3
"""
scripts/load_injury_round.py

Load per-player injury data into the injury_reports table.

For each item, resolves team name and match, then inserts a row.
Existing rows for the same (match_id, team_id, player_name) are replaced.

USAGE
-----
    python scripts/load_injury_round.py --json '[...]' [--dry-run]
    python scripts/load_injury_round.py --input injuries.json [--dry-run]

JSON FORMAT
-----------
Array of objects:
    [
      {
        "season":         2026,
        "round":          7,
        "team":           "Brisbane Broncos",
        "player":         "Adam Reynolds",
        "role":           "halfback",
        "importance_tier":"elite",
        "status":         "out",
        "notes":          "hamstring"
      }
    ]

Valid roles:        fullback, halfback, five_eighth, hooker, pack, other
Valid tiers:        elite, key, rotation
Valid statuses:     out, doubtful, managed, available

Notes and source_url are optional.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

# Canonical team name mapping (same as load_ref_assignments)
NAME_MAP = {
    'Canterbury Bulldogs':      'Canterbury-Bankstown Bulldogs',
    'Cronulla Sharks':          'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':         'Manly-Warringah Sea Eagles',
    'North QLD Cowboys':        'North Queensland Cowboys',
    'St George Dragons':        'St. George Illawarra Dragons',
    # Short nicknames
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


def canonical(name: str) -> str:
    return NAME_MAP.get(name.strip(), name.strip())


def resolve_team(conn: sqlite3.Connection, team_name: str):
    row = conn.execute(
        "SELECT team_id FROM teams WHERE team_name = ?", (canonical(team_name),)
    ).fetchone()
    return row['team_id'] if row else None


def resolve_match(conn: sqlite3.Connection, season: int, round_number: int, team_id: int):
    """Find a match_id where team plays (home or away) in that round."""
    row = conn.execute(
        """
        SELECT match_id FROM matches
        WHERE season = ? AND round_number = ?
          AND (home_team_id = ? OR away_team_id = ?)
        """,
        (season, round_number, team_id, team_id),
    ).fetchone()
    return row['match_id'] if row else None


def process_injuries(conn: sqlite3.Connection, items: list, dry_run: bool) -> None:
    now = datetime.utcnow().isoformat()

    print(f"\n{'─'*110}")
    print(f"  {'Round':>5}  {'Team':<32}  {'Player':<22}  {'Role':<14}  {'Tier':<10}  {'Status':<10}  Result")
    print(f"{'─'*110}")

    ok = 0
    errors = 0

    for item in items:
        season     = int(item.get('season', 2026))
        round_num  = int(item.get('round', 0))
        team_name  = str(item.get('team', '')).strip()
        player     = str(item.get('player', '')).strip()
        role       = str(item.get('role', 'other')).strip().lower()
        tier       = str(item.get('importance_tier', 'rotation')).strip().lower()
        status     = str(item.get('status', 'out')).strip().lower()
        notes      = item.get('notes')
        source_url = item.get('source_url')

        display = f"{canonical(team_name):<32}"

        if not round_num or not team_name or not player:
            print(f"  {'?':>5}  {display}  {player:<22}  {role:<14}  {tier:<10}  {status:<10}  SKIP (missing fields)")
            errors += 1
            continue

        if role not in VALID_ROLES:
            role = 'other'
        if tier not in VALID_TIERS:
            tier = 'rotation'
        if status not in VALID_STATUSES:
            print(f"  {round_num:>5}  {display}  {player:<22}  {role:<14}  {tier:<10}  {status:<10}  ERROR (invalid status)")
            errors += 1
            continue

        team_id = resolve_team(conn, team_name)
        if team_id is None:
            print(f"  {round_num:>5}  {display}  {player:<22}  {role:<14}  {tier:<10}  {status:<10}  ERROR (team not found)")
            errors += 1
            continue

        match_id = resolve_match(conn, season, round_num, team_id)
        if match_id is None:
            print(f"  {round_num:>5}  {display}  {player:<22}  {role:<14}  {tier:<10}  {status:<10}  ERROR (match not found)")
            errors += 1
            continue

        if not dry_run:
            conn.execute(
                """
                INSERT INTO injury_reports
                    (match_id, team_id, player_name, player_role, importance_tier,
                     status, notes, source_url, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id, team_id, player_name) DO UPDATE SET
                    player_role      = excluded.player_role,
                    importance_tier  = excluded.importance_tier,
                    status           = excluded.status,
                    notes            = excluded.notes,
                    source_url       = excluded.source_url,
                    captured_at      = excluded.captured_at
                """,
                (match_id, team_id, player, role, tier, status, notes, source_url, now),
            )
            result_str = 'WRITTEN'
        else:
            result_str = 'DRY-RUN'

        print(f"  {round_num:>5}  {display}  {player:<22}  {role:<14}  {tier:<10}  {status:<10}  {result_str}")
        ok += 1

    if not dry_run:
        conn.commit()

    print(f"{'─'*110}")
    print(f"  {ok} players loaded, {errors} errors.")


def main():
    parser = argparse.ArgumentParser(description='Load injury data into injury_reports table')
    parser.add_argument('--settings', default='config/settings.yaml')
    parser.add_argument('--input',    default=None, help='Path to JSON file')
    parser.add_argument('--json',     default=None, help='Inline JSON string')
    parser.add_argument('--dry-run',  action='store_true')
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
        print("ERROR: JSON must be an array of injury objects")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Add UNIQUE constraint support — injury_reports may need it
    # Check if the constraint exists, apply as a soft-create otherwise
    mode = 'DRY RUN' if args.dry_run else 'WRITE'
    print(f"\nLoad injury data — mode={mode}")
    print(f"DB: {db_path}  |  {len(items)} players")

    process_injuries(conn, items, args.dry_run)
    conn.close()


if __name__ == '__main__':
    main()
