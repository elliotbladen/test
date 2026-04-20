"""
lib/scraper/oddscomparison.py

NRL odds scraper — targets OddsComparison.com.au NRL page.
Extracts home/away odds per bookmaker per game and writes to
Supabase weekly_odds table.

─── SWAP NOTE ────────────────────────────────────────────────────────────
After ~500 visitors, replace this scraper with The Odds API:
  ODDS_SCRAPER_TARGET=oddsapi  (set in .env.local)
The Supabase schema (weekly_odds) does not change.
Replace get_odds_oddscomparison() with get_odds_oddsapi().
One afternoon of work.
──────────────────────────────────────────────────────────────────────────

Usage:
  python lib/scraper/oddscomparison.py
  # or invoked by scheduler.py / OpenClaw sub-agent
"""

import os
import time
import random
import logging
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

# ─── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────
SUPABASE_URL  = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY  = os.environ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
TARGET        = os.environ.get("ODDS_SCRAPER_TARGET", "oddscomparison")

NRL_URL  = "https://www.oddscomparison.com.au/nrl/"
AFL_URL  = "https://www.oddscomparison.com.au/afl/"

# Bookmakers to capture (column order in weekly_odds)
BOOKMAKERS = ["sportsbet", "tab", "neds", "betfair"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ─── Scraper ──────────────────────────────────────────────────────────────

def human_delay(lo: float = 3.0, hi: float = 9.0) -> None:
    """Sleep a random duration to avoid rate-limit detection."""
    delay = random.uniform(lo, hi)
    log.debug("Sleeping %.1fs", delay)
    time.sleep(delay)


def fetch_page(url: str) -> BeautifulSoup | None:
    """Fetch URL with rotating delays and return parsed HTML."""
    human_delay()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as exc:
        log.error("Failed to fetch %s — %s", url, exc)
        return None


def parse_odds_table(soup: BeautifulSoup, sport: str) -> list[dict]:
    """
    Parse the OddsComparison match table.
    Returns a list of game dicts ready for Supabase upsert.

    NOTE: CSS selectors here are illustrative — update them to match
    the live OddsComparison DOM if it changes.
    """
    games = []
    rows = soup.select("table.odds-table tbody tr.match-row")

    if not rows:
        log.warning("No match rows found — page structure may have changed.")
        return games

    for row in rows:
        try:
            home_team = row.select_one(".home-team").get_text(strip=True)
            away_team = row.select_one(".away-team").get_text(strip=True)
            kickoff   = row.select_one(".kickoff-time").get_text(strip=True)
            venue     = row.select_one(".venue").get_text(strip=True) or ""

            odds_cells = row.select(".bookmaker-odds")
            bm_odds: dict[str, dict[str, float]] = {}

            for cell in odds_cells:
                bm   = cell.get("data-bookmaker", "").lower().replace(" ", "")
                home = float(cell.get("data-home-odds", 0) or 0)
                away = float(cell.get("data-away-odds", 0) or 0)
                if bm in BOOKMAKERS:
                    bm_odds[bm] = {"home": home, "away": away}

            # Fill missing bookmakers with None
            for bm in BOOKMAKERS:
                bm_odds.setdefault(bm, {"home": None, "away": None})

            games.append({
                "sport":               sport,
                "season":              datetime.now(timezone.utc).year,
                "round":               "TBC",           # populated by scheduler
                "home_team":           home_team,
                "away_team":           away_team,
                "kickoff_time":        kickoff,
                "venue":               venue,
                "referee":             "",               # populated separately
                "referee_bucket":      "",
                "home_odds_sportsbet": bm_odds["sportsbet"]["home"],
                "home_odds_tab":       bm_odds["tab"]["home"],
                "home_odds_neds":      bm_odds["neds"]["home"],
                "home_odds_betfair":   bm_odds["betfair"]["home"],
                "away_odds_sportsbet": bm_odds["sportsbet"]["away"],
                "away_odds_tab":       bm_odds["tab"]["away"],
                "away_odds_neds":      bm_odds["neds"]["away"],
                "away_odds_betfair":   bm_odds["betfair"]["away"],
                "ev_line_pct":         None,
                "ev_total_pct":        None,
                "ev_h2h_pct":          None,
                "sentiment_public_lean": None,
                "sentiment_line_move": None,
                "sentiment_ou_split":  None,
                "model_line":          None,
                "model_total":         None,
                "created_at":          datetime.now(timezone.utc).isoformat(),
            })

        except Exception as exc:
            log.error("Error parsing row — %s", exc)
            continue

    return games


def upsert_to_supabase(client: Client, games: list[dict]) -> None:
    """Upsert games to Supabase weekly_odds table."""
    if not games:
        log.info("No games to upsert.")
        return

    result = (
        client.table("weekly_odds")
        .upsert(games, on_conflict="sport,season,home_team,away_team")
        .execute()
    )
    log.info("Upserted %d games → Supabase", len(result.data))


def write_last_updated(client: Client, sport: str) -> None:
    """Write scraper run timestamp to a scraper_log table (optional)."""
    try:
        client.table("scraper_log").upsert(
            {"sport": sport, "last_run": datetime.now(timezone.utc).isoformat()},
            on_conflict="sport",
        ).execute()
    except Exception as exc:
        log.warning("Could not write scraper_log — %s", exc)


# ─── Odds API fallback ────────────────────────────────────────────────────
# TODO: swap in after 500 visitors — set ODDS_SCRAPER_TARGET=oddsapi
# from odds_api import get_odds_oddsapi

def get_odds_oddscomparison(sport: str) -> list[dict]:
    url  = NRL_URL if sport == "NRL" else AFL_URL
    soup = fetch_page(url)
    if not soup:
        return []
    return parse_odds_table(soup, sport)


# ─── Main ─────────────────────────────────────────────────────────────────

def run(sports: list[str] | None = None) -> None:
    sports = sports or ["NRL"]
    client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    for sport in sports:
        log.info("Scraping %s odds from %s …", sport, TARGET)

        if TARGET == "oddsapi":
            # Placeholder — swap scraper here
            # games = get_odds_oddsapi(sport)
            raise NotImplementedError("Set ODDS_SCRAPER_TARGET=oddscomparison until Odds API is configured.")
        else:
            games = get_odds_oddscomparison(sport)

        upsert_to_supabase(client, games)
        write_last_updated(client, sport)
        human_delay(5, 12)   # polite gap between sports

    log.info("Scrape complete.")


if __name__ == "__main__":
    run(["NRL"])
