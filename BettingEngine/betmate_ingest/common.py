from __future__ import annotations

import json
from pathlib import Path
from typing import Any


NAME_MAP = {
    "Canterbury Bulldogs": "Canterbury-Bankstown Bulldogs",
    "Cronulla Sharks": "Cronulla-Sutherland Sharks",
    "Cronulla Sutherland Sharks": "Cronulla-Sutherland Sharks",
    "Manly Sea Eagles": "Manly-Warringah Sea Eagles",
    "Manly Warringah Sea Eagles": "Manly-Warringah Sea Eagles",
    "North QLD Cowboys": "North Queensland Cowboys",
    "St George Dragons": "St. George Illawarra Dragons",
    "St George Illawarra Dragons": "St. George Illawarra Dragons",
    "Broncos": "Brisbane Broncos",
    "Bulldogs": "Canterbury-Bankstown Bulldogs",
    "Cowboys": "North Queensland Cowboys",
    "Dolphins": "Dolphins",
    "Dragons": "St. George Illawarra Dragons",
    "Eels": "Parramatta Eels",
    "Knights": "Newcastle Knights",
    "Panthers": "Penrith Panthers",
    "Rabbitohs": "South Sydney Rabbitohs",
    "Raiders": "Canberra Raiders",
    "Roosters": "Sydney Roosters",
    "Sea Eagles": "Manly-Warringah Sea Eagles",
    "Sharks": "Cronulla-Sutherland Sharks",
    "Storm": "Melbourne Storm",
    "Titans": "Gold Coast Titans",
    "Warriors": "New Zealand Warriors",
    "Wests Tigers": "Wests Tigers",
}

VALID_ROLES = {"fullback", "halfback", "five_eighth", "hooker", "pack", "other"}
VALID_TIERS = {"elite", "key", "rotation"}
VALID_STATUSES = {"out", "doubtful", "managed", "available"}
VALID_ABSENCE_TYPES = {"injury", "suspension"}
VALID_FLAG_TYPES = {
    "milestone",
    "new_coach",
    "star_return",
    "shame_blowout",
    "origin_boost",
    "farewell",
    "personal_tragedy",
    "rivalry_derby",
    "must_win",
}
VALID_STRENGTHS = {"minor", "normal", "major"}


def canonical_team(name: Any) -> str:
    text = str(name or "").strip()
    return NAME_MAP.get(text, text)


def clean_key(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value)).strip("_")


def first_value(row: dict[str, Any], *keys: str, default: Any = "") -> Any:
    normalized = {clean_key(k): v for k, v in row.items()}
    for key in keys:
        value = normalized.get(clean_key(key))
        if value is not None and str(value).strip() != "":
            return value
    return default


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
