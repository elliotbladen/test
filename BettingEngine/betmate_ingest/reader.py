from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import clean_key, load_json


SUPPORTED_SUFFIXES = {".json", ".csv", ".xlsx", ".xls"}


@dataclass(frozen=True)
class BetmateFiles:
    round_dir: Path
    injuries: Path | None
    referees: Path | None
    emotional: Path | None
    other: tuple[Path, ...] = ()


def find_round_dir(root: Path, season: int, round_number: int) -> Path:
    if not root.exists():
        raise FileNotFoundError(f"Betmate root does not exist: {root}")
    if root.is_file():
        raise NotADirectoryError(f"Betmate root must be a directory: {root}")

    patterns = [
        f"r{round_number}_{season}",
        f"round_{round_number}_{season}",
        f"round-{round_number}-{season}",
        f"{season}_r{round_number}",
        f"{season}_round_{round_number}",
        f"r{round_number}",
        f"round_{round_number}",
        f"round-{round_number}",
    ]
    lowered_patterns = [p.lower() for p in patterns]

    candidates: list[Path] = []
    for path in [root, *[p for p in root.rglob("*") if p.is_dir()]]:
        name = path.name.lower().replace(" ", "_")
        if any(pattern in name for pattern in lowered_patterns):
            candidates.append(path)

    if not candidates:
        return root

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def discover_files(round_dir: Path) -> BetmateFiles:
    files = [p for p in round_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES]

    def score(path: Path, include: tuple[str, ...], exclude: tuple[str, ...] = ()) -> int:
        text = clean_key(path.stem)
        if any(word in text for word in exclude):
            return -100
        return sum(5 for word in include if word in text)

    injuries = _best(files, ("injury", "injuries", "suspension", "suspensions", "absence", "absences"))
    referees = _best(files, ("referee", "referees", "official", "officials", "match_official"))
    emotional = _best(files, ("emotional", "emotion", "context", "human", "milestone", "narrative"))
    selected = {p for p in (injuries, referees, emotional) if p}
    other = tuple(p for p in files if p not in selected)
    return BetmateFiles(round_dir=round_dir, injuries=injuries, referees=referees, emotional=emotional, other=other)


def _best(files: list[Path], keywords: tuple[str, ...]) -> Path | None:
    scored: list[tuple[int, float, Path]] = []
    for path in files:
        text = clean_key(path.stem)
        points = sum(1 for keyword in keywords if keyword in text)
        if points:
            scored.append((points, path.stat().st_mtime, path))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][2]


def read_records(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = load_json(path)
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            for key in ("records", "items", "data", "injuries", "referees", "assignments", "emotional", "flags"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [r for r in value if isinstance(r, dict)]
        raise ValueError(f"JSON file must contain an array or known record array: {path}")
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as fh:
            return list(csv.DictReader(fh))
    if suffix in {".xlsx", ".xls"}:
        return _read_excel_records(path)
    raise ValueError(f"Unsupported Betmate file type: {path}")


def _read_excel_records(path: Path) -> list[dict[str, Any]]:
    import pandas as pd

    frames = pd.read_excel(path, sheet_name=None)
    records: list[dict[str, Any]] = []
    for _, frame in frames.items():
        frame = frame.dropna(how="all")
        if frame.empty:
            continue
        frame.columns = [str(c).strip() for c in frame.columns]
        records.extend(frame.fillna("").to_dict(orient="records"))
    return records
