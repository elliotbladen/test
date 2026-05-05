"""
lib/scraper/nrl_injuries.py

Scrapes the NRL casualty ward from NRL.com (server-rendered, no JS required).
Outputs JSON in the exact format BettingEngine's prepare_round.py expects.

Source URL pattern:
  https://www.nrl.com/news/{season}/01/01/nrl-casualty-ward-how-your-club-is-shaping-heading-into-{season}/

Outputs:
  data/nrl/injuries/raw/YYYY/round-N.json
  data/nrl/injuries/processed/YYYY/round-N-injuries.json
  data/nrl/injuries/processed/latest-injuries.json
  data/nrl/injuries/logs/scrape.log

Usage:
  uv run --with requests --with beautifulsoup4 python lib/scraper/nrl_injuries.py --season 2026 --round 10
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
    "cronulla sharks":               "Cronulla-Sutherland Sharks",
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
    "st george illawarra dragons":   "St. George Illawarra Dragons",
    "st. george illawarra dragons":  "St. George Illawarra Dragons",
    "sydney roosters":               "Sydney Roosters",
}

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


def nrl_casualty_url(season: int) -> str:
    return (
        f"https://www.nrl.com/news/{season}/01/01/"
        f"nrl-casualty-ward-how-your-club-is-shaping-heading-into-{season}/"
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
        log.warning("Fetch failed %s -- %s", url, exc)
        return None


def _parse_return_status(return_info: str, current_round: int) -> str | None:
    """
    Convert return round text to a status string.
    Returns 'out', 'doubtful', or None (player already returned -- skip them).
    """
    r = return_info.strip().upper()
    if not r or "TBC" in r or "INDEFINITE" in r:
        return "out"

    m = re.search(r"ROUND[^\d]*(\d+)", r)
    if m:
        return_round = int(m.group(1))
        if return_round < current_round:
            return None       # already returned
        if return_round == current_round:
            return "doubtful"
        return "out"

    return "out"


def _is_team_heading(text: str) -> bool:
    return text.strip().lower() in TEAM_MAP


def parse_nrl_casualty_ward(html: str, season: int, round_number: int) -> list[dict]:
    """
    Parse NRL.com casualty ward article.
    Structure: h3 team headings followed by ul/li player entries.
    Each li: "Player Name: Injury description | Return round/TBC"
    """
    soup = BeautifulSoup(html, "html.parser")
    records = []
    scraped_at = datetime.now(timezone.utc).isoformat()
    current_team: str | None = None

    for element in soup.find_all(["h2", "h3", "h4", "li"]):
        if element.name in ("h2", "h3", "h4"):
            text = element.get_text(strip=True)
            if _is_team_heading(text):
                current_team = canon_team(text)
            else:
                # Non-team heading — reset so we don't misassign players
                current_team = None
            continue

        if element.name == "li" and current_team:
            text = element.get_text(strip=True)
            # Format: "Player Name (injury description, Round N or TBC)"
            m = re.match(r"^(.+?)\s*\((.+)\)$", text)
            if not m:
                continue

            player = m.group(1).strip()
            inner = m.group(2).strip()

            # Split on last comma: "head knock, TBC" or "knee, Round 12-14"
            if "," in inner:
                last_comma = inner.rfind(",")
                injury = inner[:last_comma].strip()
                return_info = inner[last_comma + 1:].strip()
            else:
                injury = inner
                return_info = "TBC"

            status = _parse_return_status(return_info, round_number)
            if status is None:
                log.debug("  Skipping %s (%s) -- already returned (%s)", player, current_team, return_info)
                continue

            records.append({
                "season":          season,
                "round":           round_number,
                "team":            current_team,
                "player":          player,
                "role":            "other",
                "importance_tier": importance_tier(player, ""),
                "status":          status,
                "notes":           f"{injury} | Return: {return_info}",
                "scraped_at":      scraped_at,
            })
            log.debug("  %s %-30s [%s] %s", current_team, player, status, injury)

    if not records:
        log.warning("Parsed 0 records -- page structure may have changed or URL is wrong")

    return records


def write_outputs(records: list[dict], raw_html: str, season: int, round_number: int,
                  source_url: str) -> None:
    scraped_at = datetime.now(timezone.utc).isoformat()

    raw_dir = RAW_DIR / str(season)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"round-{round_number}.json").write_text(
        json.dumps({"scraped_at": scraped_at, "source": source_url,
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
    log.info("Wrote latest-injuries.json -- %d player records, round %d", len(records), round_number)


def scrape(season: int, round_number: int, max_attempts: int, retry_delay: int) -> int:
    url = nrl_casualty_url(season)
    for attempt in range(1, max_attempts + 1):
        log.info("Attempt %d/%d -- injuries R%d %d -- %s", attempt, max_attempts, round_number, season, url)
        html = fetch_html(url)
        if html:
            records = parse_nrl_casualty_ward(html, season, round_number)
            write_outputs(records, html, season, round_number, url)
            log.info("Injuries scraped -- %d records", len(records))
            return len(records)
        if attempt < max_attempts:
            log.warning("Fetch failed, retrying in %ds", retry_delay)
            time.sleep(retry_delay)
    log.error("All attempts exhausted -- no injury data")
    return 0


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(description="Scrape NRL injuries from NRL.com casualty ward")
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
