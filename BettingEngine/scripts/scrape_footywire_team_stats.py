#!/usr/bin/env python3
"""
scripts/scrape_footywire_team_stats.py

Scrapes AFL season-average team statistics from Footywire.

Two pages per year:
  Basic  : ft_team_rankings?year=YYYY          -> Goals, Behinds, I50, R50, HO
  Advanced: ft_team_rankings?advv=Y&year=YYYY  -> CP, CL, CCL, SCL, MI5, ITC, T50

The correct data table is the one whose first <td> says 'Team' — this is the
clean individual-cell table (Table 10 in the page source). Other tables with
matching headers contain navigation blobs or all-in-one text dumps.

Stores results in: data/footywire_team_stats.csv

USAGE
-----
    python3 scripts/scrape_footywire_team_stats.py
    python3 scripts/scrape_footywire_team_stats.py --years 2020 2021 2022
    python3 scripts/scrape_footywire_team_stats.py --years 2026
"""

import argparse
import csv
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT    = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / 'data' / 'footywire_team_stats.csv'

BASE_URL = 'https://www.footywire.com/afl/footy/ft_team_rankings'

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'en-AU,en;q=0.9',
    'Referer': 'https://www.footywire.com/',
}

# Footywire names (both short and full) → our canonical name
TEAM_MAP = {
    # Short names used from ~2015 onwards
    'Crows':            'Adelaide Crows',
    'Lions':            'Brisbane Lions',
    'Blues':            'Carlton Blues',
    'Magpies':          'Collingwood Magpies',
    'Bombers':          'Essendon Bombers',
    'Dockers':          'Fremantle Dockers',
    'Giants':           'Greater Western Sydney Giants',
    'Cats':             'Geelong Cats',
    'Suns':             'Gold Coast Suns',
    'Hawks':            'Hawthorn Hawks',
    'Demons':           'Melbourne Demons',
    'Kangaroos':        'North Melbourne Kangaroos',
    'Power':            'Port Adelaide Power',
    'Tigers':           'Richmond Tigers',
    'Saints':           'St Kilda Saints',
    'Swans':            'Sydney Swans',
    'Eagles':           'West Coast Eagles',
    'Bulldogs':         'Western Bulldogs',
    # Full names used in earlier years (2013–2014)
    'Adelaide':         'Adelaide Crows',
    'Brisbane Lions':   'Brisbane Lions',
    'Brisbane':         'Brisbane Lions',
    'Carlton':          'Carlton Blues',
    'Collingwood':      'Collingwood Magpies',
    'Essendon':         'Essendon Bombers',
    'Fremantle':        'Fremantle Dockers',
    'GWS Giants':       'Greater Western Sydney Giants',
    'GWS':              'Greater Western Sydney Giants',
    'Greater Western Sydney': 'Greater Western Sydney Giants',
    'Geelong':          'Geelong Cats',
    'Gold Coast':       'Gold Coast Suns',
    'Hawthorn':         'Hawthorn Hawks',
    'Melbourne':        'Melbourne Demons',
    'North Melbourne':  'North Melbourne Kangaroos',
    'Port Adelaide':    'Port Adelaide Power',
    'Richmond':         'Richmond Tigers',
    'St Kilda':         'St Kilda Saints',
    'Sydney':           'Sydney Swans',
    'West Coast':       'West Coast Eagles',
    'Western Bulldogs': 'Western Bulldogs',
    # Legacy / ignore
    'Brisbane Bears':   None,
    'Fitzroy':          None,
}

# ── Column layout ─────────────────────────────────────────────────────────────
# Basic page columns (after Rk=0, Team=1):
# idx: 0=Rk  1=Team  2=Gm  3=K  4=HB  5=D  6=M  7=G  8=GA  9=I50
#      10=BH  11=HO  12=OF  13=FF  14=FA  15=CL  16=CG  17=R50  18=AFS  19=SC
BASIC_IDX = {
    'games':          2,
    'goals_pg':       7,
    'behinds_pg':     10,
    'inside_50s_pg':  9,
    'hitouts_pg':     11,
    'rebound_50s_pg': 17,
    'clearances_pg':  15,
}

