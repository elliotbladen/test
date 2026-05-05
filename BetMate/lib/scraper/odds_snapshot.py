"""
lib/scraper/odds_snapshot.py

Daily odds snapshot — pulls NRL + AFL from The Odds API and saves to CSV.

One row per game × bookmaker × market × outcome.
Run daily so you have a full year of odds movement to study.

Outputs:
  data/odds_snapshots/YYYY/YYYY-MM-DD.csv   ← dated archive
  data/odds_snapshots/latest.csv            ← always most recent

Usage:
  python lib/scraper/odds_snapshot.py
  python lib/scraper/odds_snapshot.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT       = Path(__file__).resolve().parents[2]
SNAP_DIR   = ROOT / "data" / "odds_snapshots"
LOG_DIR    = SNAP_DIR / "logs"
LOG_PATH   = LOG_DIR / "snapshot.log"
ENV_PATH   = ROOT / ".env.local"

SPORTS = {
    "NRL": "rugbyleague_nrl",
    "AFL": "aussierules_afl",
}

BASE_URL    = "https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
REGIONS     = "au"
MARKETS     = "h2h,spreads,totals"
ODDS_FORMAT = "decimal"

FIELDNAMES = [
    "snapshot_date", "snapshot_time", "sport",
    "game_id", "home_team", "away_team", "commence_time",
    "bookmaker", "market", "outcome", "price", "point",
]

log = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_api_key() -> str:
    """Read ODDS_API_KEY from .env.local or environment."""
    key = os.environ.get("ODDS_API_KEY", "")
    if key:
        return key
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ODDS_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    return ""


def fetch_odds(api_key: str, sport_key: str) -> list[dict]:
    url = BASE_URL.format(sport_key=sport_key)
    params = {
        "apiKey":     api_key,
        "regions":    REGIONS,
        "markets":    MARKETS,
        "oddsFormat": ODDS_FORMAT,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    remaining = resp.headers.get("x-requests-remaining", "?")
    log.info("  %s — %s events, %s API calls remaining", sport_key, len(resp.json()), remaining)
    return resp.json()


def flatten(events: list[dict], sport: str, snap_date: str, snap_time: str) -> list[dict]:
    """Flatten Odds API response into one row per game × bookmaker × market × outcome."""
    rows = []
    for event in events:
        base = {
            "snapshot_date": snap_date,
            "snapshot_time": snap_time,
            "sport":         sport,
            "game_id":       event["id"],
            "home_team":     event["home_team"],
            "away_team":     event["away_team"],
            "commence_time": event["commence_time"],
        }
        for bm in event.get("bookmakers", []):
            bm_key = bm["key"]
            for mkt in bm.get("markets", []):
                mkt_key = mkt["key"]  # h2h / spreads / totals
                for outcome in mkt.get("outcomes", []):
                    rows.append({
                        **base,
                        "bookmaker": bm_key,
                        "market":    mkt_key,
                        "outcome":   outcome["name"],
                        "price":     outcome["price"],
                        "point":     outcome.get("point", ""),
                    })
    return rows


def write_csv(rows: list[dict], path: Path, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and path.exists() else "w"
    with open(path, mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        if mode == "w":
            writer.writeheader()
        writer.writerows(rows)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Intraday odds snapshot to CSV")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't write files")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    api_key = load_api_key()
    if not api_key:
        log.error("ODDS_API_KEY not found in environment or .env.local")
        sys.exit(1)

    now       = datetime.now(timezone.utc)
    snap_date = now.strftime("%Y-%m-%d")
    snap_time = now.strftime("%H:%M:%S")
    year      = now.strftime("%Y")

    all_rows: list[dict] = []

    for sport, sport_key in SPORTS.items():
        log.info("Fetching %s odds ...", sport)
        try:
            events = fetch_odds(api_key, sport_key)
            rows   = flatten(events, sport, snap_date, snap_time)
            log.info("  %d rows", len(rows))
            all_rows.extend(rows)
        except Exception as exc:
            log.error("Failed to fetch %s — %s", sport, exc)

    if not all_rows:
        log.warning("No data fetched — nothing written.")
        sys.exit(1)

    if args.dry_run:
        log.info("DRY RUN — would write %d rows. Sample:", len(all_rows))
        for r in all_rows[:3]:
            log.info("  %s", r)
        return

    # Dated archive: append intraday snapshots so the file becomes a time series.
    dated_path = SNAP_DIR / year / f"{snap_date}.csv"
    append = dated_path.exists()
    write_csv(all_rows, dated_path, append=append)
    log.info("%s: %s (%d rows)", "Appended" if append else "Saved", dated_path, len(all_rows))

    # Latest copy
    latest_path = SNAP_DIR / "latest.csv"
    write_csv(all_rows, latest_path)
    log.info("Updated: %s", latest_path)


if __name__ == "__main__":
    main()
