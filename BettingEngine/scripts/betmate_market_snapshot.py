#!/usr/bin/env python3
"""Capture NRL bookmaker market snapshots from Betmate's odds workbook.

This reads Betmate's already-collected historical/current odds workbook and
appends the latest available H2H, handicap, and totals prices into
market_snapshots. It does not scrape bookmakers itself.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingestion.market_snapshots import ingest_snapshots_bulk  # noqa: E402
from normalization.normalizers import normalize_team_name  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Append Betmate odds workbook prices to market_snapshots.")
    parser.add_argument("--config", default="config/betmate_automation.yaml")
    parser.add_argument("--settings", default="config/settings.yaml")
    parser.add_argument("--season", type=int)
    parser.add_argument("--round", dest="round_number", type=int)
    parser.add_argument(
        "--round-mode",
        choices=["next", "current_or_next"],
        default="next",
        help="next = first round whose first game is after today; current_or_next = first round with any remaining game.",
    )
    parser.add_argument("--odds-file", help="Override Betmate historical odds workbook path.")
    parser.add_argument("--captured-at", help="Override capture timestamp, ISO/local format.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = _load_yaml(ROOT / args.config)
    settings = _load_yaml(ROOT / args.settings)
    season = args.season or int(config["pricing"]["season"])
    db_path = ROOT / settings["database"]["path"]
    odds_file = Path(args.odds_file) if args.odds_file else _default_odds_file(config)
    captured_at = args.captured_at or datetime.now().isoformat(timespec="seconds")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    round_number = args.round_number or _auto_round(conn, season, args.round_mode)
    matches = _round_matches(conn, season, round_number)
    rows = _read_betmate_workbook(odds_file)
    snapshots, missing = _build_snapshots(matches, rows, captured_at, str(odds_file))

    report = {
        "season": season,
        "round_number": round_number,
        "captured_at": captured_at,
        "odds_file": str(odds_file),
        "dry_run": args.dry_run,
        "matches": len(matches),
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
    report_path = log_dir / f"nrl_r{round_number}_{season}_{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"NRL R{round_number} {season} market snapshot")
    print(f"Odds file: {odds_file}")
    print(f"Captured at: {captured_at}")
    print(f"Snapshots inserted: {report['inserted']} / {len(snapshots)}")
    if missing:
        print("Missing odds for:")
        for game in missing:
            print(f"  - {game}")
    print(f"Report: {report_path}")


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _default_odds_file(config: dict) -> Path:
    return Path(config["betmate"]["root"]) / "historical-odds" / "latest" / "nrl.xlsx"


def _auto_round(conn: sqlite3.Connection, season: int, mode: str) -> int:
    today = datetime.now().date().isoformat()
    if mode == "next":
        row = conn.execute(
            """
            SELECT round_number
            FROM matches
            WHERE sport = 'NRL' AND season = ?
            GROUP BY round_number
            HAVING MIN(match_date) > ?
            ORDER BY MIN(match_date)
            LIMIT 1
            """,
            (season, today),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT round_number
            FROM matches
            WHERE sport = 'NRL' AND season = ?
            GROUP BY round_number
            HAVING MAX(match_date) >= ?
            ORDER BY MIN(match_date)
            LIMIT 1
            """,
            (season, today),
        ).fetchone()
    if not row:
        raise RuntimeError(f"Could not auto-detect target NRL round for season {season}")
    return int(row["round_number"])


