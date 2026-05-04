"""
lib/scraper/nrl_referees.py

Scrapes NRL referee appointments from the NRL.com draw page.
Referees are typically announced Tuesday/Wednesday each week.
Outputs CSV in the exact format BettingEngine's prepare_round.py expects.

Outputs:
  data/nrl/referees/raw/YYYY/round-N.json
  data/nrl/referees/processed/YYYY/round-N-referees.csv
  data/nrl/referees/processed/latest-referees.csv
  data/nrl/referees/logs/scrape.log

Usage:
  uv run --with requests --with beautifulsoup4 python lib/scraper/nrl_referees.py --season 2026 --round 11
"""

from __future__ import annotations

import argparse
import csv
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
BASE_DIR      = ROOT / "data" / "nrl" / "referees"
RAW_DIR       = BASE_DIR / "raw"
PROCESSED_DIR = BASE_DIR / "processed"
LOG_DIR       = BASE_DIR / "logs"
LOG_PATH      = LOG_DIR / "scrape.log"

DEFAULT_TIMEOUT      = 30
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY  = 30
DEFAULT_ROUND_ONE_MONDAY = "2026-03-02"

NRL_DRAW_URL = "https://www.nrl.com/draw/nrl-premiership/{season}/round-{round}/"

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


def fetch_html(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        log.warning("Fetch failed %s — %s", url, exc)
        return None


def extract_json_blobs(html: str) -> list[dict]:
    """Extract any JSON blobs embedded in script tags (NRL.com uses Next.js data)."""
    blobs = []
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", {"id": "__NEXT_DATA__"}):
        try:
            blobs.append(json.loads(script.string))
        except Exception:
            pass
    for script in soup.find_all("script", type="application/json"):
        try:
            blobs.append(json.loads(script.string))
        except Exception:
            pass
    return blobs


def search_blob_for_referees(blob: dict, depth: int = 0) -> list[dict]:
    """Recursively search a JSON blob for referee assignment data."""
    results = []
    if depth > 10:
        return results
    if isinstance(blob, dict):
        # Look for keys that indicate game/match data with referee info
        if "referee" in blob or "officials" in blob:
            results.append(blob)
        for v in blob.values():
            results.extend(search_blob_for_referees(v, depth + 1))
    elif isinstance(blob, list):
        for item in blob:
            results.extend(search_blob_for_referees(item, depth + 1))
    return results


def parse_referee_from_blob(blob: dict) -> dict | None:
    """Try to extract home_team, away_team, referee from a game blob."""
    try:
        home = away = referee = ""

        # Try various structures NRL.com might use
        home = (blob.get("homeTeam") or blob.get("home_team") or
                blob.get("homeTeamName") or "")
        away = (blob.get("awayTeam") or blob.get("away_team") or
                blob.get("awayTeamName") or "")

        if isinstance(home, dict):
            home = home.get("name") or home.get("nickName") or ""
        if isinstance(away, dict):
            away = away.get("name") or away.get("nickName") or ""

        officials = blob.get("officials") or blob.get("referee") or []
        if isinstance(officials, str):
            referee = officials
        elif isinstance(officials, list) and officials:
            first = officials[0]
            if isinstance(first, dict):
                referee = first.get("name") or first.get("fullName") or ""
            else:
                referee = str(first)
        elif isinstance(officials, dict):
            referee = officials.get("name") or officials.get("fullName") or ""

        home = canon_team(home)
        away = canon_team(away)

        if home and away and referee:
            return {"home_team": home, "away_team": away, "referee": referee}
    except Exception:
        pass
    return None


def parse_referee_from_html(html: str) -> list[dict]:
    """
    Fallback: scan page text for patterns like 'Referee: Ashley Klein'
    near team name mentions.
    """
    soup  = BeautifulSoup(html, "html.parser")
    text  = soup.get_text("\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    records = []

    # Look for explicit referee lines
    ref_pattern = re.compile(r"(?:referee|ref)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)", re.IGNORECASE)
    team_pattern = re.compile(r"(" + "|".join(re.escape(k) for k in TEAM_MAP) + r")",
                              re.IGNORECASE)

    current_home = current_away = None
    for i, line in enumerate(lines):
        team_m = team_pattern.search(line)
        if team_m:
            team = canon_team(team_m.group(1))
            if current_home is None:
                current_home = team
            elif current_away is None:
                current_away = team

        ref_m = ref_pattern.search(line)
        if ref_m and current_home and current_away:
            records.append({
                "home_team": current_home,
                "away_team": current_away,
                "referee":   ref_m.group(1).strip(),
            })
            current_home = current_away = None

    return records


def scrape_referees(html: str) -> list[dict]:
    records = []

    # Try JSON blob approach first (NRL.com Next.js)
    blobs = extract_json_blobs(html)
    for blob in blobs:
        game_nodes = search_blob_for_referees(blob)
        for node in game_nodes:
            row = parse_referee_from_blob(node)
            if row:
                records.append(row)

    if not records:
        log.info("JSON blob parse found 0 — trying HTML text fallback")
        records = parse_referee_from_html(html)

    # Deduplicate by (home, away)
    seen = set()
    deduped = []
    for r in records:
        key = (r["home_team"], r["away_team"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped


def write_outputs(records: list[dict], raw_html: str, season: int, round_number: int) -> None:
    scraped_at = datetime.now(timezone.utc).isoformat()

    raw_dir = RAW_DIR / str(season)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"round-{round_number}.json").write_text(
        json.dumps({"scraped_at": scraped_at, "records": records}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    proc_dir = PROCESSED_DIR / str(season)
    proc_dir.mkdir(parents=True, exist_ok=True)

    def write_csv(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["home_team", "away_team", "referee"])
            writer.writeheader()
            writer.writerows(records)

    write_csv(proc_dir / f"round-{round_number}-referees.csv")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(PROCESSED_DIR / "latest-referees.csv")
    log.info("Wrote latest-referees.csv — %d assignments, round %d", len(records), round_number)


def scrape(season: int, round_number: int, max_attempts: int, retry_delay: int) -> int:
    url = NRL_DRAW_URL.format(season=season, round=round_number)
    for attempt in range(1, max_attempts + 1):
        log.info("Attempt %d/%d — referees R%d %d — %s", attempt, max_attempts, round_number, season, url)
        html = fetch_html(url)
        if html:
            records = scrape_referees(html)
            write_outputs(records, html, season, round_number)
            if records:
                log.info("Referees scraped — %d assignments", len(records))
            else:
                log.warning("Page fetched but no referee data found — referees may not be announced yet")
            return len(records)
        if attempt < max_attempts:
            log.warning("Fetch failed, retrying in %ds", retry_delay)
            time.sleep(retry_delay)
    log.error("All attempts exhausted — no referee data")
    return 0


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(description="Scrape NRL referee assignments")
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
