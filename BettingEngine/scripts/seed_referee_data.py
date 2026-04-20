#!/usr/bin/env python3
"""
scripts/seed_referee_data.py

Seed Tier 6 referee data into the database.

Does two things:
1. Loads data/import/referee_profiles_2025.csv
   → seeds referees + referee_profiles tables

2. Reads data/import/ref_match_2025.csv (if non-empty),
   joins to 2025 DB results, computes team_ref_bucket_stats
   (bucket_edge = avg margin from team's perspective under that bucket's referees).
   Minimum 3 games required; otherwise stores 0.0.

USAGE
-----
    python scripts/seed_referee_data.py [--dry-run]
    python scripts/seed_referee_data.py --settings config/settings.yaml
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from db.queries import get_or_create_referee

# Canonical team name mapping (xlsx short names → DB canonical names)
NAME_MAP = {
    'Canterbury Bulldogs':      'Canterbury-Bankstown Bulldogs',
    'Cronulla Sharks':          'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':         'Manly-Warringah Sea Eagles',
    'North QLD Cowboys':        'North Queensland Cowboys',
    'St George Dragons':        'St. George Illawarra Dragons',
}

PROFILES_CSV = Path('data/import/referee_profiles_2025.csv')
REF_MATCH_CSV = Path('data/import/ref_match_2025.csv')
MIN_GAMES_FOR_EDGE = 3


def canonical(name: str) -> str:
    """Map short/alternate team names to canonical DB names."""
    return NAME_MAP.get(name.strip(), name.strip())


def load_referee_profiles(conn: sqlite3.Connection, dry_run: bool) -> dict:
    """
    Read referee_profiles_2025.csv, seed referees + referee_profiles.

    Returns dict: {referee_name: {'referee_id': int, 'bucket': str}}
    """
    if not PROFILES_CSV.exists():
        print(f"  ERROR: {PROFILES_CSV} not found")
        return {}

    profiles = {}
    with PROFILES_CSV.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref_name = row['referee_name'].strip()
            bucket   = row['bucket'].strip()
            notes    = row.get('notes', '').strip() or None

            if not ref_name or not bucket:
                continue

            ref_id = get_or_create_referee(conn, ref_name)

            # Upsert referee_profile
            existing = conn.execute(
                "SELECT referee_id FROM referee_profiles WHERE referee_id = ?",
                (ref_id,)
            ).fetchone()

            now = datetime.utcnow().isoformat()
            if existing:
                if not dry_run:
                    conn.execute(
                        """UPDATE referee_profiles
                           SET bucket=?, notes=?, updated_at=?
                           WHERE referee_id=?""",
                        (bucket, notes, now, ref_id)
                    )
                    conn.commit()
                print(f"  UPDATED referee_profile: {ref_name} → {bucket}")
            else:
                if not dry_run:
                    conn.execute(
                        """INSERT INTO referee_profiles (referee_id, bucket, notes, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (ref_id, bucket, notes, now, now)
                    )
                    conn.commit()
                print(f"  INSERTED referee_profile: {ref_name} → {bucket}")

            profiles[ref_name] = {'referee_id': ref_id, 'bucket': bucket}

    print(f"\n  Loaded {len(profiles)} referee profiles.")
    return profiles


