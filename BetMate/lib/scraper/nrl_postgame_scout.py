"""
lib/scraper/nrl_postgame_scout.py

Scout v1: post-game NRL intelligence scan.

Runs after games and stores material post-game signals:
  - late withdrawals / team-list changes
  - injuries / illness / HIA / did-not-return language
  - sin bins and judiciary-watch incidents
  - confirmed judiciary/casualty-ward signals from official NRL pages

The script is safe to run repeatedly. It only processes games whose kickoff is
at least --scan-delay-hours after kickoff. The default is 3 hours, which is a
practical "about one hour after full time" proxy for NRL.

Outputs:
  data/nrl/scout/postgame/raw/YYYY/round-N-SLUG.json
  data/nrl/scout/postgame/processed/YYYY/round-N-SLUG.json
  data/nrl/scout/postgame/processed/latest.json
  data/nrl/scout/postgame/logs/scrape.log

Usage:
  uv run --with requests --with beautifulsoup4 python lib/scraper/nrl_postgame_scout.py --season 2026 --round 10
  uv run --with requests --with beautifulsoup4 python lib/scraper/nrl_postgame_scout.py --season 2026 --round 10 --game "Dolphins v Bulldogs" --force
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = ROOT / "data" / "nrl" / "scout" / "postgame"
RAW_DIR = BASE_DIR / "raw"
PROCESSED_DIR = BASE_DIR / "processed"
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "scrape.log"
FIXTURE_DIR = ROOT / "data" / "nrl" / "fixture" / "processed"

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY = 20
DEFAULT_ROUND_ONE_MONDAY = "2026-03-02"

NRL_DRAW_API = "https://www.nrl.com/draw/data/?competition=111&season={season}&round={round}"
NRL_TEAM_LISTS_URL = "https://www.nrl.com/news/{season}/05/05/nrl-team-lists-round-{round}/"
NRL_JUDICIARY_URL = "https://www.nrl.com/news/{season}/01/01/nrl-judiciary-report-{season}/"
NRL_CASUALTY_URL = (
    "https://www.nrl.com/news/{season}/01/01/"
    "nrl-casualty-ward-how-your-club-is-shaping-heading-into-{season}/"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

TEAM_ALIASES = {
    "Brisbane Broncos": ["broncos", "brisbane"],
    "Canterbury-Bankstown Bulldogs": ["bulldogs", "canterbury", "canterbury-bankstown"],
    "Canberra Raiders": ["raiders", "canberra"],
    "Cronulla-Sutherland Sharks": ["sharks", "cronulla", "cronulla sharks", "cronulla-sutherland"],
    "Dolphins": ["dolphins"],
    "Gold Coast Titans": ["titans", "gold coast"],
    "Manly-Warringah Sea Eagles": ["sea eagles", "manly", "manly-warringah"],
    "Melbourne Storm": ["storm", "melbourne"],
    "Newcastle Knights": ["knights", "newcastle"],
    "New Zealand Warriors": ["warriors", "new zealand"],
    "North Queensland Cowboys": ["cowboys", "north queensland"],
    "Parramatta Eels": ["eels", "parramatta"],
    "Penrith Panthers": ["panthers", "penrith"],
    "South Sydney Rabbitohs": ["rabbitohs", "south sydney", "souths"],
    "St. George Illawarra Dragons": ["dragons", "st george", "st. george"],
    "Sydney Roosters": ["roosters", "sydney roosters"],
    "Wests Tigers": ["wests tigers", "tigers"],
}

TEAM_SHORT = {
    "Brisbane Broncos": "Broncos",
    "Canterbury-Bankstown Bulldogs": "Bulldogs",
    "Canberra Raiders": "Raiders",
    "Cronulla-Sutherland Sharks": "Sharks",
    "Dolphins": "Dolphins",
    "Gold Coast Titans": "Titans",
    "Manly-Warringah Sea Eagles": "Sea Eagles",
    "Melbourne Storm": "Storm",
    "Newcastle Knights": "Knights",
    "New Zealand Warriors": "Warriors",
    "North Queensland Cowboys": "Cowboys",
    "Parramatta Eels": "Eels",
    "Penrith Panthers": "Panthers",
    "South Sydney Rabbitohs": "Rabbitohs",
    "St. George Illawarra Dragons": "Dragons",
    "Sydney Roosters": "Roosters",
    "Wests Tigers": "Wests Tigers",
}

MAJOR_TERMS = [
    "late withdrawal",
    "ruled out",
    "withdrawal",
    "failed hia",
    "category 1",
    "cat 1",
    "did not return",
    "surgery",
    "suspended",
    "suspension",
    "facing ban",
    "accepted a one-week suspension",
    "accepted a two-week suspension",
]

WATCH_TERMS = [
    "sin bin",
    "sent to the sin bin",
    "late tackle",
    "high tackle",
    "dangerous contact",
    "careless high tackle",
    "head knock",
    "hia",
    "illness",
    "biceps",
    "knee",
    "shoulder",
    "ankle",
    "scans",
    "omitted",
    "drops out",
    "dropped out",
    "return from suspension",
    "return from a knee injury",
]

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
    today = datetime.now().date()
    if today < monday:
        return 1
    return (today - monday).days // 7 + 1


def slugify(text: str) -> str:
    text = text.lower().replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def clean_text(text: str) -> str:
    text = text.replace("\\n", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def team_short(team: str) -> str:
    return TEAM_SHORT.get(team, team)


def game_label(game: dict) -> str:
    return f"{team_short(game['home_team'])} v {team_short(game['away_team'])}"


def source_fetch(url: str, expect_json: bool = False) -> tuple[object | None, str]:
    for attempt in range(1, DEFAULT_MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            return (resp.json() if expect_json else resp.text), resp.url
        except Exception as exc:
            log.warning("Fetch failed attempt %d/%d %s -- %s", attempt, DEFAULT_MAX_ATTEMPTS, url, exc)
            if attempt < DEFAULT_MAX_ATTEMPTS:
                time.sleep(DEFAULT_RETRY_DELAY)
    return None, url


def html_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = []
    for raw in soup.get_text("\n").splitlines():
        line = clean_text(raw)
        if len(line) < 4:
            continue
        if line.lower() in {"main", "cancel", "replay", "play next"}:
            continue
        lines.append(line)
    return lines


def line_has_team(line: str, teams: Iterable[str]) -> bool:
    lower = line.lower()
    for team in teams:
        aliases = TEAM_ALIASES.get(team, [team.lower()])
        if any(re.search(rf"\b{re.escape(alias)}\b", lower) for alias in aliases):
            return True
    return False


def line_has_signal(line: str) -> bool:
    lower = line.lower()
    return any(term in lower for term in MAJOR_TERMS + WATCH_TERMS)


def signal_severity(line: str) -> str:
    lower = line.lower()
    if any(term in lower for term in MAJOR_TERMS):
        return "major"
    return "watch"


def signal_type(line: str) -> str:
    lower = line.lower()
    if any(term in lower for term in ["late withdrawal", "illness", "ruled out", "omitted", "drops out", "dropped out"]):
        return "team_availability"
    if any(term in lower for term in ["sin bin", "late tackle", "high tackle", "dangerous contact", "careless high tackle"]):
        return "judiciary_watch"
    if any(term in lower for term in ["hia", "head knock", "knee", "shoulder", "ankle", "biceps", "scans", "did not return"]):
        return "injury_watch"
    if "suspension" in lower or "suspended" in lower:
        return "suspension"
    return "watch"


def confidence_for(source_name: str, line: str) -> str:
    lower = line.lower()
    if source_name.startswith("nrl_") and any(term in lower for term in MAJOR_TERMS):
        return "verified"
    if source_name.startswith("nrl_"):
        return "watch_pending"
    return "unverified"


def source_signal(source_name: str, url: str, line: str, teams: list[str]) -> dict:
    matched_teams = teams_for_line(line, teams)
    return {
        "severity": signal_severity(line),
        "type": signal_type(line),
        "status": confidence_for(source_name, line),
        "text": line,
        "teams": matched_teams or teams,
        "source": {
            "name": source_name,
            "url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def teams_for_line(line: str, teams: list[str]) -> list[str]:
    lower = line.lower()
    matched = []
    for team in teams:
        short = team_short(team).lower()
        if re.match(rf"^{re.escape(short)}\s*:", lower):
            return [team]
        aliases = TEAM_ALIASES.get(team, [team.lower()])
        if any(re.search(rf"\b{re.escape(alias)}\b", lower) for alias in aliases):
            matched.append(team)
    return matched


def dedupe_signals(signals: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for sig in signals:
        key = (sig["type"], sig["text"].lower()[:180], tuple(sig.get("teams", [])))
        if key in seen:
            continue
        seen.add(key)
        out.append(sig)
    order = {"major": 0, "watch": 1}
    return sorted(out, key=lambda s: (order.get(s["severity"], 9), s["type"], s["text"]))


def find_game_window(lines: list[str], game: dict, window: int = 180) -> list[str]:
    labels = [
        f"{team_short(game['home_team'])} v {team_short(game['away_team'])}".lower(),
        f"{team_short(game['home_team'])} vs {team_short(game['away_team'])}".lower(),
        f"{game['home_team']} v {game['away_team']}".lower(),
        f"{game['home_team']} vs {game['away_team']}".lower(),
    ]
    for i, line in enumerate(lines):
        lower = line.lower()
        if any(label in lower for label in labels):
            return lines[i : i + window]
    return lines


def team_section_lines(lines: list[str], teams: list[str]) -> list[str]:
    """Return lines from explicit team sections when a page is structured by club."""
    all_headings: dict[str, str] = {}
    for team, aliases in TEAM_ALIASES.items():
        all_headings[team.lower()] = team
        all_headings[team_short(team).lower()] = team
        for alias in aliases:
            all_headings[alias.lower()] = team

    wanted = set()
    for team in teams:
        wanted.add(team.lower())
        wanted.add(team_short(team).lower())
        wanted.update(alias.lower() for alias in TEAM_ALIASES.get(team, []))

    out: list[str] = []
    active_team: str | None = None
    for line in lines:
        norm = line.lower().strip(" :")
        if norm in all_headings:
            active_team = all_headings[norm] if norm in wanted else None
            if active_team:
                out.append(line)
            continue
        if active_team:
            out.append(f"{team_short(active_team)}: {line}")
    return out or lines


def extract_text_signals(
    source_name: str,
    url: str,
    lines: list[str],
    teams: list[str],
    require_team: bool = True,
) -> list[dict]:
    signals = []
    for line in lines:
        if not line_has_signal(line):
            continue
        if require_team and not line_has_team(line, teams):
            continue
        signals.append(source_signal(source_name, url, line, teams))
    return signals


def draw_game_from_api(raw_game: dict, season: int, round_number: int) -> dict | None:
    if raw_game.get("type") != "Match":
        return None
    home = raw_game.get("homeTeam", {})
    away = raw_game.get("awayTeam", {})
    home_team = canon_team(home.get("nickName", ""))
    away_team = canon_team(away.get("nickName", ""))
    kickoff_utc = raw_game.get("clock", {}).get("kickOffTimeLong", "")
    if not home_team or not away_team or not kickoff_utc:
        return None
    try:
        dt = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    except Exception:
        dt = None
    return {
        "season": season,
        "round": round_number,
        "home_team": home_team,
        "away_team": away_team,
        "venue": raw_game.get("venue", ""),
        "kickoff_utc": kickoff_utc,
        "kickoff_dt": dt,
        "match_state": raw_game.get("matchState", ""),
        "match_mode": raw_game.get("matchMode", ""),
        "home_score": home.get("score"),
        "away_score": away.get("score"),
        "match_centre_url": "https://www.nrl.com" + raw_game.get("matchCentreUrl", ""),
        "raw": raw_game,
    }


def canon_team(raw: str) -> str:
    raw = raw.strip()
    for team, aliases in TEAM_ALIASES.items():
        if raw.lower() == team.lower() or raw.lower() in aliases:
            return team
    return raw


def load_draw_games(season: int, round_number: int) -> tuple[list[dict], dict]:
    url = NRL_DRAW_API.format(season=season, round=round_number)
    raw, final_url = source_fetch(url, expect_json=True)
    if not isinstance(raw, dict):
        # Fallback to latest local fixture if the live API is unavailable.
        path = FIXTURE_DIR / str(season) / f"round-{round_number}-fixture.json"
        if not path.exists():
            return [], {"source_url": final_url, "error": "draw_fetch_failed"}
        fixture = json.loads(path.read_text(encoding="utf-8"))
        games = []
        for g in fixture.get("games", []):
            item = dict(g)
            item["kickoff_dt"] = datetime.fromisoformat(item["kickoff_utc"].replace("Z", "+00:00"))
            item["match_state"] = "unknown"
            item["match_mode"] = "unknown"
            item["home_score"] = None
            item["away_score"] = None
            item["match_centre_url"] = ""
            item["raw"] = {}
            games.append(item)
        return games, {"source_url": str(path), "fallback": True}
    games = [g for g in (draw_game_from_api(f, season, round_number) for f in raw.get("fixtures", [])) if g]
    return games, {"source_url": final_url, "raw": raw}


def eligible_games(games: list[dict], game_filter: str | None, scan_delay_hours: float, force: bool) -> list[dict]:
    now = datetime.now(timezone.utc)
    out = []
    for game in games:
        label = game_label(game)
        if game_filter and game_filter.lower() not in label.lower():
            continue
        kickoff = game.get("kickoff_dt")
        if force or game.get("match_state") == "FullTime":
            if force or not kickoff or now >= kickoff + timedelta(hours=scan_delay_hours):
                out.append(game)
    return out


def scout_game(game: dict, season: int, round_number: int) -> tuple[dict, dict]:
    teams = [game["home_team"], game["away_team"]]
    label = game_label(game)
    log.info("Scout scan: %s", label)

    sources: dict[str, dict] = {}
    all_signals: list[dict] = []

    team_lists_url = NRL_TEAM_LISTS_URL.format(season=season, round=round_number)
    html, final_url = source_fetch(team_lists_url)
    if isinstance(html, str):
        lines = find_game_window(html_lines(html), game)
        sources["nrl_team_lists"] = {"url": final_url, "line_count": len(lines)}
        all_signals.extend(extract_text_signals("nrl_team_lists", final_url, lines, teams, require_team=False))

    match_html, final_match_url = source_fetch(game.get("match_centre_url", ""))
    if isinstance(match_html, str):
        lines = html_lines(match_html)
        sources["nrl_match_centre"] = {"url": final_match_url, "line_count": len(lines)}
        all_signals.extend(extract_text_signals("nrl_match_centre", final_match_url, lines, teams, require_team=False))

    judiciary_url = NRL_JUDICIARY_URL.format(season=season)
    html, final_url = source_fetch(judiciary_url)
    if isinstance(html, str):
        lines = html_lines(html)
        sources["nrl_judiciary"] = {"url": final_url, "line_count": len(lines)}
        all_signals.extend(extract_text_signals("nrl_judiciary", final_url, lines, teams, require_team=True))

    casualty_url = NRL_CASUALTY_URL.format(season=season)
    html, final_url = source_fetch(casualty_url)
    if isinstance(html, str):
        lines = team_section_lines(html_lines(html), teams)
        sources["nrl_casualty_ward"] = {"url": final_url, "line_count": len(lines)}
        all_signals.extend(extract_text_signals("nrl_casualty_ward", final_url, lines, teams, require_team=False))

    signals = dedupe_signals(all_signals)
    major = [s for s in signals if s["severity"] == "major"]
    watch = [s for s in signals if s["severity"] == "watch"]

    if major:
        verdict = "major_signals_found"
    elif watch:
        verdict = "watch_signals_found"
    else:
        verdict = "no_material_signals_found"

    payload = {
        "schema_version": 1,
        "agent": "Scout",
        "scan_type": "nrl_postgame",
        "season": season,
        "round": round_number,
        "game": {
            "label": label,
            "home_team": game["home_team"],
            "away_team": game["away_team"],
            "venue": game.get("venue", ""),
            "kickoff_utc": game.get("kickoff_utc", ""),
            "match_state": game.get("match_state", ""),
            "match_mode": game.get("match_mode", ""),
            "score": {
                "home": game.get("home_score"),
                "away": game.get("away_score"),
            },
            "match_centre_url": game.get("match_centre_url", ""),
        },
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "counts": {
            "major": len(major),
            "watch": len(watch),
            "total": len(signals),
        },
        "signals": signals,
        "sources": sources,
        "engine_policy": {
            "model_safe_without_auditor": False,
            "allowed_for_public_summary": True,
            "notes": "Scout flags require Auditor confirmation before engine use.",
        },
    }
    raw_bundle = {
        "draw_game": game.get("raw", {}),
        "sources": sources,
    }
    return payload, raw_bundle


def write_game_outputs(payload: dict, raw_bundle: dict) -> Path:
    season = payload["season"]
    round_number = payload["round"]
    slug = slugify(payload["game"]["label"])

    raw_dir = RAW_DIR / str(season)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"round-{round_number}-{slug}.json"
    raw_path.write_text(json.dumps(raw_bundle, indent=2, ensure_ascii=False), encoding="utf-8")

    proc_dir = PROCESSED_DIR / str(season)
    proc_dir.mkdir(parents=True, exist_ok=True)
    out_path = proc_dir / f"round-{round_number}-{slug}.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    (PROCESSED_DIR / "latest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def run(season: int, round_number: int, game_filter: str | None, scan_delay_hours: float, force: bool) -> int:
    games, draw_meta = load_draw_games(season, round_number)
    selected = eligible_games(games, game_filter, scan_delay_hours, force)
    if not selected:
        log.info(
            "No eligible games for Scout scan. season=%s round=%s game_filter=%s delay=%s source=%s",
            season,
            round_number,
            game_filter,
            scan_delay_hours,
            draw_meta.get("source_url"),
        )
        return 0

    written = []
    for game in selected:
        payload, raw_bundle = scout_game(game, season, round_number)
        raw_bundle["draw_meta"] = draw_meta
        out_path = write_game_outputs(payload, raw_bundle)
        written.append(str(out_path))
        log.info("Wrote Scout report: %s", out_path)

    latest_index = {
        "season": season,
        "round": round_number,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "reports_written": written,
    }
    (PROCESSED_DIR / "latest-index.json").write_text(
        json.dumps(latest_index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="NRL post-game Scout scan")
    parser.add_argument("--season", type=int, default=datetime.now().year)
    parser.add_argument("--round", type=int, default=None, dest="round_number")
    parser.add_argument("--game", type=str, default=None, help='Optional filter, e.g. "Dolphins v Bulldogs"')
    parser.add_argument("--scan-delay-hours", type=float, default=3.0)
    parser.add_argument("--force", action="store_true", help="Scan even if the delay window has not elapsed")
    parser.add_argument("--round-one-monday", default=DEFAULT_ROUND_ONE_MONDAY)
    args = parser.parse_args()

    setup_logging()
    round_number = args.round_number or infer_round(args.round_one_monday)
    return run(args.season, round_number, args.game, args.scan_delay_hours, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
