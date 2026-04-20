#!/usr/bin/env python3
"""
ml/features/scrape_referees.py

Scrapes NRL.com match pages to extract referee assignments for every game
from 2009 onwards. Results are cached locally so the site is never hit twice
for the same game.

Source: nrl.com match centre pages (HTML, no auth required)

USAGE
-----
    python ml/features/scrape_referees.py \
        --game-log ml/results/game_log.csv \
        --out      ml/results/referee_assignments.csv \
        --cache    ml/results/referee_cache.json \
        --seasons  2009 2025

OUTPUT COLUMNS
--------------
    season, date, home_team, away_team, referee

NOTE
----
    NRL.com draw URLs follow this pattern:
        /draw/nrl-premiership/{year}/round-{n}/{home-slug}-v-{away-slug}/

    The script builds the slug from team names and tries to fetch.
    Failed lookups are logged and cached as '' so they are not retried.

    Run time: ~2-3 hours for 15 seasons at polite rate.
    All results cached — rerun is instant.
"""

import argparse
import csv
import json
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

SLEEP_SEC   = 0.5    # polite — NRL.com is a production site
BASE_URL    = 'https://www.nrl.com'
DRAW_URL    = BASE_URL + '/draw/data?competition=111&season={season}&round={round}'

# Map canonical team names → NRL.com URL slugs
TEAM_SLUG = {
    'Brisbane Broncos':              'broncos',
    'Canberra Raiders':              'raiders',
    'Canterbury-Bankstown Bulldogs': 'bulldogs',
    'Cronulla-Sutherland Sharks':    'sharks',
    'Dolphins':                      'dolphins',
    'Gold Coast Titans':             'titans',
    'Manly-Warringah Sea Eagles':    'sea-eagles',
    'Melbourne Storm':               'storm',
    'New Zealand Warriors':          'warriors',
    'Newcastle Knights':             'knights',
    'North Queensland Cowboys':      'cowboys',
    'Parramatta Eels':               'eels',
    'Penrith Panthers':              'panthers',
    'South Sydney Rabbitohs':        'rabbitohs',
    'St. George Illawarra Dragons':  'dragons',
    'Sydney Roosters':               'roosters',
    'Wests Tigers':                  'tigers',
    'Gold Coast Chargers':           'chargers',
    'Northern Eagles':               'northern-eagles',
    'South Queensland Crushers':     'crushers',
    'Ottawa Senators':               'senators',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}


def load_cache(path: str) -> dict:
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict, path: str):
    with open(path, 'w') as f:
        json.dump(cache, f, indent=2)


def fetch_draw_round(season: int, round_num: int) -> list[dict]:
    """
    Fetch all fixtures for a round from NRL.com draw API.
    Returns list of dicts with matchCentreUrl, homeTeam, awayTeam.
    """
    url = DRAW_URL.format(season=season, round=round_num)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return data.get('fixtures', [])
    except Exception:
        return []


def extract_referee_from_page(match_url: str) -> str:
    """
    Fetch a match centre page and extract the referee name.
    Returns referee name or '' if not found.
    """
    url = BASE_URL + match_url
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode('utf-8')
    except Exception:
        return ''

    # Data is HTML-encoded JSON fragments: {"firstName":"X","lastName":"Y","position":"Referee",...}
    chunks = re.findall(
        r'\{[^{}]{0,500}[Rr]eferee[^{}]{0,500}\}', html
    )
    for chunk in chunks:
        chunk = chunk.replace('&quot;', '"').replace('&amp;', '&')
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if obj.get('position') == 'Referee':
            first = obj.get('firstName', '')
            last  = obj.get('lastName', '')
            if first and last:
                return f"{first} {last}"

    return ''


def get_rounds_for_season(season: int) -> list[int]:
    """Return round numbers that have data for a season."""
    rounds = []
    for rnd in range(1, 30):
        fixtures = fetch_draw_round(season, rnd)
        if not fixtures:
            break
        rounds.append(rnd)
        time.sleep(SLEEP_SEC)
    return rounds


def main():
    parser = argparse.ArgumentParser(description='Scrape NRL.com referee assignments')
    parser.add_argument('--game-log', default=str(ROOT / 'ml/results/game_log.csv'))
    parser.add_argument('--out',      default=str(ROOT / 'ml/results/referee_assignments.csv'))
    parser.add_argument('--cache',    default=str(ROOT / 'ml/results/referee_cache.json'))
    parser.add_argument('--seasons',  nargs=2, type=int, default=[2009, 2025],
                        metavar=('FROM', 'TO'))
    args = parser.parse_args()

    seasons = list(range(args.seasons[0], args.seasons[1] + 1))

    print(f"Loading cache ...")
    cache = load_cache(args.cache)
    print(f"  {len(cache)} entries cached")

    results = []
    total_fetched = 0
    total_found   = 0
    total_missed  = 0

    for season in seasons:
        print(f"\nSeason {season} ...")
        season_found = 0

        for rnd in range(1, 30):
            fixtures = fetch_draw_round(season, rnd)
            if not fixtures:
                break

            time.sleep(SLEEP_SEC)

            for fix in fixtures:
                if fix.get('type') != 'Match':
                    continue

                match_url = fix.get('matchCentreUrl', '')
                if not match_url:
                    continue

                cache_key = match_url

                if cache_key in cache:
                    referee = cache[cache_key]
                else:
                    referee = extract_referee_from_page(match_url)
                    cache[cache_key] = referee
                    total_fetched += 1
                    time.sleep(SLEEP_SEC)

                    # Save cache every 50 fetches
                    if total_fetched % 50 == 0:
                        save_cache(cache, args.cache)
                        print(f"  Cache saved ({total_fetched} fetched so far) ...")

                home = fix.get('homeTeam', {}).get('nickName', '')
                away = fix.get('awayTeam', {}).get('nickName', '')
                kickoff = fix.get('clock', {}).get('kickOffTimeLong', '')
                date = kickoff[:10] if kickoff else ''

                row = {
                    'season':    season,
                    'round':     rnd,
                    'date':      date,
                    'home_team': home,
                    'away_team': away,
                    'match_url': match_url,
                    'referee':   referee,
                }
                results.append(row)

                if referee:
                    season_found += 1
                    total_found += 1
                else:
                    total_missed += 1

        print(f"  R1-R{rnd-1}: {season_found} refs found")

    # Final cache save
    save_cache(cache, args.cache)

    # Write output
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if results:
        with open(out, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)

    print(f"\n{'─'*60}")
    print(f"  Total games:   {len(results)}")
    print(f"  Refs found:    {total_found}")
    print(f"  Refs missing:  {total_missed}")
    print(f"  Hit rate:      {total_found/max(len(results),1)*100:.1f}%")
    print(f"\n  Written → {out}")
    print("\nDone.")


if __name__ == '__main__':
    main()
