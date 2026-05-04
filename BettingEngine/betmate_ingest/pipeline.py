from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import dump_json
from .normalize import normalize_emotional, normalize_injuries, normalize_referees
from .reader import BetmateFiles, discover_files, find_round_dir, read_records
from .storage import save_import_run
from .validation import load_round_matches, validate_payload


def import_round(
    *,
    season: int,
    round_number: int,
    betmate_root: Path | None = None,
    round_dir: Path | None = None,
    out_root: Path = Path("data/import/betmate"),
    engine_import_dir: Path = Path("data/import"),
    settings: str = "config/settings.yaml",
) -> dict[str, Any]:
    if round_dir is None:
        if betmate_root is None:
            raise ValueError("Provide either --round-dir or --betmate-root.")
        round_dir = find_round_dir(betmate_root, season, round_number)

    discovered = discover_files(round_dir)
    injuries = normalize_injuries(read_records(discovered.injuries), season, round_number)
    referees = normalize_referees(read_records(discovered.referees), season, round_number)
    emotional = normalize_emotional(read_records(discovered.emotional), season, round_number)
    matches = load_round_matches(settings, season, round_number)
    filter_report: dict[str, int] = {}
    if matches:
        teams = {m["home_team"] for m in matches} | {m["away_team"] for m in matches}
        before = len(injuries)
        injuries = [item for item in injuries if item["team"] in teams]
        filter_report["injuries_dropped_non_round_team"] = before - len(injuries)
        before = len(emotional)
        emotional = [item for item in emotional if item["team"] in teams]
        filter_report["emotional_dropped_non_round_team"] = before - len(emotional)

    stage_dir = out_root / f"r{round_number}_{season}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    engine_import_dir.mkdir(parents=True, exist_ok=True)

    stage_injuries = stage_dir / "injuries.json"
    stage_referees = stage_dir / "referees.csv"
    stage_emotional = stage_dir / "emotional.json"
    engine_injuries = engine_import_dir / f"injuries_r{round_number}.json"
    engine_referees = engine_import_dir / f"referees_r{round_number}.csv"
    engine_emotional = engine_import_dir / f"emotional_r{round_number}.json"

    dump_json(stage_injuries, injuries)
    dump_json(stage_emotional, emotional)
    _write_referees(stage_referees, referees)
    dump_json(engine_injuries, injuries)
    dump_json(engine_emotional, emotional)
    _write_referees(engine_referees, referees)

    validation = validate_payload(
        season=season,
        round_number=round_number,
        matches=matches,
        injuries=injuries,
        referees=referees,
        emotional=emotional,
    )
    validation["filters"] = filter_report
    dump_json(stage_dir / "validation_report.json", validation)

    manifest = _manifest(
        season=season,
        round_number=round_number,
        discovered=discovered,
        stage_dir=stage_dir,
        engine_files={
            "injuries": engine_injuries,
            "referees": engine_referees,
            "emotional": engine_emotional,
        },
        validation=validation,
    )
    dump_json(stage_dir / "manifest.json", manifest)
    save_import_run(settings, manifest)
    return manifest


def _write_referees(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["home_team", "away_team", "referee"])
        writer.writeheader()
        writer.writerows(rows)


def _manifest(
    *,
    season: int,
    round_number: int,
    discovered: BetmateFiles,
    stage_dir: Path,
    engine_files: dict[str, Path],
    validation: dict[str, Any],
) -> dict[str, Any]:
    source_files = {
        "injuries": str(discovered.injuries) if discovered.injuries else None,
        "referees": str(discovered.referees) if discovered.referees else None,
        "emotional": str(discovered.emotional) if discovered.emotional else None,
        "other": [str(p) for p in discovered.other],
    }
    return {
        "season": season,
        "round": round_number,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "source_round_dir": str(discovered.round_dir),
        "source_files": source_files,
        "stage_dir": str(stage_dir),
        "engine_files": {k: str(v) for k, v in engine_files.items()},
        "validation": validation,
    }
