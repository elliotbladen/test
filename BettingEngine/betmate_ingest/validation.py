from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import yaml


def load_round_matches(settings_path: str, season: int, round_number: int) -> list[dict[str, Any]]:
    settings = yaml.safe_load(open(settings_path))
    db_path = settings["database"]["path"]
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT h.team_name AS home_team, a.team_name AS away_team
        FROM matches m
        JOIN teams h ON h.team_id = m.home_team_id
        JOIN teams a ON a.team_id = m.away_team_id
        WHERE m.season=? AND m.round_number=?
        ORDER BY m.match_date, m.match_id
        """,
        (season, round_number),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def validate_payload(
    *,
    season: int,
    round_number: int,
    matches: list[dict[str, Any]],
    injuries: list[dict[str, Any]],
    referees: list[dict[str, Any]],
    emotional: list[dict[str, Any]],
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    teams = {m["home_team"] for m in matches} | {m["away_team"] for m in matches}
    matchups = {(m["home_team"], m["away_team"]) for m in matches}

    if not matches:
        warnings.append("No engine fixtures found for this season/round; DB fixture validation skipped.")

    for item in injuries:
        if int(item.get("season", season)) != season or int(item.get("round", round_number)) != round_number:
            errors.append(f"Injury record has wrong season/round: {item['team']} ({item['player']})")
        if teams and item["team"] not in teams:
            errors.append(f"Injury team is not in this round: {item['team']} ({item['player']})")

    for item in emotional:
        if int(item.get("season", season)) != season or int(item.get("round", round_number)) != round_number:
            errors.append(f"Emotional record has wrong season/round: {item['team']} ({item['flag_type']})")
        if teams and item["team"] not in teams:
            errors.append(f"Emotional team is not in this round: {item['team']} ({item['flag_type']})")

    for item in referees:
        matchup = (item["home_team"], item["away_team"])
        if matchups and matchup not in matchups:
            errors.append(f"Referee matchup is not in this round: {item['home_team']} v {item['away_team']}")

    if matches and len(referees) < len(matches):
        warnings.append(f"Referee file has {len(referees)} assignments for {len(matches)} fixtures.")

    return {
        "status": "error" if errors else "ok",
        "counts": {
            "matches": len(matches),
            "injuries": len(injuries),
            "referees": len(referees),
            "emotional": len(emotional),
        },
        "errors": errors,
        "warnings": warnings,
    }
