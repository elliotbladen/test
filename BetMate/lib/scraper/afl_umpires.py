"""
Scrape AFL umpire appointments from AFLUA round PDFs.

Outputs:
  data/afl/umpires/raw/YYYY/round-N.pdf
  data/afl/umpires/raw/YYYY/round-N.txt
  data/afl/umpires/processed/YYYY/round-N-umpires.csv
  data/afl/umpires/processed/latest-umpires.csv
  data/afl/umpires/processed/latest-umpires.json

Usage:
  uv run --with requests --with beautifulsoup4 --with pypdf python lib/scraper/afl_umpires.py --season 2026 --round 9
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = ROOT / "data" / "afl" / "umpires"
RAW_DIR = BASE_DIR / "raw"
PROCESSED_DIR = BASE_DIR / "processed"
LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "scrape.log"

AFLUA_APPOINTMENTS_URL = "https://aflua.com.au/umpire-appointments/"
DEFAULT_ROUND_ONE_MONDAY = "2026-03-09"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

TEAM_MAP = {
    "adelaide": "Adelaide Crows",
    "brisbane": "Brisbane Lions",
    "carlton": "Carlton Blues",
    "collingwood": "Collingwood Magpies",
    "essendon": "Essendon Bombers",
    "fremantle": "Fremantle Dockers",
    "geelong": "Geelong Cats",
    "gold coast": "Gold Coast Suns",
    "gws giants": "Greater Western Sydney Giants",
    "gws": "Greater Western Sydney Giants",
    "hawthorn": "Hawthorn Hawks",
    "melbourne": "Melbourne Demons",
    "north melbourne": "North Melbourne Kangaroos",
    "port adelaide": "Port Adelaide Power",
    "richmond": "Richmond Tigers",
    "st kilda": "St Kilda Saints",
    "sydney": "Sydney Swans",
    "west coast": "West Coast Eagles",
    "western bulldogs": "Western Bulldogs",
}

VENUES = [
    "Optus Stadium",
    "The Gabba",
    "Adelaide Oval",
    "Marvel Stadium",
    "ENGIE Stadium",
    "TIO Stadium",
    "MCG",
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


def canon_team(raw: str) -> str:
    cleaned = raw.strip().replace(".", "").lower()
    return TEAM_MAP.get(cleaned, raw.strip())


def fetch(url: str) -> bytes:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.content


def discover_pdf_url(round_number: int, explicit_url: str | None = None) -> str:
    if explicit_url:
        return explicit_url

    html = fetch(AFLUA_APPOINTMENTS_URL).decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    target = f"Round {round_number}".lower()
    for link in soup.find_all("a", href=True):
        text = link.get_text(" ", strip=True).lower()
        href = link["href"]
        if target == text and href.lower().endswith(".pdf"):
            return href

    pattern = re.compile(rf"https://aflua\.com\.au/wp-content/uploads/\d{{4}}/\d{{2}}/Round-{round_number}\.pdf", re.I)
    match = pattern.search(html)
    if match:
        return match.group(0)

    raise RuntimeError(f"Could not discover AFLUA PDF for Round {round_number}")


def pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def names_from_line(line: str, stop_words: list[str] | None = None) -> list[str]:
    stop_words = stop_words or []
    cleaned = line
    for stop in stop_words:
        cleaned = cleaned.split(stop)[0]
    markers = list(re.finditer(r"\b\d+\s*[–-]?\s*", cleaned))
    if markers:
        names: list[str] = []
        for idx, marker in enumerate(markers):
            start = marker.end()
            end = markers[idx + 1].start() if idx + 1 < len(markers) else len(cleaned)
            name = re.sub(r"\s+", " ", cleaned[start:end]).strip(" -–")
            if name:
                names.append(name)
        return names
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return [cleaned] if cleaned else []


def parse_text(text: str) -> list[dict]:
    records: list[dict] = []
    blocks = re.split(r"\bDATE AFL MATCH VENUE TIME\b", text)

    for block in blocks:
        if "FIELD UMPIRES" not in block:
            continue

        venue_pattern = "|".join(re.escape(v) for v in VENUES)
        header_match = re.search(
            rf"\d{{4}}\s+(.+?)\s+vs\.\s+(.+?)\s+({venue_pattern})\s+\d{{1,2}}:\d{{2}}",
            block,
            re.S,
        )
        if not header_match:
            continue

        home = canon_team(header_match.group(1))
        away = canon_team(header_match.group(2))

        field_line = re.search(r"FIELD UMPIRES\s+(.+?)\s+BOUNDARY UMPIRES", block, re.S)
        boundary_line = re.search(r"BOUNDARY UMPIRES\s+(.+?)\s+GOAL UMPIRES", block, re.S)
        goal_line = re.search(r"GOAL UMPIRES\s+(.+?)(?:\n\s*\n|$)", block, re.S)

        field = names_from_line(field_line.group(1), ["BOUNDARY UMPIRES"]) if field_line else []
        boundary = names_from_line(boundary_line.group(1), ["GOAL UMPIRES"]) if boundary_line else []
        goal = names_from_line(goal_line.group(1), ["EM:"]) if goal_line else []
        emergency_match = re.search(r"EM:\s*([A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+)+)", block)
        emergency = emergency_match.group(1).strip() if emergency_match else ""

        records.append({
            "home_team": home,
            "away_team": away,
            "field_umpires": "; ".join(field),
            "boundary_umpires": "; ".join(boundary),
            "goal_umpires": "; ".join(goal),
            "emergency": emergency,
            "referee": "; ".join(field),
        })

    return records


def write_outputs(records: list[dict], pdf_bytes: bytes, text: str, season: int, round_number: int, source_url: str) -> None:
    scraped_at = datetime.now(timezone.utc).isoformat()

    raw_dir = RAW_DIR / str(season)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"round-{round_number}.pdf").write_bytes(pdf_bytes)
    (raw_dir / f"round-{round_number}.txt").write_text(text, encoding="utf-8")

    proc_dir = PROCESSED_DIR / str(season)
    proc_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = ["home_team", "away_team", "field_umpires", "boundary_umpires", "goal_umpires", "emergency", "referee"]

    def write_csv(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

    write_csv(proc_dir / f"round-{round_number}-umpires.csv")
    write_csv(PROCESSED_DIR / "latest-umpires.csv")
    (PROCESSED_DIR / "latest-umpires.json").write_text(
        json.dumps({
            "sport": "AFL",
            "season": season,
            "round": round_number,
            "scraped_at": scraped_at,
            "source_url": source_url,
            "records": records,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Wrote latest-umpires.csv — %d assignments, round %d", len(records), round_number)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Scrape AFL umpire appointments from AFLUA")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--round", dest="round_number", type=int, default=0)
    parser.add_argument("--round-one-monday", default=DEFAULT_ROUND_ONE_MONDAY)
    parser.add_argument("--pdf-url", default=None, help="Explicit AFLUA round PDF URL")
    args = parser.parse_args()

    round_number = args.round_number or infer_round(args.round_one_monday)
    pdf_url = discover_pdf_url(round_number, args.pdf_url)
    log.info("Using AFLUA source: %s", pdf_url)
    pdf_bytes = fetch(pdf_url)
    text = pdf_text(pdf_bytes)
    records = parse_text(text)
    write_outputs(records, pdf_bytes, text, args.season, round_number, pdf_url)
    sys.exit(0 if records else 1)


if __name__ == "__main__":
    main()
