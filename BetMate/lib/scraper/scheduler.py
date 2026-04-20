"""
lib/scraper/scheduler.py

Two-run weekly schedule for the odds scraper:

  Run 1 — Thursday evening (19:00 AEST / 09:00 UTC)
           After NRL/AFL referee appointments are published.
           Captures opening lines and referee data.

  Run 2 — Saturday morning (08:00 AEST / 22:00 UTC prev day)
           Captures any line movement before weekend games kick off.

Can be deployed as:
  - A cron job on a Linux server / Render / Railway
  - A GitHub Actions workflow (see .github/workflows/scraper.yml template below)
  - Called by an OpenClaw sub-agent on a schedule

Usage:
  python lib/scraper/scheduler.py            # run immediately (manual)
  python lib/scraper/scheduler.py --daemon   # run on schedule (blocking)
"""

import argparse
import logging
import time
from datetime import datetime, timezone

import schedule

from oddscomparison import run as run_scraper

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

SPORTS = ["NRL"]   # extend to ["NRL", "AFL"] when AFL module is ready


def scrape_job(label: str) -> None:
    log.info("=== Scheduled scrape: %s ===", label)
    try:
        run_scraper(SPORTS)
    except Exception as exc:
        log.error("Scrape failed [%s] — %s", label, exc)


def setup_schedule() -> None:
    # Thursday 19:00 AEST = Thursday 09:00 UTC
    schedule.every().thursday.at("09:00").do(scrape_job, label="Thursday-referee-drop")
    # Saturday 08:00 AEST = Friday 22:00 UTC
    schedule.every().friday.at("22:00").do(scrape_job, label="Saturday-line-movement")

    log.info("Scheduler ready. Jobs:")
    for job in schedule.jobs:
        log.info("  %s", job)


def run_daemon() -> None:
    setup_schedule()
    log.info("Daemon running. Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(30)


# ─── GitHub Actions cron template ────────────────────────────────────────
# Create .github/workflows/scraper.yml with:
#
# name: Odds Scraper
# on:
#   schedule:
#     - cron: '0 9 * * 4'    # Thursday 09:00 UTC
#     - cron: '0 22 * * 5'   # Friday 22:00 UTC (Saturday 08:00 AEST)
#   workflow_dispatch:
# jobs:
#   scrape:
#     runs-on: ubuntu-latest
#     steps:
#       - uses: actions/checkout@v4
#       - uses: actions/setup-python@v5
#         with: { python-version: '3.12' }
#       - run: pip install requests beautifulsoup4 supabase schedule
#       - run: python lib/scraper/scheduler.py
#     env:
#       NEXT_PUBLIC_SUPABASE_URL:      ${{ secrets.SUPABASE_URL }}
#       NEXT_PUBLIC_SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}
#       ODDS_SCRAPER_TARGET:           oddscomparison
# ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as a blocking daemon on the weekly schedule.",
    )
    args = parser.parse_args()

    if args.daemon:
        run_daemon()
    else:
        # Manual / CI one-shot run
        log.info("Manual run — %s UTC", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
        scrape_job(label="manual")
