#!/usr/bin/env python3
"""Capture AFL bookmaker market snapshots from an AFL odds workbook."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.queries import get_or_create_match, get_or_create_team, get_or_create_venue  # noqa: E402
from ingestion.market_snapshots import ingest_snapshots_bulk  # noqa: E402


AFL_ALIASES = {
    "Adelaide": "Adelaide Crows",
    "Brisbane": "Brisbane Lions",
    "Carlton": "Carlton Blues",
    "Collingwood": "Collingwood Magpies",
    "Essendon": "Essendon Bombers",
    "Fremantle": "Fremantle Dockers",
    "Geelong": "Geelong Cats",
    "Gold Coast": "Gold Coast Suns",
    "GWS Giants": "Greater Western Sydney Giants",
    "Greater Western Sydney": "Greater Western Sydney Giants",
    "Hawthorn": "Hawthorn Hawks",
    "Melbourne": "Melbourne Demons",
    "North Melbourne": "North Melbourne Kangaroos",
    "Port Adelaide": "Port Adelaide Power",
    "Richmond": "Richmond Tigers",
    "St Kilda": "St Kilda Saints",
    "Sydney": "Sydney Swans",
    "West Coast": "West Coast Eagles",
    "Western Bulldogs": "Western Bulldogs",
}

VENUE_ALIASES = {
    "Gabba": "The Gabba",
    "GIANTS Stadium": "Engie Stadium",
    "Manuka": "Manuka Oval",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Append AFL workbook prices to market_snapshots.")
    parser.add_argument("--config", default="config/betmate_automation.yaml")
    parser.add_argument("--settings", default="config/settings.yaml")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--odds-file")
    parser.add_argument("--date-from", help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--date-to", help="YYYY-MM-DD. Defaults to date-from + days.")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--round", dest="round_number", type=int, help="Optional round_number to stamp on created matches.")
    parser.add_argument("--captured-at", help="Override capture timestamp.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = _load_yaml(ROOT / args.config)
    settings = _load_yaml(ROOT / args.settings)
    odds_file = Path(args.odds_file or config.get("afl", {}).get("odds_file", ""))
    if not odds_file:
        raise RuntimeError("AFL odds file not configured. Set afl.odds_file or pass --odds-file.")

    date_from = args.date_from or datetime.now().date().isoformat()
    date_to = args.date_to or (datetime.fromisoformat(date_from).date() + timedelta(days=args.days)).isoformat()
    captured_at = args.captured_at or datetime.now().isoformat(timespec="seconds")

    conn = sqlite3.connect(ROOT / settings["database"]["path"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    rows = _read_workbook(odds_file, date_from, date_to)
    snapshots = []
    missing = []
    for index, row in enumerate(rows, start=1):
        match_id = -index if args.dry_run else _find_or_create_match(conn, row, args.season, args.round_number)
        before = len(snapshots)
        _add_h2h(snapshots, match_id, row, captured_at, str(odds_file))
        _add_handicap(snapshots, match_id, row, captured_at, str(odds_file))
        _add_total(snapshots, match_id, row, captured_at, str(odds_file))
        if len(snapshots) == before:
            missing.append(f"{row['date']} {row['home_team']} v {row['away_team']} (row found, no prices)")

    report = {
        "sport": "AFL",
        "season": args.season,
        "round_number": args.round_number,
        "date_from": date_from,
        "date_to": date_to,
        "captured_at": captured_at,
        "odds_file": str(odds_file),
        "dry_run": args.dry_run,
        "workbook_games": len(rows),
        "snapshots_to_insert": len(snapshots),
        "missing_games": missing,
    }

    if not args.dry_run and snapshots:
        ids = ingest_snapshots_bulk(conn, snapshots)
        report["inserted"] = len(ids)
        report["first_snapshot_id"] = ids[0]
        report["last_snapshot_id"] = ids[-1]
    else:
        report["inserted"] = 0

    log_dir = ROOT / "logs" / "market_snapshots"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = captured_at.replace(":", "").replace("-", "").replace("T", "_").replace(" ", "_")[:15]
    report_path = log_dir / f"afl_{date_from}_{date_to}_{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"AFL market snapshot {date_from} to {date_to}")
    print(f"Odds file: {odds_file}")
    print(f"Captured at: {captured_at}")
    print(f"Workbook games found: {len(rows)}")
    print(f"Snapshots inserted: {report['inserted']} / {len(snapshots)}")
    if missing:
        print("Missing odds for:")
        for game in missing:
            print(f"  - {game}")
    print(f"Report: {report_path}")


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _read_workbook(path: Path, date_from: str, date_to: str) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_excel(path, sheet_name="Data", header=1)
    rows = []
    for _, raw in df.iterrows():
        if pd.isna(raw.get("Date")) or pd.isna(raw.get("Home Team")) or pd.isna(raw.get("Away Team")):
            continue
        game_date = pd.to_datetime(raw["Date"]).date().isoformat()
        if game_date < date_from or game_date > date_to:
            continue
        rows.append(
            {
                "date": game_date,
                "kickoff": _kickoff(raw.get("Kick Off (local)")),
                "home_team": _team(raw["Home Team"]),
                "away_team": _team(raw["Away Team"]),
                "venue": _venue(raw.get("Venue")),
                "raw": raw.to_dict(),
            }
        )
    rows.sort(key=lambda item: (item["date"], item["kickoff"], item["home_team"]))
    return rows


def _team(value) -> str:
    raw = str(value or "").strip()
    return AFL_ALIASES.get(raw, raw)


def _venue(value) -> str:
    raw = str(value or "AFL Venue TBD").strip()
    return VENUE_ALIASES.get(raw, raw)


def _kickoff(value) -> str:
    if value is None or pd.isna(value):
        return "19:00:00"
    text = str(value).strip()
    if " " in text:
        text = text.split(" ")[-1]
    if len(text) == 5:
        return f"{text}:00"
    return text[:8]


def _find_or_create_match(conn: sqlite3.Connection, row: dict, season: int, round_number: int | None) -> int:
    home_id = get_or_create_team(conn, row["home_team"], "AFL")
    away_id = get_or_create_team(conn, row["away_team"], "AFL")
    venue_id = get_or_create_venue(conn, row["venue"])
    source_key = f"afl:{season}:{row['date']}:{row['home_team']}:{row['away_team']}"
    return get_or_create_match(
        conn,
        {
            "sport": "AFL",
            "competition": "AFL",
            "season": season,
            "round_number": round_number,
            "match_date": row["date"],
            "kickoff_datetime": f"{row['date']} {row['kickoff']}",
            "home_team_id": home_id,
            "away_team_id": away_id,
            "venue_id": venue_id,
            "status": "scheduled",
            "source_match_key": source_key,
        },
    )


def _book() -> tuple[str, str]:
    return "Bet365", "bet365"


def _latest(raw: dict, close_col: str, open_col: str):
    close_value = raw.get(close_col)
    if _has_value(close_value):
        return close_value, 0
    open_value = raw.get(open_col)
    if _has_value(open_value):
        return open_value, 1
    return None, 0


def _has_value(value) -> bool:
    return value is not None and not pd.isna(value) and str(value).strip() != ""


def _base(match_id: int, captured_at: str, source_url: str) -> dict:
    bookmaker, bookmaker_code = _book()
    return {
        "match_id": match_id,
        "bookmaker": bookmaker,
        "bookmaker_code": bookmaker_code,
        "captured_at": captured_at,
        "source_method": "api",
        "source_url": source_url,
    }


def _add_h2h(snapshots: list, match_id: int, row: dict, captured_at: str, source_url: str) -> None:
    raw = row["raw"]
    for selection, close_col, open_col in (
        ("home", "Home Odds Close", "Home Odds Open"),
        ("away", "Away Odds Close", "Away Odds Open"),
    ):
        odds, is_opening = _latest(raw, close_col, open_col)
        if not _has_value(odds):
            continue
        item = _base(match_id, captured_at, source_url)
        item.update({"market_type": "h2h", "selection": selection, "odds": odds, "is_opening": is_opening})
        snapshots.append(item)


def _add_handicap(snapshots: list, match_id: int, row: dict, captured_at: str, source_url: str) -> None:
    raw = row["raw"]
    home_line, home_opening = _latest(raw, "Home Line Close", "Home Line Open")
    away_line, away_opening = _latest(raw, "Away Line Close", "Away Line Open")
    home_odds, _ = _latest(raw, "Home Line Odds Close", "Home Line Odds Open")
    away_odds, _ = _latest(raw, "Away Line Odds Close", "Away Line Odds Open")
    for selection, line, odds, is_opening in (
        ("home", home_line, home_odds, home_opening),
        ("away", away_line, away_odds, away_opening),
    ):
        if not _has_value(line) or not _has_value(odds):
            continue
        item = _base(match_id, captured_at, source_url)
        item.update({"market_type": "handicap", "selection": selection, "line": line, "odds": odds, "is_opening": is_opening})
        snapshots.append(item)


def _add_total(snapshots: list, match_id: int, row: dict, captured_at: str, source_url: str) -> None:
    raw = row["raw"]
    total_line, is_opening = _latest(raw, "Total Score Close", "Total Score Open")
    over_odds, _ = _latest(raw, "Total Score Over Close", "Total Score Over Open")
    under_odds, _ = _latest(raw, "Total Score Under Close", "Total Score Under Open")
    for selection, odds in (("over", over_odds), ("under", under_odds)):
        if not _has_value(total_line) or not _has_value(odds):
            continue
        item = _base(match_id, captured_at, source_url)
        item.update({"market_type": "total", "selection": selection, "line": total_line, "odds": odds, "is_opening": is_opening})
        snapshots.append(item)


if __name__ == "__main__":
    main()
