#!/usr/bin/env python3
"""
scripts/load_yardage_stats_2023.py

Load Tier 2 yardage-bucket stats into team_stats for season 2023.

Reads:  data/import/team_yardage_stats_2023.csv
Writes: team_stats.run_metres_pg, completion_rate, errors_pg,
        penalties_pg, kick_metres_pg
        WHERE season=2023 AND as_of_date='2023-08-30'

IMPORTANT — completion_rate format:
    Store as a decimal fraction: 0.78 = 78%.
    If your source shows "78", divide by 100 before entering the CSV.
    The loader will auto-detect and convert values > 1.0.

USAGE
-----
    cd /path/to/Betting_model
    python scripts/load_yardage_stats_2023.py [--dry-run]
"""

import argparse
import sqlite3
import sys
import yaml
import pandas as pd
from pathlib import Path

CSV_PATH    = Path('data/import/team_yardage_stats_2023.csv')
SEASON      = 2023
AS_OF_DATE  = '2023-08-30'

NUMERIC_COLS = [
    'run_metres_pg',
    'completion_rate',
    'errors_pg',
    'penalties_pg',
    'kick_metres_pg',
]


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(str(path))
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def validate(df: pd.DataFrame) -> list:
    errors = []
    required = ['team_id', 'season', 'as_of_date'] + NUMERIC_COLS
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        errors.append(f"Missing columns: {missing_cols}")
        return errors   # can't continue without columns

    if len(df) != 17:
        errors.append(f"Expected 17 rows (one per team), got {len(df)}")

    blank_cols = []
    for col in NUMERIC_COLS:
        if df[col].isnull().all():
            blank_cols.append(col)
    if blank_cols:
        errors.append(f"All-null columns (not yet filled in): {blank_cols}")

    for col in NUMERIC_COLS:
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        non_numeric = non_null[pd.to_numeric(non_null, errors='coerce').isnull()]
        if len(non_numeric):
            errors.append(f"Non-numeric values in '{col}': {list(non_numeric)}")

    return errors


