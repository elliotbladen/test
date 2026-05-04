"""
lib/scraper/nrl_fixture.py

Scrapes the upcoming NRL round fixture from ESPN's public API.
BettingEngine reads latest-fixture.json at pricing time to know
which games are on and auto-detect the round number.

Outputs:
  data/nrl/fixture/raw/YYYY/round-N.json
  data/nrl/fixture/processed/YYYY/round-N-fixture.json
  data/nrl/fixture/processed/latest-fixture.json
  data/nrl/fixture/logs/scrape.log

Usage:
  uv run --with requests python lib/scraper/nrl_fixture.py --season 2026 --round 11
  uv run --with requests python lib/scraper/nrl_fixture.py --season 2026  # auto-detect round
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

ROOT        = Path(__file__).resolve().parents[2]
BASE_DIR    = ROOT / "data" / "nrl" / "fixture"
RAW_DIR     = BASE_DIR / "raw"
PROCESSED_DIR = BASE_DIR / "processed"
LOG_DIR     = BASE_DIR / "logs"
LOG_PATH    = LOG_DIR / "scrape.log"

DEFAULT_TIMEOUT       = 30
DEFAULT_MAX_ATTEMPTS  = 3
DEFAULT_RETRY_DELAY   = 30
DEFAULT_ROUND_ONE_MONDAY = "2026-03-02"

# NRL.com official draw API — returns fixture JSON for any round
NRL_DRAW_API = (
    "https://www.nrl.com/draw/data/"
    "?competition=111&season={season}&round={round}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,*/*",
    "Accept-Language": "en-AU,en;q=0.9",
}

TEAM_MAP = {
    "Brisbane Broncos":              "Brisbane Broncos",
    "Broncos":                       "Brisbane Broncos",
    "Canterbury Bulldogs":           "Canterbury-Bankstown Bulldogs",
    "Canterbury-Bankstown Bulldogs": "Canterbury-Bankstown Bulldogs",
    "Bulldogs":                      "Canterbury-Bankstown Bulldogs",
    "Canberra Raiders":              "Canberra Raiders",
    "Raiders":                       "Canberra Raiders",
    "Cronulla Sharks":               "Cronulla-Sutherland Sharks",
    "Cronulla-Sutherland Sharks":    "Cronulla-Sutherland Sharks",
    "Sharks":                        "Cronulla-Sutherland Sharks",
    "Dolphins":                      "Dolphins",
    "Gold Coast Titans":             "Gold Coast Titans",
    "Titans":                        "Gold Coast Titans",
    "Manly Sea Eagles":              "Manly-Warringah Sea Eagles",
    "Manly-Warringah Sea Eagles":    "Manly-Warringah Sea Eagles",
    "Sea Eagles":                    "Manly-Warringah Sea Eagles",
    "Melbourne Storm":               "Melbourne Storm",
    "Storm":                         "Melbourne Storm",
    "Newcastle Knights":             "Newcastle Knights",
    "Knights":                       "Newcastle Knights",
    "New Zealand Warriors":          "New Zealand Warriors",
    "Warriors":                      "New Zealand Warriors",
    "North Queensland Cowboys":      "North Queensland Cowboys",
    "Cowboys":                       "North Queensland Cowboys",
    "Parramatta Eels":               "Parramatta Eels",
    "Eels":                          "Parramatta Eels",
    "Penrith Panthers":              "Penrith Panthers",
    "Panthers":                      "Penrith Panthers",
    "South Sydney Rabbitohs":        "South Sydney Rabbitohs",
    "Rabbitohs":                     "South Sydney Rabbitohs",
    "St. George Illawarra Dragons":  "St. George Illawarra Dragons",
    "St George Illawarra Dragons":   "St. George Illawarra Dragons",
    "Dragons":                       "St. George Illawarra Dragons",
    "Sydney Roosters":               "Sydney Roosters",
    "Roosters":                      "Sydney Roosters",
    "Wests Tigers":                  "Wests Tigers",
    "Tigers":                        "Wests Tigers",
}

log = logging.getLogger(__name__)


def setup_logging() -> None:
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


def infer_round(round_one_monday: str) -> int:
    monday = datetime.strptime(round_one_monday, "%Y-%m-%d").date()
    today  = datetime.now().date()
    if today < monday:
        return 1
    return (today - monday).days // 7 + 1


def canon_team(raw: str) -> str:
    return TEAM_MAP.get(raw.strip(), raw.strip())


def fetch_json(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.warning("Fetch failed %s — %s", url, exc)
        return None


def parse_nrl_fixture(fixture: dict, season: int, round_number: int) -> dict | None:
    """Parse a single fixture object from NRL.com draw API."""
    try:
        if fixture.get("type") != "Match":
            return None  # skip byes etc.

        home_nick = fixture.get("homeTeam", {}).get("nickName", "")
        away_nick = fixture.get("awayTeam", {}).get("nickName", "")
        home_name = canon_team(home_nick)
        away_name = canon_team(away_nick)
        venue     = fixture.get("venue", "")
        kickoff_utc = fixture.get("clock", {}).get("kickOffTimeLong", "")

        try:
            dt_utc  = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
            dt_aest = dt_utc + timedelta(hours=10)
            kickoff_local = dt_aest.strftime("%Y-%m-%dT%H:%M:%S+10:00")
        except Exception:
            kickoff_local = kickoff_utc

        if not home_name or not away_name:
            return None

        return {
            "season":        season,
            "round":         round_number,
            "home_team":     home_name,
            "away_team":     away_name,
            "venue":         venue,
            "kickoff_utc":   kickoff_utc,
            "kickoff_local": kickoff_local,
        }
    except Exception as exc:
        log.warning("parse_nrl_fixture error — %s", exc)
        return None


def fetch_via_nrl_api(season: int, round_number: int) -> tuple[list[dict], dict]:
    url = NRL_DRAW_API.format(season=season, round=round_number)
    log.info("NRL draw API: %s", url)
    raw = fetch_json(url)
    if not raw:
        return [], {}

    games = []
    for f in raw.get("fixtures", []):
        p = parse_nrl_fixture(f, season, round_number)
        if p:
            games.append(p)

    return games, raw


def write_outputs(games: list[dict], raw: dict, season: int, round_number: int) -> None:
    scraped_at = datetime.now(timezone.utc).isoformat()

    raw_dir = RAW_DIR / str(season)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"round-{round_number}.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    payload = {
        "season":     season,
        "round":      round_number,
        "scraped_at": scraped_at,
        "game_count": len(games),
        "games":      games,
    }
    proc_dir = PROCESSED_DIR / str(season)
    proc_dir.mkdir(parents=True, exist_ok=True)
    (proc_dir / f"round-{round_number}-fixture.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    (PROCESSED_DIR / "latest-fixture.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Wrote latest-fixture.json — %d games, round %d", len(games), round_number)


def scrape(season: int, round_number: int, max_attempts: int, retry_delay: int) -> int:
    for attempt in range(1, max_attempts + 1):
        log.info("Attempt %d/%d — R%d %d", attempt, max_attempts, round_number, season)
        games, raw = fetch_via_nrl_api(season, round_number)
        if games:
            write_outputs(games, raw, season, round_number)
            return len(games)
        if attempt < max_attempts:
            log.warning("No games found, retrying in %ds", retry_delay)
            time.sleep(retry_delay)
    log.error("All attempts exhausted — no fixture data for R%d", round_number)
    return 0


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(description="Scrape NRL fixture")
    p.add_argument("--season", type=int, default=2026)
    p.add_argument("--round", dest="round_number", type=int, default=0)
    p.add_argument("--round-one-monday", default=DEFAULT_ROUND_ONE_MONDAY)
    p.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    p.add_argument("--retry-delay-seconds", type=int, default=DEFAULT_RETRY_DELAY)
    args = p.parse_args()

    round_number = args.round_number or infer_round(args.round_one_monday)
    log.info("Targeting season=%d round=%d", args.season, round_number)
    count = scrape(args.season, round_number, args.max_attempts, args.retry_delay_seconds)
    sys.exit(0 if count > 0 else 1)


if __name__ == "__main__":
    main()
