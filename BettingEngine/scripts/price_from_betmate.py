#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from betmate_ingest.common import dump_json
from betmate_ingest.freshness import run_preflight
from betmate_ingest.pipeline import import_round
from betmate_ingest.storage import save_preflight_check


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Betmate data, load engine tier inputs, then run the existing pricing flow."
    )
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--round", dest="round_number", type=int, required=True)
    parser.add_argument("--betmate-root", type=Path, default=None)
    parser.add_argument("--round-dir", type=Path, default=None)
    parser.add_argument("--settings", default="config/settings.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-weather", action="store_true")
    parser.add_argument("--strict-injuries", action="store_true")
    parser.add_argument("--no-export", action="store_true", help="Skip export_round_csv after pricing.")
    parser.add_argument("--preflight-config", default="config/betmate_automation.yaml")
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    betmate_root = args.betmate_root
    if not args.skip_preflight and betmate_root:
        cfg_path = ROOT / args.preflight_config
        cfg = yaml.safe_load(cfg_path.read_text()) if cfg_path.exists() else {}
        preflight = run_preflight(
            betmate_root=betmate_root,
            settings_path=args.settings,
            config=cfg or {},
            season=args.season,
            round_number=args.round_number,
            run_date=date.today(),
        )
        report_dir = ROOT / "logs" / "betmate"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"manual_preflight_r{args.round_number}_{args.season}.json"
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
            args.settings,
            season=args.season,
            round_number=args.round_number,
            run_date=date.today().isoformat(),
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
            raise SystemExit("Preflight failed; pricing not run. Use --skip-preflight only for deliberate overrides.")

    manifest = import_round(
        season=args.season,
        round_number=args.round_number,
        betmate_root=betmate_root,
        round_dir=args.round_dir,
        settings=args.settings,
    )

    validation = manifest["validation"]
    for warning in validation["warnings"]:
        print(f"WARNING: {warning}")
    for error in validation["errors"]:
        print(f"ERROR: {error}")
    if args.strict and validation["errors"]:
        raise SystemExit("Betmate validation failed; pricing not run.")

    emotional_path = manifest["engine_files"]["emotional"]
    injury_path = manifest["engine_files"]["injuries"]
    referee_path = manifest["engine_files"]["referees"]

    emotional_cmd = [
        sys.executable,
        "scripts/load_emotional_round.py",
        "--settings",
        args.settings,
        "--input",
        emotional_path,
    ]
    if args.dry_run:
        emotional_cmd.append("--dry-run")
    run(emotional_cmd)

    prepare_cmd = [
        sys.executable,
        "scripts/prepare_round.py",
        "--settings",
        args.settings,
        "--season",
        str(args.season),
        "--round",
        str(args.round_number),
        "--injury-json",
        injury_path,
        "--referee-csv",
        referee_path,
    ]
    if args.dry_run:
        prepare_cmd.append("--dry-run")
    if args.skip_weather:
        prepare_cmd.append("--skip-weather")
    if args.strict_injuries:
        prepare_cmd.append("--strict-injuries")
    run(prepare_cmd)

    if not args.no_export and not args.dry_run:
        run(
            [
                sys.executable,
                "scripts/export_round_csv.py",
                "--season",
                str(args.season),
                "--round",
                str(args.round_number),
            ]
        )

    print(f"Betmate-priced round complete. Manifest: {manifest['stage_dir']}/manifest.json")


def run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
