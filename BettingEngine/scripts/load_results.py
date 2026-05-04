#!/usr/bin/env python3
"""
scripts/load_results.py

Load match results from a CSV into the results table.

CSV format (one row per match):
  match_id,home_team,away_team,home_score,away_score,match_date

Usage:
  python scripts/load_results.py data/import/r10_results_2026.csv
  python scripts/load_results.py data/import/r10_results_2026.csv --dry-run
"""

import argparse
import csv
import sqlite3
import sys
import yaml
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    p = argparse.ArgumentParser(description="Load match results into DB from CSV")
    p.add_argument("csv_file", help="Path to results CSV")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--settings", default="config/settings.yaml")
    args = p.parse_args()

    settings = yaml.safe_load(open(args.settings))
    conn = sqlite3.connect(settings["database"]["path"])
    conn.row_factory = sqlite3.Row

    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"ERROR: file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    now = datetime.utcnow().isoformat()
    written = errors = 0

    print(f"\n  {'ID':>4}  {'Home':<42}  {'Away':<42}  {'Score':>7}  Result")
    print(f"  {'─'*4}  {'─'*42}  {'─'*42}  {'─'*7}  {'─'*8}")

    for row in rows:
        mid = row.get("match_id", "").strip()
        home_score_raw = row.get("home_score", "").strip()
        away_score_raw = row.get("away_score", "").strip()
        home = row.get("home_team", "").strip()
        away = row.get("away_team", "").strip()

        if not mid or not home_score_raw or not away_score_raw:
            print(f"  {'?':>4}  {home:<42}  {away:<42}  {'SKIP':>7}  missing data")
            errors += 1
            continue

        try:
            match_id = int(mid)
            hs = int(home_score_raw)
            aws = int(away_score_raw)
        except ValueError:
            print(f"  {mid:>4}  {home:<42}  {away:<42}  {'ERR':>7}  invalid numbers")
            errors += 1
            continue

        match_row = conn.execute(
            "SELECT match_id FROM matches WHERE match_id=?", (match_id,)
        ).fetchone()
        if not match_row:
            print(f"  {match_id:>4}  {home:<42}  {away:<42}  {hs}-{aws:>3}  MATCH NOT FOUND")
            errors += 1
            continue

        score = f"{hs}-{aws}"
        if not args.dry_run:
            conn.execute(
                """
                INSERT INTO results (match_id, home_score, away_score, result_status, source, captured_at)
                VALUES (?,?,?,'final','manual',?)
                ON CONFLICT(match_id) DO UPDATE SET
                    home_score    = excluded.home_score,
                    away_score    = excluded.away_score,
                    result_status = excluded.result_status,
                    source        = excluded.source,
                    captured_at   = excluded.captured_at
                """,
                (match_id, hs, aws, now),
            )
            action = "WRITTEN"
        else:
            action = "DRY-RUN"

        print(f"  {match_id:>4}  {home:<42}  {away:<42}  {score:>7}  {action}")
        written += 1

    if not args.dry_run and written:
        conn.commit()

    print(f"\n  {written} results {'staged' if args.dry_run else 'written'}, {errors} errors.")
    conn.close()


if __name__ == "__main__":
    main()
