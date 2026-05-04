#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from betmate_ingest.pipeline import import_round


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Betmate round outputs into engine-ready tier files.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--round", dest="round_number", type=int, required=True)
    parser.add_argument("--betmate-root", type=Path, default=None, help="Root folder containing Betmate round exports.")
    parser.add_argument("--round-dir", type=Path, default=None, help="Exact Betmate round export folder.")
    parser.add_argument("--out-root", type=Path, default=Path("data/import/betmate"))
    parser.add_argument("--engine-import-dir", type=Path, default=Path("data/import"))
    parser.add_argument("--settings", default="config/settings.yaml")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if validation has errors.")
    args = parser.parse_args()

    manifest = import_round(
        season=args.season,
        round_number=args.round_number,
        betmate_root=args.betmate_root,
        round_dir=args.round_dir,
        out_root=args.out_root,
        engine_import_dir=args.engine_import_dir,
        settings=args.settings,
    )

    validation = manifest["validation"]
    print(f"Betmate import complete: season={args.season} round={args.round_number}")
    print(f"Stage: {manifest['stage_dir']}")
    print("Engine files:")
    for key, path in manifest["engine_files"].items():
        print(f"  {key}: {path}")
    print(f"Counts: {validation['counts']}")
    for warning in validation["warnings"]:
        print(f"WARNING: {warning}")
    for error in validation["errors"]:
        print(f"ERROR: {error}")

    if args.strict and validation["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