def _round_matches(conn: sqlite3.Connection, season: int, round_number: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            m.match_id,
            m.match_date,
            ht.team_name AS home_team,
            at.team_name AS away_team
        FROM matches m
        JOIN teams ht ON ht.team_id = m.home_team_id
        JOIN teams at ON at.team_id = m.away_team_id
        WHERE m.sport = 'NRL' AND m.season = ? AND m.round_number = ?
        ORDER BY m.match_date, m.kickoff_datetime
        """,
        (season, round_number),
    ).fetchall()
    return [dict(row) for row in rows]


def _read_betmate_workbook(path: Path) -> dict[tuple[str, str, str], dict]:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_excel(path, sheet_name="Data", header=1)
    rows = {}
    for _, row in df.iterrows():
        if pd.isna(row.get("Date")) or pd.isna(row.get("Home Team")) or pd.isna(row.get("Away Team")):
            continue
        date = pd.to_datetime(row["Date"]).date().isoformat()
        home = normalize_team_name(row["Home Team"])
        away = normalize_team_name(row["Away Team"])
        rows[(date, home, away)] = row.to_dict()
    return rows


def _build_snapshots(
    matches: list[dict],
    workbook_rows: dict[tuple[str, str, str], dict],
    captured_at: str,
    source_url: str,
) -> tuple[list[dict], list[str]]:
    snapshots = []
    missing = []
    for match in matches:
        key = (match["match_date"], match["home_team"], match["away_team"])
        row = workbook_rows.get(key)
        if row is None:
            missing.append(f"{match['match_date']} {match['home_team']} v {match['away_team']}")
            continue

        bookmaker_name, bookmaker_code = _bookmaker_for_date(match["match_date"])
        before = len(snapshots)
        _add_h2h(snapshots, match, row, bookmaker_name, bookmaker_code, captured_at, source_url)
        _add_handicap(snapshots, match, row, bookmaker_name, bookmaker_code, captured_at, source_url)
        _add_total(snapshots, match, row, bookmaker_name, bookmaker_code, captured_at, source_url)
        if len(snapshots) == before:
            missing.append(f"{match['match_date']} {match['home_team']} v {match['away_team']} (row found, no prices)")
    return snapshots, missing


def _bookmaker_for_date(match_date: str) -> tuple[str, str]:
    if match_date >= "2024-04-29":
        return "BlueBet", "bluebet"
    if match_date >= "2018-04-03":
        return "Bet365", "bet365"
    return "Pinnacle", "pinnacle"


def _latest(row: dict, close_col: str, open_col: str):
    close_value = row.get(close_col)
    if _has_value(close_value):
        return close_value, 0
    open_value = row.get(open_col)
    if _has_value(open_value):
        return open_value, 1
    return None, 0


def _has_value(value) -> bool:
    return value is not None and not pd.isna(value) and str(value).strip() != ""


def _base(match: dict, bookmaker_name: str, bookmaker_code: str, captured_at: str, source_url: str) -> dict:
    return {
        "match_id": match["match_id"],
        "bookmaker": bookmaker_name,
        "bookmaker_code": bookmaker_code,
        "captured_at": captured_at,
        "source_method": "api",
        "source_url": source_url,
    }


def _add_h2h(snapshots: list, match: dict, row: dict, bookmaker_name: str, bookmaker_code: str, captured_at: str, source_url: str) -> None:
    for selection, close_col, open_col in (
        ("home", "Home Odds Close", "Home Odds Open"),
        ("away", "Away Odds Close", "Away Odds Open"),
    ):
        odds, is_opening = _latest(row, close_col, open_col)
        if not _has_value(odds):
            continue
        item = _base(match, bookmaker_name, bookmaker_code, captured_at, source_url)
        item.update({"market_type": "h2h", "selection": selection, "odds": odds, "is_opening": is_opening})
        snapshots.append(item)


def _add_handicap(snapshots: list, match: dict, row: dict, bookmaker_name: str, bookmaker_code: str, captured_at: str, source_url: str) -> None:
    home_line, home_opening = _latest(row, "Home Line Close", "Home Line Open")
    away_line, away_opening = _latest(row, "Away Line Close", "Away Line Open")
    home_odds, _ = _latest(row, "Home Line Odds Close", "Home Line Odds Open")
    away_odds, _ = _latest(row, "Away Line Odds Close", "Away Line Odds Open")
    for selection, line, odds, is_opening in (
        ("home", home_line, home_odds, home_opening),
        ("away", away_line, away_odds, away_opening),
    ):
        if not _has_value(line) or not _has_value(odds):
            continue
        item = _base(match, bookmaker_name, bookmaker_code, captured_at, source_url)
        item.update({"market_type": "handicap", "selection": selection, "line": line, "odds": odds, "is_opening": is_opening})
        snapshots.append(item)


def _add_total(snapshots: list, match: dict, row: dict, bookmaker_name: str, bookmaker_code: str, captured_at: str, source_url: str) -> None:
    total_line, is_opening = _latest(row, "Total Score Close", "Total Score Open")
    over_odds, _ = _latest(row, "Total Score Over Close", "Total Score Over Open")
    under_odds, _ = _latest(row, "Total Score Under Close", "Total Score Under Open")
    for selection, odds in (("over", over_odds), ("under", under_odds)):
        if not _has_value(total_line) or not _has_value(odds):
            continue
        item = _base(match, bookmaker_name, bookmaker_code, captured_at, source_url)
        item.update({"market_type": "total", "selection": selection, "line": total_line, "odds": odds, "is_opening": is_opening})
        snapshots.append(item)


if __name__ == "__main__":
    main()