# Advanced page columns (after Rk=0, Team=1):
# idx: 0=Rk  1=Team  2=Gm  3=CP  4=UP  5=ED  6=DE%  7=CM  8=MI5  9=1%
#      10=BO  11=CL  12=CCL  13=SCL  14=MG  15=TO  16=ITC  17=T50
ADV_IDX = {
    'games':                    2,
    'cp_pg':                    3,
    'marks_i50_pg':             8,
    'clearances_pg':            11,
    'centre_clearances_pg':     12,
    'stoppage_clearances_pg':   13,
    'intercept_poss_pg':        16,
    'tackles_i50_pg':           17,
}

# Advanced page for some years (2013) has fewer columns — stop if missing
ADV_IDX_V1 = {   # 2013-2014: no CCL/SCL/MG/TO/ITC/T50
    'games':     2,
    'cp_pg':     3,
    'marks_i50_pg': 8,
    'clearances_pg': 11,
}


def _safe_float(txt: str):
    try:
        return float(txt.replace(',', '').replace('%', '').strip())
    except (ValueError, AttributeError):
        return None


def _find_clean_table(soup: BeautifulSoup, header_hints: list[str]):
    """
    Find the clean data table: a table with matching header hints AND whose
    first <td> text is 'Team'. This is always table-10 in the page, which
    has one clean cell per stat per row.
    """
    for table in soup.find_all('table'):
        ths = [th.get_text(strip=True) for th in table.find_all('th')]
        if not any(h in ths for h in header_hints):
            continue
        tds = table.find_all('td')
        if tds and tds[0].get_text(strip=True) == 'Team':
            return table
    return None


def _parse_table(table, col_idx_map: dict, year: int) -> dict[str, dict]:
    """
    Parse a clean Footywire stats table.
    Row structure: Rk | Team | stat1 | stat2 | ...
    Returns {canonical_team: {field: value, ...}}
    """
    results: dict[str, dict] = {}

    for tr in table.find_all('tr'):
        cells = tr.find_all(['td', 'th'])
        if not cells:
            continue

        first = cells[0].get_text(strip=True)

        # Skip header rows and the sticky 'Team' label row
        if first in ('', 'Team', 'Rk') or not first.isdigit():
            continue

        # first cell is Rk (digit), second is Team name
        if len(cells) < 3:
            continue

        team_raw = cells[1].get_text(strip=True)
        canonical = TEAM_MAP.get(team_raw)
        if canonical is None:
            # Try partial match
            for k, v in TEAM_MAP.items():
                if k.lower() in team_raw.lower() or team_raw.lower() in k.lower():
                    canonical = v
                    break
        if not canonical:
            continue

        rec: dict = {'season': year}
        for field, idx in col_idx_map.items():
            if idx < len(cells):
                rec[field] = _safe_float(cells[idx].get_text(strip=True))
            else:
                rec[field] = None

        results[canonical] = rec

    return results


