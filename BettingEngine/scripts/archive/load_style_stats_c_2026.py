#!/usr/bin/env python3
"""
scripts/load_style_stats_c_2026.py

Load Tier 2 Family C (Physical Carry & Forward Dominance) stats into
team_style_stats for 2026.

Reads:  data/import/team_style_stats_c_2026.csv
Writes: team_style_stats.run_metres_pg
        WHERE season=2026 AND as_of_date=2026-03-24

Note: errors_pg (style inverted) and mt_pg (vulnerability) are already loaded
in team_style_stats from Family A and Family B respectively. Only run_metres_pg
is new.

USAGE
-----
    cd /path/to/Betting_model
    python scripts/load_style_stats_c_2026.py [--dry-run]
"""

import argparse
import sqlite3
import sys
import yaml
import pandas as pd
from pathlib import Path

CSV_PATH   = Path('data/import/team_style_stats_c_2026.csv')
SEASON     = 2026
AS_OF_DATE = '2026-03-24'
NUMERIC_COLS = ['run_metres_pg']


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(str(path))
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def validate(df: pd.DataFrame) -> list:
    errors = []
    required = ['team_id'] + NUMERIC_COLS
    missing = [c for c in required if c not in df.columns]
    if missing:
        errors.append(f"Missing columns: {missing}")
        return errors
    if len(df) != 17:
        errors.append(f"Expected 17 rows (one per team), got {len(df)}")
    for col in NUMERIC_COLS:
        if df[col].isnull().all():
            errors.append(f"All-null column (not filled in): {col}")
    return errors


def write_to_db(conn, df: pd.DataFrame, dry_run: bool) -> tuple:
    written = skipped = 0
    for _, row in df.iterrows():
        team_id = int(row['team_id'])

        existing = conn.execute(
            "SELECT style_stat_id FROM team_style_stats WHERE team_id=? AND season=? AND as_of_date=?",
            (team_id, SEASON, AS_OF_DATE),
        ).fetchone()

        updates = {}
        for col in NUMERIC_COLS:
            val = row.get(col)
            if pd.notna(val):
                try:
                    updates[col] = float(val)
                except (ValueError, TypeError):
                    print(f"  WARNING: cannot convert {col}={val!r} — skipping")

        if not updates:
            print(f"  SKIP team_id={team_id}: no numeric values to write")
            skipped += 1
            continue

        team_name = row.get('team', f'id={team_id}')
        rm = updates.get('run_metres_pg', '—')
        marker = "(dry-run)" if dry_run else "written"

        if not dry_run:
            if existing:
                set_clause = ', '.join(f"{col}=?" for col in updates)
                vals = list(updates.values()) + [existing[0]]
                conn.execute(
                    f"UPDATE team_style_stats SET {set_clause} WHERE style_stat_id=?", vals
                )
            else:
                cols = ['team_id', 'season', 'as_of_date'] + list(updates.keys())
                vals = [team_id, SEASON, AS_OF_DATE] + list(updates.values())
                placeholders = ', '.join('?' for _ in vals)
                conn.execute(
                    f"INSERT INTO team_style_stats ({', '.join(cols)}) VALUES ({placeholders})",
                    vals,
                )

        print(f"  {team_name:<40}  run_metres_pg={rm}  {marker}")
        written += 1

    if not dry_run:
        conn.commit()

    return written, skipped


def print_verification_table(conn):
    print(f"\n{'='*80}")
    print(f"VERIFICATION — Family C  season={SEASON}  as_of_date={AS_OF_DATE}")
    print(f"{'='*80}")
    rows = conn.execute("""
        SELECT t.team_name, s.run_metres_pg
        FROM team_style_stats s
        JOIN teams t ON s.team_id = t.team_id
        WHERE s.season=? AND s.as_of_date=?
        ORDER BY s.run_metres_pg DESC
    """, (SEASON, AS_OF_DATE)).fetchall()

    print(f"  {'Team':<40}  {'run_m':>7}")
    print(f"  {'─'*40}  {'─'*7}")
    null_count = 0
    for r in rows:
        v = r['run_metres_pg']
        if v is None:
            null_count += 1
        print(f"  {r['team_name']:<40}  {f'{v:.0f}' if v is not None else 'NULL':>7}")

    print()
    if null_count:
        print(f"  WARNING: {null_count} team(s) still have NULL run_metres_pg.")
    else:
        print(f"  All {len(rows)} teams have run_metres_pg.")


def main():
    parser = argparse.ArgumentParser(
        description='Load 2026 Family C style stats into team_style_stats'
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--settings', default='config/settings.yaml')
    parser.add_argument('--csv', default=str(CSV_PATH))
    args = parser.parse_args()

    with open(args.settings) as f:
        settings = yaml.safe_load(f)
    db_path = settings['database']['path']
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print(f"CSV   : {args.csv}")
    print(f"DB    : {db_path}")
    print(f"Target: season={SEASON}  as_of_date={AS_OF_DATE}")
    print(f"Mode  : {'DRY RUN' if args.dry_run else 'WRITE'}")
    print()

    try:
        df = load_csv(Path(args.csv))
    except FileNotFoundError:
        print(f"ERROR: CSV not found: {args.csv}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    print(f"Loaded {len(df)} rows from CSV.")

    errs = validate(df)
    if errs:
        print("\nVALIDATION ISSUES:")
        for e in errs:
            print(f"  - {e}")
        if any(df[c].isnull().all() for c in NUMERIC_COLS):
            print("\nBLOCKED: CSV has unfilled columns.")
            conn.close()
            sys.exit(1)

    print()
    print(f"{'─'*60}")
    written, skipped = write_to_db(conn, df, args.dry_run)
    print(f"{'─'*60}")
    print(f"\nDone.  Written={written}  Skipped={skipped}")

    print_verification_table(conn)
    conn.close()


if __name__ == '__main__':
    main()
