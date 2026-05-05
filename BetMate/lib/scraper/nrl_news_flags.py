"""
lib/scraper/nrl_news_flags.py

Nightly NRL market news scanner.

Flags post-game news that can move Monday odds:
  - Cat 1 HIA / failed HIA / concussion protocols
  - surgery / scans / did not return / ruled out
  - suspensions / judiciary charges / facing bans
  - key player injury language

Outputs:
  data/nrl/news_flags/raw/YYYY/YYYY-MM-DD.json
  data/nrl/news_flags/processed/YYYY/YYYY-MM-DD.json
  data/nrl/news_flags/processed/YYYY/YYYY-MM-DD.csv
  data/nrl/news_flags/processed/latest.json
  data/nrl/news_flags/processed/latest.csv

Usage:
  uv run --with requests --with beautifulsoup4 python lib/scraper/nrl_news_flags.py --season 2026
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = ROOT / "data" / "nrl" / "news_flags"
RAW_DIR = BASE_DIR / "raw"
PROCESSED_DIR = BASE_DIR / "processed"
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "scrape.log"
FIXTURE_PATH = ROOT / "data" / "nrl" / "fixture" / "processed" / "latest-fixture.json"
INJURIES_PATH = ROOT / "data" / "nrl" / "injuries" / "processed" / "latest-injuries.json"

DEFAULT_ROUND_ONE_MONDAY = "2026-03-02"
DEFAULT_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

TEAM_ALIASES = {
    "Brisbane Broncos": ["broncos", "brisbane"],
    "Canterbury-Bankstown Bulldogs": ["bulldogs", "canterbury"],
    "Canberra Raiders": ["raiders", "canberra"],
    "Cronulla-Sutherland Sharks": ["sharks", "cronulla"],
    "Dolphins": ["dolphins"],
    "Gold Coast Titans": ["titans", "gold coast"],
    "Manly-Warringah Sea Eagles": ["sea eagles", "manly", "manly-warringah"],
    "Melbourne Storm": ["storm", "melbourne"],
    "Newcastle Knights": ["knights", "newcastle"],
    "New Zealand Warriors": ["warriors", "new zealand"],
    "North Queensland Cowboys": ["cowboys", "north queensland"],
    "Parramatta Eels": ["eels", "parramatta"],
    "Penrith Panthers": ["panthers", "penrith"],
    "South Sydney Rabbitohs": ["rabbitohs", "south sydney"],
    "St. George Illawarra Dragons": ["dragons", "st george", "st. george"],
    "Sydney Roosters": ["roosters", "sydney roosters"],
    "Wests Tigers": ["wests tigers", "tigers"],
}

CLUB_NEWS_URLS = {
    "Brisbane Broncos": "https://www.broncos.com.au/news/",
    "Canterbury-Bankstown Bulldogs": "https://www.bulldogs.com.au/news/",
    "Canberra Raiders": "https://www.raiders.com.au/news/",
    "Cronulla-Sutherland Sharks": "https://www.sharks.com.au/news/",
    "Dolphins": "https://www.dolphinsnrl.com.au/news/",
    "Gold Coast Titans": "https://www.titans.com.au/news/",
    "Manly-Warringah Sea Eagles": "https://www.seaeagles.com.au/news/",
    "Melbourne Storm": "https://www.melbournestorm.com.au/news/",
    "Newcastle Knights": "https://www.newcastleknights.com.au/news/",
    "New Zealand Warriors": "https://www.warriors.kiwi/news/",
    "North Queensland Cowboys": "https://www.cowboys.com.au/news/",
    "Parramatta Eels": "https://www.parraeels.com.au/news/",
    "Penrith Panthers": "https://www.penrithpanthers.com.au/news/",
    "South Sydney Rabbitohs": "https://www.rabbitohs.com.au/news/",
    "St. George Illawarra Dragons": "https://www.dragons.com.au/news/",
    "Sydney Roosters": "https://www.roosters.com.au/news/",
    "Wests Tigers": "https://www.weststigers.com.au/news/",
}

HIGH_TERMS = [
    "category 1", "cat 1", "failed hia", "surgery", "suspended", "suspension",
    "ruled out", "out indefinitely", "season-ending", "season ending", "acl",
    "fractured", "ruptured", "broken", "limb-saving", "limb saving",
]
MEDIUM_TERMS = [
    "hia", "head knock", "concussion", "sent for scans", "scans", "did not return",
    "failed to finish", "tbc", "doubtful", "hamstring", "calf", "knee",
    "shoulder", "ankle", "groin", "quad", "thigh", "syndesmosis",
]
LOW_TERMS = ["cork", "knock", "niggle", "illness", "rested", "managed"]

SPINE_TERMS = ["halfback", "five-eighth", "five eighth", "hooker", "fullback", "captain", "goal kicker"]
FLAG_TERMS = HIGH_TERMS + MEDIUM_TERMS + LOW_TERMS + SPINE_TERMS

MARKET_KEY_PLAYERS = {
    "Adam Reynolds", "Payne Haas", "Ben Hunt", "Reece Walsh", "Kotoni Staggs",
    "Patrick Carrigan", "Ezra Mam", "Daly Cherry-Evans", "Tom Trbojevic",
    "Jamal Fogarty", "Luke Brooks", "Haumole Olakau'atu", "Nathan Cleary",
    "Jarome Luai", "Mitchell Moses", "Dylan Brown", "Nicho Hynes",
    "Cameron Munster", "Jahrome Hughes", "Harry Grant", "Ryan Papenhuyzen",
    "Latrell Mitchell", "Cody Walker", "Kalyn Ponga", "Reed Mahoney",
    "Api Koroisau", "Tino Fa'asuamaleaui", "David Fifita", "James Tedesco",
}

log = logging.getLogger(__name__)


@dataclass
class Source:
    name: str
    url: str
    team: str | None = None


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
    today = datetime.now().date()
    if today < monday:
        return 1
    return (today - monday).days // 7 + 1


def nrl_casualty_url(season: int) -> str:
    return (
        f"https://www.nrl.com/news/{season}/01/01/"
        f"nrl-casualty-ward-how-your-club-is-shaping-heading-into-{season}/"
    )


def nrl_judiciary_url(season: int) -> str:
    return f"https://www.nrl.com/news/{season}/01/01/nrl-judiciary-report-{season}/"


def fetch_html(source: Source) -> str | None:
    try:
        resp = requests.get(source.url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        log.info("Fetched %-32s %s bytes", source.name, len(resp.text))
        return resp.text
    except Exception as exc:
        log.warning("Fetch failed %-32s %s -- %s", source.name, source.url, exc)
        return None


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    text = clean_text(text)
    parts = re.split(r"(?<=[.!?])\s+|(?:\s+-\s+)|(?:\s+\|\s+)", text)
    return [p.strip() for p in parts if len(p.strip()) >= 35]


def text_chunks(soup: BeautifulSoup) -> list[str]:
    chunks = []
    for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th"]):
        text = clean_text(element.get_text(" "))
        if len(text) < 25:
            continue
        if "Skip to main content" in text or "Share via Facebook" in text:
            continue
        if len(text) > 420:
            chunks.extend(split_sentences(text))
        else:
            chunks.append(text)
    return chunks


def contains_flag(text: str) -> bool:
    lower = text.lower()
    return any(term_matches(lower, term) for term in FLAG_TERMS)


def term_matches(lower_text: str, term: str) -> bool:
    escaped = re.escape(term.lower())
    if term.replace("-", "").replace(" ", "").isalnum():
        return re.search(rf"\b{escaped}\b", lower_text) is not None
    return term.lower() in lower_text


def infer_teams(text: str, preferred_team: str | None = None) -> list[str]:
    if preferred_team:
        return [preferred_team]
    lower = text.lower()
    teams = []
    for team, aliases in TEAM_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", lower) for alias in aliases):
            teams.append(team)
    return teams


def load_injury_players() -> dict[str, str]:
    if not INJURIES_PATH.exists():
        return {}
    try:
        records = json.loads(INJURIES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {r.get("player", ""): r.get("importance_tier", "rotation") for r in records if r.get("player")}


def infer_player(text: str, known_players: dict[str, str]) -> str:
    for player in known_players:
        if player and re.search(rf"\b{re.escape(player)}\b", text, re.IGNORECASE):
            return player
    # Conservative fallback: two capitalised words near the start of the sentence.
    match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-zA-Z'.-]+){1,2})\b", text)
    return match.group(1) if match else ""


def classify_flag(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in ["suspended", "suspension", "facing ban", "charged"]):
        return "SUSPENSION"
    if any(term in lower for term in ["cat 1", "category 1", "failed hia", "head knock", "concussion", "hia"]):
        return "HIA"
    if any(term in lower for term in ["surgery", "scans", "fractured", "broken", "ruptured", "acl"]):
        return "INJURY"
    if any(term in lower for term in ["ruled out", "did not return", "failed to finish", "doubtful", "tbc"]):
        return "AVAILABILITY"
    return "WATCH"


def severity_for(text: str, player: str, known_players: dict[str, str]) -> str:
    lower = text.lower()
    tier = known_players.get(player, "")
    if (
        player in MARKET_KEY_PLAYERS
        or tier == "elite"
        or any(term in lower for term in HIGH_TERMS)
        or any(term in lower for term in SPINE_TERMS)
    ):
        return "HIGH"
    if tier == "key" or any(term in lower for term in MEDIUM_TERMS):
        return "MEDIUM"
    return "LOW"


def return_round_from_text(text: str) -> int | None:
    match = re.search(r"\bRound\s+(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def is_current_judiciary_item(text: str, current_round: int) -> bool:
    charge_round = return_round_from_text(text)
    if charge_round is None:
        return False
    return current_round - 1 <= charge_round <= current_round


def is_current_market_relevant(text: str, player: str, current_round: int) -> bool:
    lower = text.lower()
    if player in MARKET_KEY_PLAYERS:
        return True
    if "tbc" in lower or "indefinite" in lower or "surgery" in lower or "cat 1" in lower or "category 1" in lower:
        return True
    return_round = return_round_from_text(text)
    if return_round is None:
        return True
    return current_round <= return_round <= current_round + 2


def load_fixture_games() -> list[dict]:
    if not FIXTURE_PATH.exists():
        return []
    try:
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        return data.get("games", [])
    except Exception:
        return []


def next_game_for(team: str, games: list[dict]) -> dict:
    for game in games:
        if game.get("home_team") == team:
            return {
                "next_game": f"{game.get('home_team')} v {game.get('away_team')}",
                "opponent": game.get("away_team", ""),
                "kickoff_local": game.get("kickoff_local", ""),
            }
        if game.get("away_team") == team:
            return {
                "next_game": f"{game.get('home_team')} v {game.get('away_team')}",
                "opponent": game.get("home_team", ""),
                "kickoff_local": game.get("kickoff_local", ""),
            }
    return {"next_game": "", "opponent": "", "kickoff_local": ""}


def market_note(flag: dict) -> str:
    team = flag["team"]
    flag_type = flag["flag_type"].lower()
    player = flag.get("player") or "player"
    next_game = flag.get("next_game") or "next game"
    return f"{team} negative {flag_type} flag: {player}. Watch {next_game} odds."


def make_flag(
    *,
    season: int,
    round_number: int,
    team: str,
    player: str,
    excerpt: str,
    source: Source,
    known_players: dict[str, str],
    fixture_games: list[dict],
    detected_at: str,
) -> dict:
    game = next_game_for(team, fixture_games)
    flag = {
        "detected_at": detected_at,
        "season": season,
        "round": round_number,
        "team": team,
        "player": player,
        "severity": severity_for(excerpt, player, known_players),
        "flag_type": classify_flag(excerpt),
        "reason": clean_text(excerpt)[:260],
        "source_name": source.name,
        "source_url": source.url,
        **game,
    }
    flag["market_note"] = market_note(flag)
    return flag


def extract_generic_flags(
    html: str,
    source: Source,
    season: int,
    round_number: int,
    known_players: dict[str, str],
    fixture_games: list[dict],
    detected_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    flags = []
    for chunk in text_chunks(soup):
        if not contains_flag(chunk):
            continue
        teams = infer_teams(chunk, source.team)
        if not teams:
            continue
        player = infer_player(chunk, known_players)
        if not is_current_market_relevant(chunk, player, round_number):
            continue
        for team in teams:
            flags.append(make_flag(
                season=season,
                round_number=round_number,
                team=team,
                player=player,
                excerpt=chunk,
                source=source,
                known_players=known_players,
                fixture_games=fixture_games,
                detected_at=detected_at,
            ))
    return flags


def extract_casualty_flags(
    html: str,
    source: Source,
    season: int,
    round_number: int,
    known_players: dict[str, str],
    fixture_games: list[dict],
    detected_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    flags = []
    current_team: str | None = None

    for element in soup.find_all(["h2", "h3", "h4", "li"]):
        if element.name in ("h2", "h3", "h4"):
            text = clean_text(element.get_text(" "))
            teams = infer_teams(text)
            current_team = teams[0] if len(teams) == 1 else None
            continue

        if element.name == "li" and current_team:
            text = clean_text(element.get_text(" "))
            if not contains_flag(text):
                continue
            player = infer_player(text, known_players)
            if not is_current_market_relevant(text, player, round_number):
                continue
            flags.append(make_flag(
                season=season,
                round_number=round_number,
                team=current_team,
                player=player,
                excerpt=text,
                source=source,
                known_players=known_players,
                fixture_games=fixture_games,
                detected_at=detected_at,
            ))

    return flags


def extract_team_section_flags(
    html: str,
    source: Source,
    season: int,
    round_number: int,
    known_players: dict[str, str],
    fixture_games: list[dict],
    detected_at: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    flags = []
    current_team: str | None = None

    for element in soup.find_all(["h2", "h3", "h4", "li", "tr"]):
        if element.name in ("h2", "h3", "h4"):
            text = clean_text(element.get_text(" "))
            teams = infer_teams(text)
            current_team = teams[0] if len(teams) == 1 else None
            continue

        if not current_team:
            continue

        text = clean_text(element.get_text(" "))
        if not contains_flag(text):
            continue
        if source.name == "NRL Judiciary Report" and not is_current_judiciary_item(text, round_number):
            continue
        player = infer_player(text, known_players)
        if not is_current_market_relevant(text, player, round_number):
            continue
        flags.append(make_flag(
            season=season,
            round_number=round_number,
            team=current_team,
            player=player,
            excerpt=text,
            source=source,
            known_players=known_players,
            fixture_games=fixture_games,
            detected_at=detected_at,
        ))

    return flags


def dedupe_flags(flags: Iterable[dict]) -> list[dict]:
    seen = set()
    output = []
    severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    sorted_flags = sorted(flags, key=lambda f: severity_rank.get(f.get("severity", "LOW"), 2))

    for flag in sorted_flags:
        key = (
            flag.get("team"),
            flag.get("player"),
            flag.get("flag_type"),
            flag.get("source_url"),
            flag.get("reason", "")[:90].lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(flag)
    return output


def sources_for(season: int) -> list[Source]:
    sources = [
        Source("NRL Casualty Ward", nrl_casualty_url(season)),
        Source("NRL Judiciary Report", nrl_judiciary_url(season)),
        Source("NRL News", "https://www.nrl.com/news/"),
    ]
    sources.extend(Source(f"{team} News", url, team) for team, url in CLUB_NEWS_URLS.items())
    return sources


def write_outputs(flags: list[dict], raw_sources: list[dict], season: int, run_date: str) -> None:
    raw_dir = RAW_DIR / str(season)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{run_date}.json").write_text(
        json.dumps(raw_sources, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    proc_dir = PROCESSED_DIR / str(season)
    proc_dir.mkdir(parents=True, exist_ok=True)
    json_path = proc_dir / f"{run_date}.json"
    csv_path = proc_dir / f"{run_date}.csv"

    json_path.write_text(json.dumps(flags, indent=2, ensure_ascii=False), encoding="utf-8")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    (PROCESSED_DIR / "latest.json").write_text(json.dumps(flags, indent=2, ensure_ascii=False), encoding="utf-8")

    fieldnames = [
        "detected_at", "season", "round", "team", "player", "severity", "flag_type",
        "reason", "source_name", "source_url", "next_game", "opponent",
        "kickoff_local", "market_note",
    ]
    for path in (csv_path, PROCESSED_DIR / "latest.csv"):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flags)

    log.info("Wrote %d flags", len(flags))
    log.info("JSON: %s", json_path)
    log.info("CSV:  %s", csv_path)


def scrape(season: int, round_number: int) -> list[dict]:
    known_players = load_injury_players()
    fixture_games = load_fixture_games()
    detected_at = datetime.now(timezone.utc).isoformat()
    flags: list[dict] = []
    raw_sources: list[dict] = []

    for source in sources_for(season):
        html = fetch_html(source)
        raw_sources.append({
            "name": source.name,
            "url": source.url,
            "team": source.team,
            "fetched": html is not None,
            "raw_length": len(html or ""),
        })
        if not html:
            continue

        if source.name == "NRL Casualty Ward":
            flags.extend(extract_casualty_flags(
                html, source, season, round_number, known_players, fixture_games, detected_at
            ))
        elif source.name == "NRL Judiciary Report":
            flags.extend(extract_team_section_flags(
                html, source, season, round_number, known_players, fixture_games, detected_at
            ))
        else:
            flags.extend(extract_generic_flags(
                html, source, season, round_number, known_players, fixture_games, detected_at
            ))
        time.sleep(0.3)

    run_date = datetime.now().strftime("%Y-%m-%d")
    clean_flags = dedupe_flags(flags)
    write_outputs(clean_flags, raw_sources, season, run_date)
    return clean_flags


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Scan NRL sources for market-moving news flags")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--round", dest="round_number", type=int, default=0)
    parser.add_argument("--round-one-monday", default=DEFAULT_ROUND_ONE_MONDAY)
    args = parser.parse_args()

    round_number = args.round_number or infer_round(args.round_one_monday)
    log.info("Targeting season=%d round=%d", args.season, round_number)
    flags = scrape(args.season, round_number)

    high_count = sum(1 for flag in flags if flag.get("severity") == "HIGH")
    log.info("News flags complete -- %d total, %d HIGH", len(flags), high_count)
    sys.exit(0)


if __name__ == "__main__":
    main()
