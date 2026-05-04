"""
lib/scraper/nrl_historical_results.py

Downloads the NRL historical results & odds Excel file from aussportsbetting.com.
The site uses Cloudflare protection so we drive a real Chromium browser via Playwright
to bypass bot detection and trigger the file download.

Source:  https://www.aussportsbetting.com/data/historical-nrl-results-and-odds-data/
Button:  "NRL 2009-present" (downloads an .xlsx file)

Outputs:
  data/nrl/historical/raw/nrl_YYYYMMDD.xlsx     ← dated copy
  data/nrl/historical/latest.xlsx               ← always the most recent
  data/nrl/historical/logs/scrape.log

BettingEngine reads latest.xlsx to rebuild ELO from historical results.

Scheduled: every Monday at 5:00 PM (before style-stats at 6:00 PM)

Usage:
  uv run --with playwright python lib/scraper/nrl_historical_results.py
  uv run --with playwright python lib/scraper/nrl_historical_results.py --headless false
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT          = Path(__file__).resolve().parents[2]
BASE_DIR      = ROOT / "data" / "nrl" / "historical"
RAW_DIR       = BASE_DIR / "raw"
LOG_DIR       = BASE_DIR / "logs"
LOG_PATH      = LOG_DIR / "scrape.log"
LATEST_PATH   = BASE_DIR / "latest.xlsx"

SOURCE_URL    = "https://www.aussportsbetting.com/data/historical-nrl-results-and-odds-data/"
DOWNLOAD_TEXT = ["NRL 2009", "NRL", "download", "Download"]  # button text candidates

DEFAULT_TIMEOUT_MS   = 60_000   # 60s page load timeout
DEFAULT_DOWNLOAD_MS  = 90_000   # 90s download timeout
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY  = 60

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


def download_with_playwright(headless: bool, timeout_ms: int, download_ms: int) -> Path | None:
    """
    Open the aussportsbetting page in a real Chromium browser, find the NRL
    download button, click it, and return the path to the downloaded file.
    Returns None if the download fails.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
            ignore_https_errors=True,   # handles corporate SSL inspection proxies
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            log.info("Opening %s", SOURCE_URL)
            page.goto(SOURCE_URL, timeout=timeout_ms, wait_until="domcontentloaded")

            # Wait for Cloudflare challenge to pass (if present)
            log.info("Waiting for page to settle ...")
            page.wait_for_timeout(4000)

            # Handle FortiGuard / content-filter block page
            # These pages typically show a "Proceed" link to bypass the warning
            title = page.title()
            body  = page.inner_text("body") if page.query_selector("body") else ""
            if any(kw in body for kw in ["FortiGuard", "Web Filter", "Access Blocked", "Blocked"]):
                log.warning("Content filter block page detected — attempting to click Proceed")
                proceed = None
                for sel in ["a:has-text('Proceed')", "input[value='Proceed']",
                            "button:has-text('Proceed')", "a:has-text('proceed')"]:
                    proceed = page.query_selector(sel)
                    if proceed:
                        break
                if proceed:
                    log.info("Clicking Proceed to bypass filter ...")
                    proceed.click()
                    page.wait_for_timeout(4000)
                    log.info("After proceed — title: %s  url: %s", page.title(), page.url)
                    # If the bypass redirected to the homepage, navigate to the data page
                    if "historical-nrl" not in page.url:
                        log.info("Bypassed to wrong page — navigating to data page ...")
                        page.goto(SOURCE_URL, timeout=timeout_ms, wait_until="domcontentloaded")
                        page.wait_for_timeout(3000)
                        log.info("Data page loaded — title: %s", page.title())
                else:
                    log.error("No Proceed button found on block page — site is network-blocked")
                    log.info("Block page text:\n%s", body[:500])
                    return None

            # Try to find the download link/button
            # Strategy 1: look for links containing xlsx
            log.info("Looking for download link ...")
            download_link = None

            # Strategy 1: any <a> whose href ends in .xlsx (most reliable)
            for a in page.query_selector_all("a[href]"):
                href = a.get_attribute("href") or ""
                if href.lower().endswith(".xlsx") or ".xlsx" in href.lower():
                    text = (a.text_content() or "").strip()
                    log.info("Found xlsx link: text=%r href=%s", text, href)
                    download_link = a
                    break

            # Strategy 2: link text contains "NRL" AND "2009" (the specific button)
            if not download_link:
                for a in page.query_selector_all("a"):
                    text = (a.text_content() or "").strip()
                    if "NRL" in text and "2009" in text:
                        href = a.get_attribute("href") or ""
                        log.info("Found NRL 2009 link: text=%r href=%s", text, href)
                        download_link = a
                        break

            # Strategy 3: any visible button/link labelled "Download" on the page
            if not download_link:
                for sel in ["a:has-text('Download NRL')", "a:has-text('NRL Excel')",
                            "a:has-text('NRL Data')", "button:has-text('NRL')"]:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        log.info("Found element via selector: %s", sel)
                        download_link = el
                        break

            if not download_link:
                log.error("Could not find download button on page")
                log.info("Page title: %s", page.title())
                log.info("Page URL: %s", page.url)
                # Dump visible text for debugging
                body_text = page.inner_text("body")[:1000]
                log.info("Page text (first 1000 chars):\n%s", body_text)
                return None

            log.info("Clicking download link ...")
            with page.expect_download(timeout=download_ms) as dl_info:
                download_link.click()

            download = dl_info.value
            suggested = download.suggested_filename or "nrl.xlsx"
            log.info("Download started: %s", suggested)

            # Save with date stamp
            today = datetime.now().strftime("%Y%m%d")
            dest = RAW_DIR / f"nrl_{today}.xlsx"
            download.save_as(str(dest))
            log.info("Saved raw: %s (%d bytes)", dest, dest.stat().st_size)
            return dest

        except PWTimeout as exc:
            log.error("Playwright timeout — %s", exc)
            return None
        except Exception as exc:
            log.error("Playwright error — %s", exc)
            return None
        finally:
            context.close()
            browser.close()


def update_latest(raw_path: Path) -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_path, LATEST_PATH)
    log.info("Updated latest.xlsx (%d bytes)", LATEST_PATH.stat().st_size)


def scrape(headless: bool, max_attempts: int, retry_delay: int,
           timeout_ms: int, download_ms: int) -> bool:
    for attempt in range(1, max_attempts + 1):
        log.info("Attempt %d/%d — downloading NRL historical results", attempt, max_attempts)
        path = download_with_playwright(headless, timeout_ms, download_ms)
        if path and path.exists() and path.stat().st_size > 10_000:
            update_latest(path)
            log.info("Download complete — %s", path.name)
            return True
        if attempt < max_attempts:
            log.warning("Download failed or file too small, retrying in %ds", retry_delay)
            time.sleep(retry_delay)
    log.error("All attempts exhausted — NRL historical results not downloaded")
    return False


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(description="Download NRL historical results from aussportsbetting.com")
    p.add_argument("--headless", default="true",
                   help="Run browser headless (true/false). Use false to debug.")
    p.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    p.add_argument("--retry-delay-seconds", type=int, default=DEFAULT_RETRY_DELAY)
    p.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    p.add_argument("--download-timeout-ms", type=int, default=DEFAULT_DOWNLOAD_MS)
    args = p.parse_args()

    headless = args.headless.lower() != "false"
    log.info("NRL Historical Results scraper — headless=%s", headless)

    ok = scrape(
        headless=headless,
        max_attempts=args.max_attempts,
        retry_delay=args.retry_delay_seconds,
        timeout_ms=args.timeout_ms,
        download_ms=args.download_timeout_ms,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
