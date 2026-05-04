from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def connect(settings_path: str) -> sqlite3.Connection:
    settings = yaml.safe_load(open(settings_path))
    conn = sqlite3.connect(settings["database"]["path"])
    conn.row_factory = sqlite3.Row
    return conn


def save_import_run(settings_path: str, manifest: dict[str, Any]) -> None:
    conn = connect(settings_path)
    try:
        validation = manifest.get("validation", {})
        counts = validation.get("counts", {})
        conn.execute(
            """
            INSERT INTO betmate_import_runs (
                season, round_number, source_round_dir, stage_dir, imported_at, status,
                injuries_count, referees_count, emotional_count, manifest_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manifest["season"],
                manifest["round"],
                manifest.get("source_round_dir"),
                manifest.get("stage_dir"),
                manifest.get("imported_at"),
                validation.get("status", "unknown"),
                int(counts.get("injuries", 0)),
                int(counts.get("referees", 0)),
                int(counts.get("emotional", 0)),
                json.dumps(manifest, sort_keys=True),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_preflight_check(
    settings_path: str,
    *,
    season: int,
    round_number: int,
    run_date: str,
    ok: bool,
    errors: list[str],
    warnings: list[str],
    details: dict[str, Any],
) -> None:
    conn = connect(settings_path)
    try:
        conn.execute(
            """
            INSERT INTO betmate_preflight_checks (
                season, round_number, run_date, checked_at, ok,
                errors_json, warnings_json, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                season,
                round_number,
                run_date,
                datetime.now(timezone.utc).isoformat(),
                int(ok),
                json.dumps(errors, sort_keys=True),
                json.dumps(warnings, sort_keys=True),
                json.dumps(details, sort_keys=True),
            ),
        )
        conn.commit()
    finally:
        conn.close()

