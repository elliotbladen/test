"""
Weekly NRL style-stat scraper.

This stores the T2 inputs BetMate will later expose to BettingEngine.
Set NRL_STYLE_STATS_URL once the source website is chosen.

Outputs:
  data/nrl/style-stats/raw/YYYY/round-N.json
  data/nrl/style-stats/processed/YYYY/round-N-style-stats.csv
  data/nrl/style-stats/processed/latest-style-stats.csv
  data/nrl/style-stats/logs/scrape.log
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = ROOT / "data" / "nrl" / "style-stats"
RAW_DIR = BASE_DIR / "raw"
PROCESSED_DIR = BASE_DIR / "processed"
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "scrape.log"

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_RETRY_DELAY_SECONDS = 600
DEFAULT_ROUND_ONE_MONDAY = "2026-03-02"
FOX_BASE_URL = "https://www.foxsports.com.au/nrl/nrl-premiership/stats/teams"
FOX_CATEGORIES = ("attack", "kicking", "defenceAndDiscipline")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

FIELDNAMES = [
    "team",
    "season",
    "round",
    "as_of_date",
    "completion_rate",
    "kick_metres_pg",
    "errors_pg",
    "penalties_pg",
    "line_breaks_pg",
    "tackle_breaks_pg",
    "missed_tackles_pg",
    "line_breaks_conceded_pg",
    "run_metres_pg",
    "forced_dropouts_pg",
    "kick_return_metres_pg",
    "source_url",
    "scraped_at",
]

ALIASES = {
    "completion rate": "completion_rate",
    "completion %": "completion_rate",
    "completion": "completion_rate",
    "kick metres": "kick_metres_pg",
    "kick metres pg": "kick_metres_pg",
    "kick metres per game": "kick_metres_pg",
    "errors": "errors_pg",
    "errors pg": "errors_pg",
    "errors per game": "errors_pg",
    "penalties": "penalties_pg",
    "penalties pg": "penalties_pg",
    "penalties per game": "penalties_pg",
    "line breaks": "line_breaks_pg",
    "line breaks pg": "line_breaks_pg",
    "line breaks per game": "line_breaks_pg",
    "tackle breaks": "tackle_breaks_pg",
    "tackle breaks pg": "tackle_breaks_pg",
    "tackle breaks per game": "tackle_breaks_pg",
    "missed tackles": "missed_tackles_pg",
    "missed tackles pg": "missed_tackles_pg",
    "missed tackles per game": "missed_tackles_pg",
    "line breaks conceded": "line_breaks_conceded_pg",
    "line breaks conceded pg": "line_breaks_conceded_pg",
    "line breaks conceded per game": "line_breaks_conceded_pg",
    "run metres": "run_metres_pg",
    "run metres pg": "run_metres_pg",
    "run metres per game": "run_metres_pg",
    "forced dropouts": "forced_dropouts_pg",
    "forced dropouts pg": "forced_dropouts_pg",
    "forced dropouts per game": "forced_dropouts_pg",
    "kick return metres": "kick_return_metres_pg",
    "kick return metres pg": "kick_return_metres_pg",
    "kick return metres per game": "kick_return_metres_pg",
}

TEAM_ALIASES = {
    "broncos": "Brisbane Broncos",
    "bulldogs": "Canterbury-Bankstown Bulldogs",
    "canterbury bulldogs": "Canterbury-Bankstown Bulldogs",
    "canterbury-bankstown bulldogs": "Canterbury-Bankstown Bulldogs",
    "canberra raiders": "Canberra Raiders",
    "raiders": "Canberra Raiders",
    "cowboys": "North Queensland Cowboys",
    "north qld cowboys": "North Queensland Cowboys",
    "north queensland cowboys": "North Queensland Cowboys",
    "dolphins": "Dolphins",
    "dragons": "St George Illawarra Dragons",
    "st george dragons": "St George Illawarra Dragons",
    "eels": "Parramatta Eels",
    "knights": "Newcastle Knights",
    "panthers": "Penrith Panthers",
    "rabbitohs": "South Sydney Rabbitohs",
    "roosters": "Sydney Roosters",
    "sea eagles": "Manly-Warringah Sea Eagles",
    "sharks": "Cronulla-Sutherland Sharks",
    "cronulla sharks": "Cronulla-Sutherland Sharks",
    "cronulla-sutherland sharks": "Cronulla-Sutherland Sharks",
    "storm": "Melbourne Storm",
    "tigers": "Wests Tigers",
    "titans": "Gold Coast Titans",
    "manly sea eagles": "Manly-Warringah Sea Eagles",
    "manly-warringah sea eagles": "Manly-Warringah Sea Eagles",
    "warriors": "New Zealand Warriors",
}

FOX_FIELD_MAP = {
    "attack": {
        "RM": "run_metres_pg",
        "LB": "line_breaks_pg",
        "TB": "tackle_breaks_pg",
        "CR%": "completion_rate",
        "KRM": "kick_return_metres_pg",
    },
    "kicking": {
        "KM": "kick_metres_pg",
        "FDO": "forced_dropouts_pg",
    },
    "defenceAndDiscipline": {
        "ERR": "errors_pg",
        "PC": "penalties_pg",
        "LBC": "line_breaks_conceded_pg",
        "MT": "missed_tackles_pg",
    },
}


@dataclass
class StyleRow:
    team: str
    season: int
    round: int
    as_of_date: str
    completion_rate: float | None = None
    kick_metres_pg: float | None = None
    errors_pg: float | None = None
    penalties_pg: float | None = None
    line_breaks_pg: float | None = None
    tackle_breaks_pg: float | None = None
    missed_tackles_pg: float | None = None
    line_breaks_conceded_pg: float | None = None
    run_metres_pg: float | None = None
    forced_dropouts_pg: float | None = None
    kick_return_metres_pg: float | None = None
    source_url: str = ""
    scraped_at: str = ""


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
    )


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def normalise_key(value: str) -> str:
    value = re.sub(r"[^a-z0-9%]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", value)


def normalise_team(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return TEAM_ALIASES.get(value.lower(), value)


def parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().replace(",", "")
    if not text or text in {"-", "--", "na", "n/a"}:
        return None
    pct = text.endswith("%")
    text = text.rstrip("%")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    num = float(match.group(0))
    return round(num / 100.0, 4) if pct else num


def parse_stat_value(field: str, value: str | None) -> float | None:
    num = parse_number(value)
    if num is None:
        return None
    if field == "completion_rate" and num > 1.0:
        return round(num / 100.0, 4)
    return num


def canonical_column(header: str) -> str | None:
    key = normalise_key(header)
    if key in {"team", "teams", "club"}:
        return "team"
    return ALIASES.get(key)


def fetch_html(url: str, timeout: int) -> str:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def fox_url(category: str) -> str:
    return (
        f"{FOX_BASE_URL}?editiondata=none&fromakamai=true&pt=none"
        f"&device=DESKTOP&isAvg=true&category={category}"
    )


def expand_source_urls(raw_url: str | None) -> list[str]:
    if raw_url:
        parts = re.split(r"[\s,]+", raw_url.strip())
        return [part for part in parts if part]
    return [fox_url(category) for category in FOX_CATEGORIES]


def category_from_url(url: str) -> str | None:
    match = re.search(r"[?&]category=([^&]+)", url)
    return match.group(1) if match else None


def extract_table_rows(html: str, source_url: str, season: int, round_number: int, as_of_date: str) -> list[StyleRow]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[StyleRow] = []

    for table in soup.find_all("table"):
        parsed = parse_table(table, source_url, season, round_number, as_of_date)
        if parsed:
            rows.extend(parsed)

    if not rows:
        category = category_from_url(source_url)
        if category in FOX_FIELD_MAP:
            rows.extend(parse_fox_text_table(soup, category, source_url, season, round_number, as_of_date))

    return dedupe_rows(rows)


def parse_fox_text_table(
    soup: BeautifulSoup,
    category: str,
    source_url: str,
    season: int,
    round_number: int,
    as_of_date: str,
) -> list[StyleRow]:
    lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
    start = next((i for i, line in enumerate(lines) if line.startswith("Top series teams")), -1)
    if start < 0:
        return []

    name_idx = next((i for i in range(start, min(start + 30, len(lines))) if lines[i] == "Name"), -1)
    first_rank_idx = next((i for i in range(name_idx + 1, min(name_idx + 40, len(lines))) if lines[i] == "1"), -1)
    if name_idx < 0 or first_rank_idx < 0:
        return []

    stat_codes = lines[name_idx + 1:first_rank_idx]
    field_map = FOX_FIELD_MAP[category]
    wanted_indexes = {idx: field_map[code] for idx, code in enumerate(stat_codes) if code in field_map}
    if not wanted_indexes:
        return []

    rows: list[StyleRow] = []
    scraped_at = datetime.now(timezone.utc).isoformat()
    i = first_rank_idx
    while i < len(lines):
        if not lines[i].isdigit():
            break
        rank = int(lines[i])
        if rank < 1 or rank > 25:
            break
        if i + 1 >= len(lines):
            break

        team = normalise_team(lines[i + 1])
        values = lines[i + 2:i + 2 + len(stat_codes)]
        if len(values) < len(stat_codes):
            break

        record = StyleRow(
            team=team,
            season=season,
            round=round_number,
            as_of_date=as_of_date,
            source_url=source_url,
            scraped_at=scraped_at,
        )
        for idx, field in wanted_indexes.items():
            setattr(record, field, parse_stat_value(field, values[idx]))
        rows.append(record)
        i += 2 + len(stat_codes)

    return rows


def parse_table(table, source_url: str, season: int, round_number: int, as_of_date: str) -> list[StyleRow]:
    header_cells = table.select("thead tr th")
    if not header_cells:
        first_row = table.find("tr")
        header_cells = first_row.find_all(["th", "td"]) if first_row else []

    headers = [canonical_column(cell.get_text(" ", strip=True)) for cell in header_cells]
    if "team" not in headers:
        return []

    wanted = {name for name in headers if name in FIELDNAMES}
    if len(wanted - {"team"}) < 2:
        return []

    parsed: list[StyleRow] = []
    body_rows = table.select("tbody tr") or table.find_all("tr")[1:]
    scraped_at = datetime.now(timezone.utc).isoformat()

    for row in body_rows:
        cells = row.find_all(["th", "td"])
        if len(cells) < len(headers):
            continue

        values = [cell.get_text(" ", strip=True) for cell in cells[: len(headers)]]
        by_col = {headers[i]: values[i] for i in range(len(headers)) if headers[i]}
        team = by_col.get("team")
        if not team:
            continue

        record = StyleRow(
            team=normalise_team(team),
            season=season,
            round=round_number,
            as_of_date=as_of_date,
            source_url=source_url,
            scraped_at=scraped_at,
        )
        for field in FIELDNAMES:
            if field in {"team", "season", "round", "as_of_date", "source_url", "scraped_at"}:
                continue
            if field in by_col:
                setattr(record, field, parse_number(by_col[field]))
        parsed.append(record)

    return parsed


def dedupe_rows(rows: Iterable[StyleRow]) -> list[StyleRow]:
    merged: dict[str, StyleRow] = {}
    for row in rows:
        current = merged.get(row.team)
        if current is None:
            merged[row.team] = row
            continue
        if row.source_url and row.source_url not in current.source_url.split("|"):
            current.source_url = f"{current.source_url}|{row.source_url}" if current.source_url else row.source_url
        for field in FIELDNAMES:
            if field in {"team", "season", "round", "as_of_date", "source_url", "scraped_at"}:
                continue
            if getattr(current, field) is None and getattr(row, field) is not None:
                setattr(current, field, getattr(row, field))
    return sorted(merged.values(), key=lambda r: r.team)


def write_outputs(rows: list[StyleRow], raw_pages: list[dict], season: int, round_number: int) -> None:
    RAW_DIR.joinpath(str(season)).mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.joinpath(str(season)).mkdir(parents=True, exist_ok=True)

    raw_path = RAW_DIR / str(season) / f"round-{round_number}.json"
    processed_path = PROCESSED_DIR / str(season) / f"round-{round_number}-style-stats.csv"
    latest_path = PROCESSED_DIR / "latest-style-stats.csv"

    raw_payload = {
        "season": season,
        "round": round_number,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "pages": raw_pages,
    }
    raw_path.write_text(json.dumps(raw_payload, indent=2), encoding="utf-8")

    for path in (processed_path, latest_path):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))

    logging.info("Wrote raw snapshot: %s", raw_path)
    logging.info("Wrote processed CSV: %s", processed_path)
    logging.info("Updated latest CSV: %s", latest_path)


def infer_round(round_one_monday: str, today: date | None = None) -> int:
    today = today or datetime.now().date()
    start = date.fromisoformat(round_one_monday)
    if today < start:
        raise ValueError(f"Cannot infer round before round-one Monday: {round_one_monday}")
    return ((today - start).days // 7) + 1


def run_once(args: argparse.Namespace) -> None:
    source_urls = expand_source_urls(args.url or os.environ.get("NRL_STYLE_STATS_URL"))

    round_number = args.round
    if round_number is None:
        round_one_monday = args.round_one_monday or os.environ.get("NRL_ROUND_ONE_MONDAY", DEFAULT_ROUND_ONE_MONDAY)
        round_number = infer_round(round_one_monday)

    as_of_date = args.as_of_date or datetime.now().date().isoformat()
    raw_pages: list[dict] = []
    all_rows: list[StyleRow] = []
    for source_url in source_urls:
        logging.info("Fetching NRL style stats from %s", source_url)
        html = fetch_html(source_url, args.timeout)
        raw_pages.append({"source_url": source_url, "html": html})
        all_rows.extend(extract_table_rows(html, source_url, args.season, round_number, as_of_date))

    rows = dedupe_rows(all_rows)

    if not rows:
        raise RuntimeError("No style-stat rows parsed. The source parser needs selectors for this website.")

    write_outputs(rows, raw_pages, args.season, round_number)
    logging.info("Parsed %d teams.", len(rows))


def run_with_retries(args: argparse.Namespace) -> None:
    last_error: Exception | None = None
    for attempt in range(1, args.max_attempts + 1):
        try:
            logging.info("Attempt %d/%d", attempt, args.max_attempts)
            run_once(args)
            return
        except Exception as exc:
            last_error = exc
            logging.error("Attempt %d failed: %s", attempt, exc)
            if attempt < args.max_attempts:
                logging.info("Retrying in %d seconds.", args.retry_delay_seconds)
                time.sleep(args.retry_delay_seconds)
    raise RuntimeError(f"All attempts failed. Last error: {last_error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape weekly NRL T2 style stats into BetMate data storage.")
    parser.add_argument("--season", type=int, default=datetime.now().year)
    parser.add_argument("--round", type=int)
    parser.add_argument("--round-one-monday", default="")
    parser.add_argument("--as-of-date", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--retry-delay-seconds", type=int, default=DEFAULT_RETRY_DELAY_SECONDS)
    parser.add_argument("--no-retry", action="store_true")
    return parser


def main() -> int:
    setup_logging()
    load_dotenv(ROOT / ".env.local")
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.no_retry:
            run_once(args)
        else:
            run_with_retries(args)
        return 0
    except Exception as exc:
        logging.error("NRL style scrape failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
