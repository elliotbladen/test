#!/usr/bin/env python3
"""
scripts/load_emotional_round.py

Load per-match emotional/human-context flags into the emotional_flags table.

For each item, resolves team name and match, then inserts a row.
Existing rows for the same (match_id, team_id, flag_type, player_name) are replaced.

USAGE
-----
    python scripts/load_emotional_round.py --json '[...]' [--dry-run]
    python scripts/load_emotional_round.py --input emotional.json [--dry-run]

JSON FORMAT
-----------
Array of objects:
    [
      {
        "season":       2026,
        "round":        8,
        "team":         "South Sydney Rabbitohs",
        "flag_type":    "milestone",
        "flag_strength":"normal",
        "player_name":  "Cody Walker",
        "notes":        "200th NRL game"
      },
      {
        "season":       2026,
        "round":        8,
        "team":         "Penrith Panthers",
        "flag_type":    "shame_blowout",
        "flag_strength":"major",
        "notes":        "Lost to Storm by 38 last week"
      }
    ]

Valid flag types:   milestone, new_coach, star_return, shame_blowout,
                    origin_boost, farewell, personal_tragedy, rivalry_derby,
                    must_win
Valid strengths:    minor, normal, major

player_name is optional (use for player-specific flags like milestone, star_return).
notes and source_url are optional.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

NAME_MAP = {
    'Canterbury Bulldogs':   'Canterbury-Bankstown Bulldogs',
    'Cronulla Sharks':       'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':      'Manly-Warringah Sea Eagles',
    'North QLD Cowboys':     'North Queensland Cowboys',
    'St George Dragons':     'St. George Illawarra Dragons',
    'Broncos':               'Brisbane Broncos',
    'Bulldogs':              'Canterbury-Bankstown Bulldogs',
    'Cowboys':               'North Queensland Cowboys',
    'Dolphins':              'Dolphins',
    'Dragons':               'St. George Illawarra Dragons',
    'Eels':                  'Parramatta Eels',
    'Knights':               'Newcastle Knights',
    'Panthers':              'Penrith Panthers',
    'Rabbitohs':             'South Sydney Rabbitohs',
    'Raiders':               'Canberra Raiders',
    'Roosters':              'Sydney Roosters',
    'Sea Eagles':            'Manly-Warringah Sea Eagles',
    'Sharks':                'Cronulla-Sutherland Sharks',
    'Storm':                 'Melbourne Storm',
    'Titans':                'Gold Coast Titans',
    'Warriors':              'New Zealand Warriors',
    'Wests Tigers':          'Wests Tigers',
}

VALID_FLAG_TYPES = {
    'milestone', 'new_coach', 'star_return', 'shame_blowout',
    'origin_boost', 'farewell', 'personal_tragedy', 'rivalry_derby', 'must_win',
}
VALID_STRENGTHS = {'minor', 'normal', 'major'}


def canonical(name: str) -> str:
    return NAME_MAP.get(name.strip(), name.strip())


def resolve_team(conn, team_name: str):
    row = conn.execute(
        "SELECT team_id FROM teams WHERE team_name = ?", (canonical(team_name),)
    ).fetchone()
    return row['team_id'] if row else None


def resolve_match(conn, season: int, round_number: int, team_id: int):
    row = conn.execute(
        """
        SELECT match_id FROM matches
        WHERE season = ? AND round_number = ?
          AND (home_team_id = ? OR away_team_id = ?)
        """,
        (season, round_number, team_id, team_id),
    ).fetchone()
    return row['match_id'] if row else None


def process_flags(conn, items: list, dry_run: bool) -> None:
    now = datetime.utcnow().isoformat()

    print(f"\n{'─'*120}")
    print(f"  {'Round':>5}  {'Team':<32}  {'Flag':<18}  {'Strength':<8}  {'Player':<22}  Result")
    print(f"{'─'*120}")

    ok = 0
    errors = 0

    for item in items:
        season     = int(item.get('season', 2026))
        round_num  = int(item.get('round', 0))
        team_name  = str(item.get('team', '')).strip()
        flag_type  = str(item.get('flag_type', '')).strip().lower()
        strength   = str(item.get('flag_strength', 'normal')).strip().lower()
        player     = item.get('player_name') or item.get('player') or None
        notes      = item.get('notes')
        source_url = item.get('source_url')

        display = f"{canonical(team_name):<32}"

        if not round_num or not team_name or not flag_type:
            print(f"  {'?':>5}  {display}  {flag_type:<18}  {strength:<8}  {'':22}  SKIP (missing fields)")
            errors += 1
            continue

        if flag_type not in VALID_FLAG_TYPES:
            print(f"  {round_num:>5}  {display}  {flag_type:<18}  {strength:<8}  {'':22}  ERROR (invalid flag_type)")
            errors += 1
            continue

        if strength not in VALID_STRENGTHS:
            strength = 'normal'

        team_id = resolve_team(conn, team_name)
        if team_id is None:
            print(f"  {round_num:>5}  {display}  {flag_type:<18}  {strength:<8}  {'':22}  ERROR (team not found)")
            errors += 1
            continue

        match_id = resolve_match(conn, season, round_num, team_id)
        if match_id is None:
            print(f"  {round_num:>5}  {display}  {flag_type:<18}  {strength:<8}  {'':22}  ERROR (match not found)")
            errors += 1
            continue

        player_disp = (player or '')[:22]

        if not dry_run:
            # Delete existing row matching the unique index (uses COALESCE on player_name)
            conn.execute(
                """
                DELETE FROM emotional_flags
                WHERE match_id = ? AND team_id = ? AND flag_type = ?
                  AND COALESCE(player_name, '') = COALESCE(?, '')
                """,
                (match_id, team_id, flag_type, player),
            )
            conn.execute(
                """
                INSERT INTO emotional_flags
                    (match_id, team_id, flag_type, flag_strength,
                     player_name, notes, source_url, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (match_id, team_id, flag_type, strength,
                 player, notes, source_url, now),
            )
            result_str = 'WRITTEN'
        else:
            result_str = 'DRY-RUN'

        print(f"  {round_num:>5}  {display}  {flag_type:<18}  {strength:<8}  {player_disp:<22}  {result_str}")
        ok += 1

    if not dry_run:
        conn.commit()

    print(f"{'─'*120}")
    print(f"  {ok} flags loaded, {errors} errors.")


def main():
    parser = argparse.ArgumentParser(description='Load emotional flags into emotional_flags table')
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
        print("ERROR: JSON must be an array of flag objects")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    mode = 'DRY RUN' if args.dry_run else 'WRITE'
    print(f"\nLoad emotional flags — mode={mode}")
    print(f"DB: {db_path}  |  {len(items)} flags")

    process_flags(conn, items, args.dry_run)
    conn.close()


if __name__ == '__main__':
    main()
