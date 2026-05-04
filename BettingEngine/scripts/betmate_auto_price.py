#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from betmate_ingest.common import dump_json
from betmate_ingest.freshness import run_preflight
from betmate_ingest.storage import save_preflight_check


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Scheduled Betmate import + existing pricing runner.")
    parser.add_argument("--config", default="config/betmate_automation.yaml")
    parser.add_argument("--date", default=None, help="Override run date for testing, YYYY-MM-DD.")
    parser.add_argument("--round", dest="round_number", type=int, default=None, help="Override auto round.")
    parser.add_argument("--season", type=int, default=None, help="Override config season.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    cfg = yaml.safe_load((ROOT / args.config).read_text()) or {}
    pricing_cfg = cfg.get("pricing", {})
    automation_cfg = cfg.get("automation", {})
    betmate_cfg = cfg.get("betmate", {})

    season = args.season or int(pricing_cfg.get("season", 2026))
    settings_path = pricing_cfg.get("settings", "config/settings.yaml")
    run_date = date.fromisoformat(args.date) if args.date else date.today()
    round_number = args.round_number or infer_round(settings_path, season, run_date)

    betmate_root = os.environ.get("BETMATE_ROOT") or betmate_cfg.get("root") or ""
    if not betmate_root:
        raise SystemExit(
            "Betmate root is not configured. Set betmate.root in config/betmate_automation.yaml "
            "or export BETMATE_ROOT."
        )

    log_dir = ROOT / automation_cfg.get("log_dir", "logs/betmate")
    log_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_preflight:
        preflight = run_preflight(
            betmate_root=Path(betmate_root),
            settings_path=settings_path,
            config=cfg,
            season=season,
            round_number=round_number,
            run_date=run_date,
        )
        report_path = log_dir / f"preflight_r{round_number}_{season}.json"
        dump_json(
            report_path,
            {
                "ok": preflight.ok,
                "errors": preflight.errors,
                "warnings": preflight.warnings,
                "details": preflight.details,
            },
        )
        save_preflight_check(
            settings_path,
            season=season,
            round_number=round_number,
            run_date=run_date.isoformat(),
            ok=preflight.ok,
            errors=preflight.errors,
            warnings=preflight.warnings,
            details=preflight.details,
        )
        for warning in preflight.warnings:
            print(f"WARNING: {warning}")
        for error in preflight.errors:
            print(f"ERROR: {error}")
        print(f"Preflight report: {report_path}")
        if not preflight.ok:
            raise SystemExit("Preflight failed; pricing not run.")

    cmd = [
        sys.executable,
        "scripts/price_from_betmate.py",
        "--season",
        str(season),
        "--round",
        str(round_number),
        "--betmate-root",
        betmate_root,
        "--settings",
        settings_path,
    ]
    if pricing_cfg.get("skip_weather", True):
        cmd.append("--skip-weather")
    if pricing_cfg.get("strict", True):
        cmd.append("--strict")
    if pricing_cfg.get("strict_injuries", False):
        cmd.append("--strict-injuries")
    if pricing_cfg.get("no_export", False):
        cmd.append("--no-export")
    if args.dry_run:
        cmd.append("--dry-run")
    cmd.append("--skip-preflight")

    print(f"Betmate auto-price date={run_date.isoformat()} season={season} round={round_number}")
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def infer_round(settings_path: str, season: int, run_date: date) -> int:
    settings = yaml.safe_load((ROOT / settings_path).read_text())
    db_path = ROOT / settings["database"]["path"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT round_number, MIN(match_date) AS first_date, MAX(match_date) AS last_date
        FROM matches
        WHERE season=?
        GROUP BY round_number
        HAVING DATE(last_date) >= DATE(?)
        ORDER BY DATE(first_date), round_number
        LIMIT 1
        """,
        (season, run_date.isoformat()),
    ).fetchone()
    conn.close()
    if not row:
        raise SystemExit(f"No current/future round found for season={season} date={run_date.isoformat()}.")
    return int(row["round_number"])


if __name__ == "__main__":
    main()