def load_ref_match_data(conn: sqlite3.Connection, profiles: dict, dry_run: bool) -> None:
    """
    Read ref_match_2025.csv, join to DB 2025 results, compute team_ref_bucket_stats.

    bucket_edge = avg signed margin from the team's perspective under that bucket's refs.
    Positive = team won. Home: home_score - away_score. Away: away_score - home_score.
    Minimum MIN_GAMES_FOR_EDGE games required; stores 0.0 otherwise.
    """
    if not REF_MATCH_CSV.exists():
        print(f"  {REF_MATCH_CSV} not found — skipping bucket stats.")
        return

    # Read CSV rows
    rows = []
    with REF_MATCH_CSV.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print(f"  {REF_MATCH_CSV} is empty — skipping bucket stats.")
        return

    # Build bucket lookup: referee_name → bucket
    bucket_by_name = {name: info['bucket'] for name, info in profiles.items()}

    # Get all 2025 results from DB
    results = conn.execute(
        """
        SELECT m.match_id, m.home_team_id, m.away_team_id,
               r.home_score, r.away_score,
               ht.team_name AS home_team, at.team_name AS away_team,
               m.match_date
        FROM matches m
        JOIN results r ON r.match_id = m.match_id
        JOIN teams ht ON ht.team_id = m.home_team_id
        JOIN teams at ON at.team_id = m.away_team_id
        WHERE m.season = 2025
        """
    ).fetchall()

    # Index results by (match_date, home_team, away_team)
    result_index = {}
    for row in results:
        key = (row['match_date'], row['home_team'], row['away_team'])
        result_index[key] = dict(row)

    # team_id lookup
    teams = conn.execute("SELECT team_id, team_name FROM teams").fetchall()
    team_id_by_name = {t['team_name']: t['team_id'] for t in teams}

    # Accumulate: {(team_id, bucket): [signed_margins]}
    from collections import defaultdict
    bucket_margins = defaultdict(list)
    matched = 0
    unmatched = 0

    for csv_row in rows:
        match_date  = csv_row.get('match_date', '').strip()
        home_team   = canonical(csv_row.get('home_team', ''))
        away_team   = canonical(csv_row.get('away_team', ''))
        ref_name    = csv_row.get('referee', '').strip()

        if not match_date or not home_team or not away_team or not ref_name:
            continue

        bucket = bucket_by_name.get(ref_name)
        if bucket is None:
            print(f"  WARNING: referee '{ref_name}' not in profiles — skipping row")
            continue

        result = result_index.get((match_date, home_team, away_team))
        if result is None:
            print(f"  WARNING: no DB result for {match_date} {home_team} vs {away_team}")
            unmatched += 1
            continue

        matched += 1
        home_id    = result['home_team_id']
        away_id    = result['away_team_id']
        home_score = result['home_score']
        away_score = result['away_score']

        # From home team's perspective
        home_margin = home_score - away_score
        bucket_margins[(home_id, bucket)].append(home_margin)

        # From away team's perspective
        away_margin = away_score - home_score
        bucket_margins[(away_id, bucket)].append(away_margin)

    print(f"\n  Ref-match join: {matched} matched, {unmatched} unmatched")

    # Compute and upsert team_ref_bucket_stats for all teams × buckets
    now = datetime.utcnow().isoformat()
    buckets_all = ('whistle_heavy', 'flow_heavy', 'neutral')

    written = 0
    for team_row in teams:
        team_id   = team_row['team_id']
        team_name = team_row['team_name']

        for bucket in buckets_all:
            margins = bucket_margins.get((team_id, bucket), [])
            games   = len(margins)
            if games >= MIN_GAMES_FOR_EDGE:
                edge = round(sum(margins) / games, 3)
            else:
                edge = 0.0

            if not dry_run:
                conn.execute(
                    """
                    INSERT INTO team_ref_bucket_stats
                        (team_id, bucket, season, games, bucket_edge, created_at, updated_at)
                    VALUES (?, ?, 2025, ?, ?, ?, ?)
                    ON CONFLICT(team_id, bucket, season) DO UPDATE SET
                        games      = excluded.games,
                        bucket_edge= excluded.bucket_edge,
                        updated_at = excluded.updated_at
                    """,
                    (team_id, bucket, games, edge, now, now)
                )
                conn.commit()
                written += 1

            if games > 0:
                print(f"  {team_name:<45} bucket={bucket:<15} games={games}  edge={edge:+.3f}"
                      + (" [below MIN — stored 0.0]" if games < MIN_GAMES_FOR_EDGE else ""))

    if dry_run:
        print(f"\n  DRY RUN — {len(teams) * len(buckets_all)} bucket stats would be written.")
    else:
        print(f"\n  {written} team_ref_bucket_stats rows written.")


def main():
    parser = argparse.ArgumentParser(description='Seed Tier 6 referee data')
    parser.add_argument('--settings', default='config/settings.yaml')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print actions without writing to DB')
    args = parser.parse_args()

    settings = yaml.safe_load(open(args.settings))
    db_path  = settings['database']['path']

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    mode = 'DRY RUN' if args.dry_run else 'WRITE'
    print(f"\nSeed referee data — mode={mode}")
    print(f"DB: {db_path}\n")

    print("=== Step 1: referee_profiles ===")
    profiles = load_referee_profiles(conn, args.dry_run)

    print("\n=== Step 2: team_ref_bucket_stats ===")
    load_ref_match_data(conn, profiles, args.dry_run)

    conn.close()
    print("\nDone.")


if __name__ == '__main__':
    main()