def scrape_year(year: int, session: requests.Session) -> list[dict]:
    """Scrape basic + advanced stats for one season. Returns list of dicts."""

    # ── Basic page ────────────────────────────────────────────────────────────
    basic_data: dict[str, dict] = {}
    try:
        resp = session.get(BASE_URL, params={'year': year},
                           headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        table = _find_clean_table(soup, ['I50', 'G', 'K'])
        if table:
            basic_data = _parse_table(table, BASIC_IDX, year)
        else:
            print(f'  [no basic table {year}]', end=' ')
    except Exception as e:
        print(f'  [basic err {year}: {e}]', end=' ')

    time.sleep(0.9)

    # ── Advanced page ─────────────────────────────────────────────────────────
    adv_data: dict[str, dict] = {}
    try:
        resp = session.get(BASE_URL, params={'year': year, 'advv': 'Y'},
                           headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')
        table = _find_clean_table(soup, ['CP', 'CL', 'MI5'])
        if table:
            # Detect column count to decide which index map to use
            first_data_row = None
            for tr in table.find_all('tr'):
                cells = tr.find_all(['td', 'th'])
                if cells and cells[0].get_text(strip=True).isdigit():
                    first_data_row = cells
                    break
            ncols = len(first_data_row) if first_data_row else 0
            idx_map = ADV_IDX if ncols >= 17 else ADV_IDX_V1
            adv_data = _parse_table(table, idx_map, year)
        else:
            print(f'  [no adv table {year}]', end=' ')
    except Exception as e:
        print(f'  [adv err {year}: {e}]', end=' ')

    time.sleep(0.9)

    # ── Merge basic + advanced ────────────────────────────────────────────────
    all_teams = set(basic_data) | set(adv_data)
    rows = []
    for team in sorted(all_teams):
        rec = {'season': year, 'team_name': team}
        for d in (basic_data.get(team, {}), adv_data.get(team, {})):
            for k, v in d.items():
                if k != 'season' and rec.get(k) is None:
                    rec[k] = v

        # Prefer games from basic
        if rec.get('games') is None:
            rec['games'] = (adv_data.get(team, {}).get('games') or
                            basic_data.get(team, {}).get('games'))

        # Derive goal conversion
        goals   = rec.get('goals_pg')
        behinds = rec.get('behinds_pg')
        if goals is not None and behinds is not None:
            shots = goals + behinds
            rec.setdefault('scoring_shots_pg', shots)
            rec['goal_conv_pct'] = round(goals / shots, 4) if shots > 0 else None
        else:
            rec.setdefault('scoring_shots_pg', None)
            rec.setdefault('goal_conv_pct', None)

        rows.append(rec)

    return rows


FIELDNAMES = [
    'season', 'team_name', 'games',
    'goals_pg', 'behinds_pg', 'scoring_shots_pg', 'goal_conv_pct',
    'inside_50s_pg', 'rebound_50s_pg',
    'marks_i50_pg',
    'hitouts_pg',
    'clearances_pg', 'centre_clearances_pg', 'stoppage_clearances_pg',
    'cp_pg',
    'intercept_poss_pg', 'tackles_i50_pg',
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--years', nargs='+', type=int,
                        default=list(range(2013, 2027)),
                        help='Seasons to scrape (default 2013-2026)')
    parser.add_argument('--out', default=str(OUT_CSV))
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    session  = requests.Session()
    all_rows = []

    for year in sorted(args.years):
        print(f'Scraping {year}...', end=' ', flush=True)
        rows = scrape_year(year, session)
        if rows:
            print(f'{len(rows)} teams')
            all_rows.extend(rows)
        else:
            print('no data')
        time.sleep(0.3)

    if not all_rows:
        print('No data scraped.')
        return

    with open(out_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_rows)

    print(f'\nSaved {len(all_rows)} rows → {out_path}')

    seasons = sorted(set(r['season'] for r in all_rows))
    print(f'Seasons: {seasons[0]} – {seasons[-1]}')

    # Sanity check on most recent full season
    sample_yr = max(s for s in seasons if s <= 2025)
    sample = [r for r in all_rows if r['season'] == sample_yr]
    print(f'\nSample ({sample_yr}) — sorted by CP/game:')
    for r in sorted(sample, key=lambda x: -(x.get('cp_pg') or 0))[:8]:
        cp  = r.get('cp_pg')   or '—'
        cl  = r.get('clearances_pg') or '—'
        i50 = r.get('inside_50s_pg') or '—'
        r50 = r.get('rebound_50s_pg') or '—'
        gconv = r.get('goal_conv_pct') or '—'
        print(f"  {r['team_name']:<40} "
              f"CP:{str(cp):>6}  CL:{str(cl):>5}  "
              f"I50:{str(i50):>5}  R50:{str(r50):>5}  "
              f"Gconv:{str(gconv):>6}")


if __name__ == '__main__':
    main()
