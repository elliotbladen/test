"""
lib/scraper/nrl_round_prep.py

Orchestrator — runs all three NRL round-prep scrapers in sequence:
  1. nrl_fixture.py   → data/nrl/fixture/processed/latest-fixture.json
  2. nrl_injuries.py  → data/nrl/injuries/processed/latest-injuries.json
  3. nrl_referees.py  → data/nrl/referees/processed/latest-referees.csv

Scheduled at 6:05 PM every Monday via Windows Task Scheduler.
BettingEngine reads from these outputs at 7:03 PM.

Usage:
  uv run --with requests --with beautifulsoup4 python lib/scraper/nrl_round_prep.py --season 2026
  uv run --with requests --with beautifulsoup4 python lib/scraper/nrl_round_prep.py --season 2026 --round 11
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT     = Path(__file__).resolve().parents[2]
LOG_DIR  = ROOT / "data" / "nrl" / "logs"
LOG_PATH = LOG_DIR / "round_prep.log"

DEFAULT_ROUND_ONE_MONDAY = "2026-03-02"

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
    from datetime import datetime as dt
    monday = dt.strptime(round_one_monday, "%Y-%m-%d").date()
    today  = dt.now().date()
    if today < monday:
        return 1
    return (today - monday).days // 7 + 1


def run_fixture(season: int, round_number: int, max_attempts: int, retry_delay: int) -> bool:
    from nrl_fixture import scrape as fixture_scrape, setup_logging as fix_log
    fix_log()
    log.info("=== FIXTURE ===")
    count = fixture_scrape(season, round_number, max_attempts, retry_delay)
    ok = count > 0
    if not ok:
        log.warning("Fixture scrape returned 0 games — BettingEngine may not know which games are on")
    return ok


def run_injuries(season: int, round_number: int, max_attempts: int, retry_delay: int) -> bool:
    from nrl_injuries import scrape as injury_scrape, setup_logging as inj_log
    inj_log()
    log.info("=== INJURIES ===")
    count = injury_scrape(season, round_number, max_attempts, retry_delay)
    # 0 injuries is valid (no outs this week) — only fail on error
    log.info("Injury scrape complete — %d records", count)
    return True


def run_referees(season: int, round_number: int, max_attempts: int, retry_delay: int) -> bool:
    from nrl_referees import scrape as ref_scrape, setup_logging as ref_log
    ref_log()
    log.info("=== REFEREES ===")
    count = ref_scrape(season, round_number, max_attempts, retry_delay)
    if count == 0:
        log.warning("Referee scrape returned 0 — may not be announced yet (usually Tue/Wed)")
    return True


def main() -> None:
    setup_logging()

    p = argparse.ArgumentParser(description="NRL round prep — fixture + injuries + referees")
    p.add_argument("--season", type=int, default=2026)
    p.add_argument("--round", dest="round_number", type=int, default=0,
                   help="Round number (0 = auto-detect)")
    p.add_argument("--round-one-monday", default=DEFAULT_ROUND_ONE_MONDAY)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--retry-delay-seconds", type=int, default=30)
    p.add_argument("--skip-fixture", action="store_true")
    p.add_argument("--skip-injuries", action="store_true")
    p.add_argument("--skip-referees", action="store_true")
    args = p.parse_args()

    round_number = args.round_number or infer_round(args.round_one_monday)
    log.info("NRL Round Prep — season=%d round=%d — %s UTC",
             args.season, round_number,
             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))

    # Add scraper dir to path so imports work
    scraper_dir = Path(__file__).parent
    if str(scraper_dir) not in sys.path:
        sys.path.insert(0, str(scraper_dir))

    results: dict[str, bool] = {}

    if not args.skip_fixture:
        results["fixture"] = run_fixture(
            args.season, round_number, args.max_attempts, args.retry_delay_seconds
        )

    if not args.skip_injuries:
        results["injuries"] = run_injuries(
            args.season, round_number, args.max_attempts, args.retry_delay_seconds
        )

    if not args.skip_referees:
        results["referees"] = run_referees(
            args.season, round_number, args.max_attempts, args.retry_delay_seconds
        )

    log.info("=== SUMMARY ===")
    all_ok = True
    for name, ok in results.items():
        status = "OK" if ok else "WARN"
        log.info("  %-12s %s", name, status)
        if not ok:
            all_ok = False

    if all_ok:
        log.info("Round prep complete — BettingEngine ready to price R%d at 7:03 PM", round_number)
    else:
        log.warning("Round prep finished with warnings — check fixture data before pricing")

    sys.exit(0)


if __name__ == "__main__":
    main()
