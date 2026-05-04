from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FreshnessResult:
    ok: bool
    errors: list[str]
    warnings: list[str]
    details: dict[str, Any]


DATASETS = {
    "injuries-suspensions": Path("injuries-suspensions/latest/manifest.json"),
    "referees": Path("referees/latest/manifest.json"),
    "emotional-flags": Path("emotional-flags/latest/manifest.json"),
    "historical-odds": Path("historical-odds/latest/manifest.json"),
}


def run_preflight(
    *,
    betmate_root: Path,
    settings_path: str,
    config: dict[str, Any],
    season: int,
    round_number: int,
    run_date: date | None = None,
) -> FreshnessResult:
    run_date = run_date or date.today()
    now = datetime.now(timezone.utc)
    freshness_cfg = config.get("freshness", {})
    max_age_hours = freshness_cfg.get("max_age_hours", {})
    require_target_round = freshness_cfg.get("require_target_round", {})

    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {"betmate": {}, "engine": {}}

    for dataset, rel_path in DATASETS.items():
        manifest_path = betmate_root / rel_path
        if not manifest_path.exists():
            errors.append(f"Betmate {dataset} manifest missing: {manifest_path}")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        stamp = _manifest_timestamp(manifest)
        dataset_detail: dict[str, Any] = {
            "manifest": str(manifest_path),
            "timestamp": stamp.isoformat() if stamp else None,
            "round": manifest.get("round"),
            "row_count": manifest.get("row_count") or manifest.get("assignment_count"),
        }
        if stamp is None:
            warnings.append(f"Betmate {dataset} has no parseable timestamp in manifest.")
        else:
            age_hours = (now - stamp).total_seconds() / 3600
            dataset_detail["age_hours"] = round(age_hours, 2)
            allowed = max_age_hours.get(dataset)
            if allowed is not None and age_hours > float(allowed):
                errors.append(
                    f"Betmate {dataset} is stale: {age_hours:.1f}h old, max allowed {float(allowed):.1f}h."
                )
        if require_target_round.get(dataset) and manifest.get("round") is not None:
            if int(manifest["round"]) != int(round_number):
                errors.append(
                    f"Betmate {dataset} is for round {manifest['round']}, target engine round is {round_number}."
                )
        count = dataset_detail.get("row_count")
        if count is not None and int(count) == 0:
            errors.append(f"Betmate {dataset} has zero rows.")
        details["betmate"][dataset] = dataset_detail

    engine = _engine_preflight(settings_path, season, round_number, run_date, freshness_cfg)
    details["engine"] = engine["details"]
    errors.extend(engine["errors"])
    warnings.extend(engine["warnings"])

    return FreshnessResult(ok=not errors, errors=errors, warnings=warnings, details=details)


def _manifest_timestamp(manifest: dict[str, Any]) -> datetime | None:
    for key in ("scraped_at", "downloaded_at", "imported_at", "created_at", "as_of_date"):
        value = manifest.get(key)
        if not value:
            continue
        parsed = _parse_datetime(str(value))
        if parsed:
            return parsed
    return None


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text[:10]).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _engine_preflight(
    settings_path: str,
    season: int,
    round_number: int,
    run_date: date,
    freshness_cfg: dict[str, Any],
) -> dict[str, Any]:
    settings = yaml.safe_load(open(settings_path))
    db_path = settings["database"]["path"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    target = conn.execute(
        """
        SELECT MIN(match_date) first_date, MAX(match_date) last_date, COUNT(*) games
        FROM matches
        WHERE season=? AND round_number=?
        """,
        (season, round_number),
    ).fetchone()
    details["target_round"] = dict(target) if target else {}
    if not target or not target["games"]:
        errors.append(f"No engine fixtures found for season={season} round={round_number}.")
        conn.close()
        return {"errors": errors, "warnings": warnings, "details": details}

    prev_round = round_number - 1
    if prev_round >= 1 and freshness_cfg.get("require_previous_round_results", True):
        prev = conn.execute(
            """
            SELECT COUNT(*) games,
                   SUM(CASE WHEN r.result_status='final' THEN 1 ELSE 0 END) final_games,
                   MAX(m.match_date) last_date
            FROM matches m
            LEFT JOIN results r ON r.match_id=m.match_id
            WHERE m.season=? AND m.round_number=?
            """,
            (season, prev_round),
        ).fetchone()
        details["previous_round_results"] = dict(prev) if prev else {}
        if not prev or not prev["games"]:
            errors.append(f"No previous round fixtures found for R{prev_round}; T1/ELO cannot be checked.")
        elif int(prev["final_games"] or 0) != int(prev["games"]):
            errors.append(
                f"Previous round R{prev_round} results incomplete: {prev['final_games']}/{prev['games']} final."
            )

    first_date = date.fromisoformat(target["first_date"])
    expected_as_of = first_date.fromordinal(first_date.toordinal() - 1).isoformat()

    if freshness_cfg.get("require_team_stats_current", True):
        stat = conn.execute(
            """
            SELECT COUNT(DISTINCT team_id) teams, MAX(as_of_date) max_as_of
            FROM team_stats
            WHERE season=? AND as_of_date=?
            """,
            (season, expected_as_of),
        ).fetchone()
        details["team_stats"] = {"expected_as_of": expected_as_of, **(dict(stat) if stat else {})}
        if not stat or int(stat["teams"] or 0) < 16:
            errors.append(
                f"Team stats are not current for target round: expected as_of_date={expected_as_of}, "
                f"found {0 if not stat else stat['teams']} teams."
            )

    if freshness_cfg.get("require_elo_current", True):
        elo = conn.execute(
            """
            SELECT COUNT(DISTINCT team_id) teams
            FROM team_stats
            WHERE season=? AND as_of_date=? AND elo_rating IS NOT NULL
            """,
            (season, expected_as_of),
        ).fetchone()
        details["elo"] = {"expected_as_of": expected_as_of, **(dict(elo) if elo else {})}
        if not elo or int(elo["teams"] or 0) < 16:
            errors.append(
                f"ELO ratings are not current for target round: expected team_stats.elo_rating "
                f"as_of_date={expected_as_of}, found {0 if not elo else elo['teams']} teams."
            )

    conn.close()
    return {"errors": errors, "warnings": warnings, "details": details}

