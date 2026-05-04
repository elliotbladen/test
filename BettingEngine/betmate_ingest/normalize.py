from __future__ import annotations

from typing import Any

from .common import (
    VALID_ABSENCE_TYPES,
    VALID_FLAG_TYPES,
    VALID_ROLES,
    VALID_STATUSES,
    VALID_STRENGTHS,
    VALID_TIERS,
    canonical_team,
    first_value,
)


ROLE_MAP = {
    "fb": "fullback",
    "full back": "fullback",
    "fullback": "fullback",
    "hb": "halfback",
    "half": "halfback",
    "halfback": "halfback",
    "five eighth": "five_eighth",
    "five-eighth": "five_eighth",
    "5/8": "five_eighth",
    "hooker": "hooker",
    "prop": "pack",
    "second row": "pack",
    "lock": "pack",
    "forward": "pack",
    "middle": "pack",
    "edge": "pack",
    "pack": "pack",
}

TIER_MAP = {
    "star": "elite",
    "elite": "elite",
    "high": "elite",
    "key": "key",
    "starter": "key",
    "starting": "key",
    "medium": "key",
    "rotation": "rotation",
    "bench": "rotation",
    "low": "rotation",
    "depth": "rotation",
}

STATUS_MAP = {
    "out": "out",
    "injured": "out",
    "suspended": "out",
    "unavailable": "out",
    "doubtful": "doubtful",
    "questionable": "doubtful",
    "managed": "managed",
    "rested": "managed",
    "available": "available",
}

FLAG_MAP = {
    "milestone": "milestone",
    "debut": "milestone",
    "new coach": "new_coach",
    "new_coach": "new_coach",
    "coach": "new_coach",
    "star return": "star_return",
    "star_return": "star_return",
    "return": "star_return",
    "shame blowout": "shame_blowout",
    "shame_blowout": "shame_blowout",
    "blowout": "shame_blowout",
    "origin": "origin_boost",
    "origin boost": "origin_boost",
    "farewell": "farewell",
    "personal tragedy": "personal_tragedy",
    "tragedy": "personal_tragedy",
    "rivalry": "rivalry_derby",
    "derby": "rivalry_derby",
    "must win": "must_win",
    "must_win": "must_win",
}


def normalize_injuries(rows: list[dict[str, Any]], season: int, round_number: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        team = canonical_team(first_value(row, "team", "club", "squad"))
        player = str(first_value(row, "player", "player_name", "name")).strip()
        if not team or not player:
            continue

        role = _map_value(first_value(row, "role", "position", "player_role"), ROLE_MAP, "other")
        tier = _map_value(first_value(row, "importance_tier", "tier", "importance", "quality", "severity"), TIER_MAP, "rotation")
        status = _map_value(first_value(row, "status", "availability"), STATUS_MAP, "out")
        absence_type = str(first_value(row, "absence_type", "type", "category", default="")).strip().lower()
        notes = str(first_value(row, "notes", "note", "details", "reason", "injury", default="")).strip()

        if not absence_type:
            raw = f"{notes} {first_value(row, 'status', 'type', 'category', default='')}".lower()
            absence_type = "suspension" if "suspend" in raw or "ban" in raw else "injury"

        if role not in VALID_ROLES:
            role = "other"
        if tier not in VALID_TIERS:
            tier = "rotation"
        if status not in VALID_STATUSES:
            status = "out"
        if absence_type not in VALID_ABSENCE_TYPES:
            absence_type = "injury"

        items.append(
            {
                "season": season,
                "round": round_number,
                "team": team,
                "player": player,
                "role": role,
                "importance_tier": tier,
                "status": status,
                "absence_type": absence_type,
                "notes": notes,
                "source_url": str(first_value(row, "source_url", "url", "source", default="")).strip() or None,
            }
        )
    return _dedupe(items, ("season", "round", "team", "player"))


def normalize_referees(rows: list[dict[str, Any]], season: int, round_number: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        home = canonical_team(first_value(row, "home_team", "home", "homeTeam"))
        away = canonical_team(first_value(row, "away_team", "away", "awayTeam"))
        referee = str(first_value(row, "referee", "ref", "official", "match_official")).strip()
        if not home or not away or not referee:
            continue
        items.append({"home_team": home, "away_team": away, "referee": referee})
    return _dedupe(items, ("home_team", "away_team"))


def normalize_emotional(rows: list[dict[str, Any]], season: int, round_number: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        team = canonical_team(first_value(row, "team", "club", "squad"))
        raw_flag = str(first_value(row, "flag_type", "flag", "type", "category", "factor")).strip().lower()
        flag_type = FLAG_MAP.get(raw_flag, raw_flag.replace(" ", "_").replace("-", "_"))
        if not team or not flag_type:
            continue
        if flag_type not in VALID_FLAG_TYPES:
            continue
        strength = str(first_value(row, "flag_strength", "strength", "severity", default="normal")).strip().lower()
        if strength not in VALID_STRENGTHS:
            strength = "normal"
        player = first_value(row, "player_name", "player", "name", default=None)
        player_name = str(player).strip() if player is not None and str(player).strip() else None
        notes = str(first_value(row, "notes", "note", "details", "description", default="")).strip()
        items.append(
            {
                "season": season,
                "round": round_number,
                "team": team,
                "flag_type": flag_type,
                "flag_strength": strength,
                "player_name": player_name,
                "notes": notes,
                "source_url": str(first_value(row, "source_url", "url", "source", default="")).strip() or None,
            }
        )
    return _dedupe(items, ("season", "round", "team", "flag_type", "player_name"))


def _map_value(value: Any, mapping: dict[str, str], default: str) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    return mapping.get(text, default)


def _dedupe(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        seen[tuple(item.get(k) for k in keys)] = item
    return list(seen.values())
