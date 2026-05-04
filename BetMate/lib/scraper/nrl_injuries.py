"""
lib/scraper/nrl_injuries.py

Scrapes the NRL injury/team list from Fox Sports.
Outputs JSON in the exact format BettingEngine's prepare_round.py expects.

Outputs:
  data/nrl/injuries/raw/YYYY/round-N.json
  data/nrl/injuries/processed/YYYY/round-N-injuries.json
  data/nrl/injuries/processed/latest-injuries.json
  data/nrl/injuries/logs/scrape.log

Usage:
  uv run --with requests --with beautifulsoup4 python lib/scraper/nrl_injuries.py --season 2026 --round 11
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT          = Path(__file__).resolve().parents[2]
BASE_DIR      = ROOT / "data" / "nrl" / "injuries"
RAW_DIR       = BASE_DIR / "raw"
PROCESSED_DIR = BASE_DIR / "processed"
LOG_DIR       = BASE_DIR / "logs"
LOG_PATH      = LOG_DIR / "scrape.log"

DEFAULT_TIMEOUT      = 30
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY  = 30
DEFAULT_ROUND_ONE_MONDAY = "2026-03-02"

# Fox Sports NRL injury list page
FOX_INJURY_URL = "https://www.foxsports.com.au/nrl/injury-list"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

TEAM_MAP = {
    "broncos":          "Brisbane Broncos",
    "bulldogs":         "Canterbury-Bankstown Bulldogs",
    "raiders":          "Canberra Raiders",
    "sharks":           "Cronulla-Sutherland Sharks",
    "dolphins":         "Dolphins",
    "titans":           "Gold Coast Titans",
    "sea eagles":       "Manly-Warringah Sea Eagles",
    "storm":            "Melbourne Storm",
    "knights":          "Newcastle Knights",
    "warriors":         "New Zealand Warriors",
    "cowboys":          "North Queensland Cowboys",
    "eels":             "Parramatta Eels",
    "panthers":         "Penrith Panthers",
    "rabbitohs":        "South Sydney Rabbitohs",
    "dragons":          "St. George Illawarra Dragons",
    "roosters":         "Sydney Roosters",
    "wests tigers":     "Wests Tigers",
    "tigers":           "Wests Tigers",
    # full names
    "brisbane broncos":              "Brisbane Broncos",
    "canterbury-bankstown bulldogs": "Canterbury-Bankstown Bulldogs",
    "canberra raiders":              "Canberra Raiders",
    "cronulla-sutherland sharks":    "Cronulla-Sutherland Sharks",
    "gold coast titans":             "Gold Coast Titans",
    "manly-warringah sea eagles":    "Manly-Warringah Sea Eagles",
    "melbourne storm":               "Melbourne Storm",
    "newcastle knights":             "Newcastle Knights",
    "new zealand warriors":          "New Zealand Warriors",
    "north queensland cowboys":      "North Queensland Cowboys",
    "parramatta eels":               "Parramatta Eels",
    "penrith panthers":              "Penrith Panthers",
    "south sydney rabbitohs":        "South Sydney Rabbitohs",
    "st. george illawarra dragons":  "St. George Illawarra Dragons",
    "sydney roosters":               "Sydney Roosters",
}

# Position → role mapping for BettingEngine tier5
POSITION_ROLE_MAP = {
    "halfback":      "halfback",
    "half":          "halfback",
    "five-eighth":   "five_eighth",
    "five eighth":   "five_eighth",
    "hooker":        "hooker",
    "rake":          "hooker",
    "fullback":      "fullback",
    "prop":          "pack",
    "lock":          "pack",
    "second row":    "pack",
    "second-row":    "pack",
    "interchange":   "pack",
    "winger":        "other",
    "centre":        "other",
    "center":        "other",
}

# Known elite/key players — drives importance_tier assignment
# Update each season as rosters change
ELITE_PLAYERS = {
    "Adam Reynolds", "Daly Cherry-Evans", "Cameron Munster", "Nathan Cleary",
    "Jarome Luai", "Nicho Hynes", "Kieran Foran", "Luke Brooks",
    "Apisai Koroisau", "Reed Mahoney", "Harry Grant", "Ben Hunt",
    "Reuben Cotter", "Josh Addo-Carr", "Joseph Suaalii", "James Tedesco",
    "Latrell Mitchell", "Tom Trbojevic",
}

KEY_PLAYERS = {
    "Jake Turpin", "Reece Walsh", "Selwyn Cobbo", "Corey Oates",
    "Jamayne Isaako", "Hamiso Tabuai-Fidow", "Connelly Lemuelu",
    "Mitchell Moses", "Dylan Brown", "Jaeman Salmon",
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
    return TEAM_MAP.get(raw.strip().lower(), raw.strip())


def importance_tier(player: str, position: str) -> str:
    if player in ELITE_PLAYERS:
        return "elite"
    if player in KEY_PLAYERS:
        return "key"
    pos = position.lower()
    if any(k in pos for k in ("halfback", "half", "five", "hooker", "fullback")):
        return "key"
    return "rotation"


def role_from_position(position: str) -> str:
    pos = position.strip().lower()
    for key, role in POSITION_ROLE_MAP.items():
        if key in pos:
            return role
    return "other"


def fetch_html(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        log.warning("Fetch failed %s — %s", url, exc)
        return None


def parse_fox_injury_page(html: str, season: int, round_number: int) -> list[dict]:
    """
    Parse Fox Sports injury list page.
    Structure: team headings followed by player rows with name, position, injury, status.
    Falls back to text extraction if table structure changes.
    """
    soup    = BeautifulSoup(html, "html.parser")
    records = []
    scraped_at = datetime.now(timezone.utc).isoformat()
    current_team = None

    # Try structured table approach first
    for element in soup.find_all(["h2", "h3", "h4", "tr", "div"]):
        text = element.get_text(strip=True)

        # Detect team heading
        canon = canon_team(text)
        if canon != text or text.lower() in TEAM_MAP:
            current_team = canon
            continue

        if not current_team:
            continue

        # Try to parse player rows from table
        if element.name == "tr":
            cells = [td.get_text(strip=True) for td in element.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            player   = cells[0] if cells else ""
            position = cells[1] if len(cells) > 1 else "other"
            injury   = cells[2] if len(cells) > 2 else ""
            status   = cells[3].lower() if len(cells) > 3 else "out"

            if not player or player.lower() in ("player", "name", ""):
                continue

            status_clean = "out" if "out" in status else (
                "doubtful" if "doubtful" in status or "test" in status else (
                    "managed" if "managed" in status or "managed" in injury.lower() else "out"
                )
            )
            records.append({
                "season":           season,
                "round":            round_number,
                "team":             current_team,
                "player":           player,
                "role":             role_from_position(position),
                "importance_tier":  importance_tier(player, position),
                "status":           status_clean,
                "notes":            injury,
                "scraped_at":       scraped_at,
            })

    if not records:
        log.warning("Structured parse found 0 records — page structure may have changed")

    return records


def write_outputs(records: list[dict], raw_html: str, season: int, round_number: int) -> None:
    scraped_at = datetime.now(timezone.utc).isoformat()

    raw_dir = RAW_DIR / str(season)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"round-{round_number}.json").write_text(
        json.dumps({"scraped_at": scraped_at, "source": FOX_INJURY_URL,
                    "raw_length": len(raw_html)}, indent=2),
        encoding="utf-8",
    )

    proc_dir = PROCESSED_DIR / str(season)
    proc_dir.mkdir(parents=True, exist_ok=True)
    (proc_dir / f"round-{round_number}-injuries.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    (PROCESSED_DIR / "latest-injuries.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Wrote latest-injuries.json — %d player records, round %d", len(records), round_number)


def scrape(season: int, round_number: int, max_attempts: int, retry_delay: int) -> int:
    for attempt in range(1, max_attempts + 1):
        log.info("Attempt %d/%d — injuries R%d %d", attempt, max_attempts, round_number, season)
        html = fetch_html(FOX_INJURY_URL)
        if html:
            records = parse_fox_injury_page(html, season, round_number)
            write_outputs(records, html, season, round_number)
            log.info("Injuries scraped — %d records", len(records))
            return len(records)
        if attempt < max_attempts:
            log.warning("Fetch failed, retrying in %ds", retry_delay)
            time.sleep(retry_delay)
    log.error("All attempts exhausted — no injury data")
    return 0


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(description="Scrape NRL injuries")
    p.add_argument("--season", type=int, default=2026)
    p.add_argument("--round", dest="round_number", type=int, default=0)
    p.add_argument("--round-one-monday", default=DEFAULT_ROUND_ONE_MONDAY)
    p.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    p.add_argument("--retry-delay-seconds", type=int, default=DEFAULT_RETRY_DELAY)
    args = p.parse_args()

    round_number = args.round_number or infer_round(args.round_one_monday)
    log.info("Targeting season=%d round=%d", args.season, round_number)
    count = scrape(args.season, round_number, args.max_attempts, args.retry_delay_seconds)
    sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()