def fix_completion_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Auto-convert completion_rate > 1.0 from percentage to decimal."""
    col = 'completion_rate'
    if col not in df.columns:
        return df
    mask = df[col].notna() & (pd.to_numeric(df[col], errors='coerce') > 1.0)
    if mask.any():
        count = mask.sum()
        print(f"  AUTO-CONVERT: {count} completion_rate value(s) > 1.0 "
              f"detected — dividing by 100 (percentage → decimal)")
        df = df.copy()
        df.loc[mask, col] = pd.to_numeric(df.loc[mask, col], errors='coerce') / 100.0
    return df


def write_to_db(conn, df: pd.DataFrame, dry_run: bool) -> tuple:
    written = skipped = errors = 0
    for _, row in df.iterrows():
        team_id = int(row['team_id'])

        stat_row = conn.execute(
            "SELECT team_stat_id FROM team_stats WHERE team_id=? AND season=? AND as_of_date=?",
            (team_id, SEASON, AS_OF_DATE),
        ).fetchone()

        if stat_row is None:
            print(f"  WARNING: no team_stats row for team_id={team_id} "
                  f"season={SEASON} as_of_date={AS_OF_DATE} — skipping")
            skipped += 1
            continue

        updates = {}
        for col in NUMERIC_COLS:
            val = row.get(col)
            if pd.notna(val):
                try:
                    updates[col] = float(val)
                except (ValueError, TypeError):
                    print(f"  WARNING: cannot convert {col}={val!r} to float — skipping field")

        if not updates:
            print(f"  SKIP team_id={team_id}: no numeric values to write")
            skipped += 1
            continue

        set_clause = ', '.join(f"{col}=?" for col in updates)
        vals = list(updates.values()) + [stat_row[0]]

        if not dry_run:
            conn.execute(
                f"UPDATE team_stats SET {set_clause} WHERE team_stat_id=?",
                vals,
            )

        marker = "(dry-run)" if dry_run else "written"
        team_name = row.get('team_name', f'id={team_id}')
        run_m = updates.get('run_metres_pg', '—')
        cr    = updates.get('completion_rate', '—')
        err   = updates.get('errors_pg', '—')
        pen   = updates.get('penalties_pg', '—')
        km    = updates.get('kick_metres_pg', '—')
        print(f"  {team_name:<40} "
              f"run_m={run_m}  cr={cr}  err={err}  pen={pen}  km={km}  {marker}")
        written += 1

    if not dry_run:
        conn.commit()

    return written, skipped, errors


def print_verification_table(conn):
    print(f"\n{'='*100}")
    print(f"VERIFICATION — team_stats season={SEASON} as_of_date={AS_OF_DATE}")
    print(f"{'='*100}")
    rows = conn.execute("""
        SELECT t.team_name, ts.run_metres_pg, ts.completion_rate,
               ts.errors_pg, ts.penalties_pg, ts.kick_metres_pg
        FROM team_stats ts
        JOIN teams t ON ts.team_id=t.team_id
        WHERE ts.season=? AND ts.as_of_date=?
        ORDER BY t.team_name
    """, (SEASON, AS_OF_DATE)).fetchall()

    print(f"  {'Team':<40}  {'run_m':>7}  {'cr':>6}  {'err':>6}  {'pen':>6}  {'km':>7}")
    print(f"  {'─'*40}  {'─'*7}  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*7}")

    null_count = 0
    for r in rows:
        def fmt(v): return f"{v:.1f}" if v is not None else "NULL"
        if any(r[col] is None for col in ['run_metres_pg','completion_rate','errors_pg','penalties_pg','kick_metres_pg']):
            null_count += 1
        print(f"  {r['team_name']:<40}  "
              f"{fmt(r['run_metres_pg']):>7}  "
              f"{fmt(r['completion_rate']):>6}  "
              f"{fmt(r['errors_pg']):>6}  "
              f"{fmt(r['penalties_pg']):>6}  "
              f"{fmt(r['kick_metres_pg']):>7}")

    print()
    if null_count:
        print(f"  WARNING: {null_count} team(s) still have NULL values in yardage fields.")
    else:
        print(f"  All 17 teams have values in all 5 yardage fields.")


def main():
    parser = argparse.ArgumentParser(description='Load 2023 yardage stats into team_stats')
    parser.add_argument('--dry-run', action='store_true',
                        help='Validate and print without writing to DB')
    parser.add_argument('--settings', default='config/settings.yaml')
    parser.add_argument('--csv', default=str(CSV_PATH),
                        help=f'Path to yardage CSV (default: {CSV_PATH})')
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

    # Load CSV
    try:
        df = load_csv(Path(args.csv))
    except FileNotFoundError:
        print(f"ERROR: CSV not found: {args.csv}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    print(f"Loaded {len(df)} rows from CSV.")

    # Validate
    errs = validate(df)
    if errs:
        print()
        print("VALIDATION ISSUES:")
        for e in errs:
            print(f"  - {e}")
        # All-null is a blocking error
        null_fields = [c for c in NUMERIC_COLS if df[c].isnull().all()]
        if null_fields:
            print()
            print("BLOCKED: CSV has not been filled in yet.")
            print(f"  Please populate {CSV_PATH} with 2023 season averages and re-run.")
            conn.close()
            sys.exit(1)

    # Auto-fix completion_rate format
    df = fix_completion_rate(df)

    # Write
    print()
    print(f"{'─'*80}")
    written, skipped, err_count = write_to_db(conn, df, args.dry_run)
    print(f"{'─'*80}")
    print(f"\nDone.  Written={written}  Skipped={skipped}  Errors={err_count}")

    # Verification table (always show, even dry-run)
    print_verification_table(conn)
    conn.close()


if __name__ == '__main__':
    main()
