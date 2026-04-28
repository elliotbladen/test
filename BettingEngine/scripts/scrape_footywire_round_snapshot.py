#!/usr/bin/env python3
"""
scripts/scrape_footywire_round_snapshot.py

Scrapes Footywire team stats for a given round and appends to a snapshots CSV.
Run this AFTER each round completes (e.g. Monday morning) to capture season-to-date
averages entering the next round.

Captures ALL available stats from both the basic and advanced pages:

Basic  (ft_team_rankings?year=YYYY):
  K, HB, D, M, G, GA, I50, BH, T, HO, FF, FA, CL, CG, R50

Advanced (ft_team_rankings?advv=Y&year=YYYY):
  CP, UP, ED, DE%, CM, MI5, 1%, BO, CL, CCL, SCL, MG, TO, ITC, T50

Derived:
  goal_conv_pct = G / (G + BH)
  kicking_ratio = K / (K + HB)        — style signal: kick-dominant vs handball-chain
  mg_pg         = MG / Gm             — metres gained per game (MG is season total on page)

Output: data/footywire_snapshots.csv  (append — one row per team per snapshot)

USAGE
-----
    python3 scripts/scrape_footywire_round_snapshot.py --season 2026 --round 9
    python3 scripts/scrape_footywire_round_snapshot.py --season 2026 --round 9 --overwrite
"""

import argparse
import csv
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT       = Path(__file__).resolve().parent.parent
SNAP_CSV   = ROOT / 'data' / 'footywire_snapshots.csv'

BASE_URL   = 'https://www.footywire.com/afl/footy/ft_team_rankings'

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

TEAM_MAP = {
    'Crows':     'Adelaide Crows',
    'Lions':     'Brisbane Lions',
    'Blues':     'Carlton Blues',
    'Magpies':   'Collingwood Magpies',
    'Bombers':   'Essendon Bombers',
    'Dockers':   'Fremantle Dockers',
    'Giants':    'Greater Western Sydney Giants',
    'Cats':      'Geelong Cats',
    'Suns':      'Gold Coast Suns',
    'Hawks':     'Hawthorn Hawks',
    'Demons':    'Melbourne Demons',
    'Kangaroos': 'North Melbourne Kangaroos',
    'Power':     'Port Adelaide Power',
    'Tigers':    'Richmond Tigers',
    'Saints':    'St Kilda Saints',
    'Swans':     'Sydney Swans',
    'Eagles':    'West Coast Eagles',
    'Bulldogs':  'Western Bulldogs',
    # Full names (older years)
    'Adelaide':         'Adelaide Crows',
    'Brisbane Lions':   'Brisbane Lions',
    'Carlton':          'Carlton Blues',
    'Collingwood':      'Collingwood Magpies',
    'Essendon':         'Essendon Bombers',
    'Fremantle':        'Fremantle Dockers',
    'GWS Giants':       'Greater Western Sydney Giants',
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
}

# ── Exact column indices (verified against live Footywire 2025 data) ──────────
# Row structure: Rk(0) | Team(1) | stat1(2) | stat2(3) | ...
BASIC_IDX = {
    'games':          2,
    'kicks_pg':       3,
    'handballs_pg':   4,
    'disposals_pg':   5,
    'marks_pg':       6,
    'goals_pg':       7,
    'goal_assists_pg':8,
    'inside_50s_pg':  9,
    'behinds_pg':     10,
    'tackles_pg':     11,   # T  (NOT hitouts — hitouts is idx 12)
    'hitouts_pg':     12,   # HO
    'frees_for_pg':   13,
    'frees_ag_pg':    14,
    'clearances_pg':  15,   # total clearances (also on adv page — use adv for CCL/SCL split)
    'clangers_pg':    16,
    'rebound_50s_pg': 17,
}

ADV_IDX = {
    'games':                  2,
    'cp_pg':                  3,   # CP
    'up_pg':                  4,   # UP
    'eff_disposals_pg':       5,   # ED
    'disposal_eff_pct':       6,   # DE%
    'cont_marks_pg':          7,   # CM
    'marks_i50_pg':           8,   # MI5
    'one_pct_pg':             9,   # 1%  (spoils / smothers / shepherds)
    'bounces_pg':             10,  # BO
    'clearances_adv_pg':      11,  # CL  (use this over basic; same value)
    'centre_cl_pg':           12,  # CCL
    'stoppage_cl_pg':         13,  # SCL
    'metres_gained_total':    14,  # MG  (season total — divide by games for per-game)
    'turnovers_pg':           15,  # TO
    'intercepts_pg':          16,  # ITC
    'tackles_i50_pg':         17,  # T50
}


def _safe_float(txt: str):
    try:
        return float(txt.replace(',', '').replace('%', '').strip())
    except (ValueError, AttributeError):
        return None


def _find_clean_table(soup, header_hints):
    for table in soup.find_all('table'):
        ths = [th.get_text(strip=True) for th in table.find_all('th')]
        if not any(h in ths for h in header_hints):
            continue
        tds = table.find_all('td')
        if tds and tds[0].get_text(strip=True) == 'Team':
            return table
    return None


def _parse_table(table, idx_map: dict) -> dict[str, dict]:
    results = {}
    for tr in table.find_all('tr'):
        cells = tr.find_all(['td', 'th'])
        if not cells:
            continue
        first = cells[0].get_text(strip=True)
        if not first.isdigit():
            continue   # skip header / sticky rows
        if len(cells) < 3:
            continue

        team_raw  = cells[1].get_text(strip=True)
        canonical = TEAM_MAP.get(team_raw)
        if not canonical:
            for k, v in TEAM_MAP.items():
                if k.lower() in team_raw.lower() or team_raw.lower() in k.lower():
                    canonical = v
                    break
        if not canonical:
            continue

        rec = {}
        for field, idx in idx_map.items():
            rec[field] = _safe_float(cells[idx].get_text(strip=True)) if idx < len(cells) else None
        results[canonical] = rec
    return results


def scrape_season_to_date(year: int, session: requests.Session) -> dict[str, dict]:
    """Scrape basic + advanced pages and return merged {team: stats}."""
    basic_data: dict[str, dict] = {}
    try:
        r = session.get(BASE_URL, params={'year': year}, headers=HEADERS, timeout=15)
        r.raise_for_status()
        t = _find_clean_table(BeautifulSoup(r.text, 'lxml'), ['I50', 'G', 'K'])
        if t:
            basic_data = _parse_table(t, BASIC_IDX)
        else:
            print(f'  [no basic table for {year}]')
    except Exception as e:
        print(f'  [basic error: {e}]')
    time.sleep(1.0)

    adv_data: dict[str, dict] = {}
    try:
        r = session.get(BASE_URL, params={'year': year, 'advv': 'Y'}, headers=HEADERS, timeout=15)
        r.raise_for_status()
        t = _find_clean_table(BeautifulSoup(r.text, 'lxml'), ['CP', 'CL', 'MI5'])
        if t:
            adv_data = _parse_table(t, ADV_IDX)
        else:
            print(f'  [no adv table for {year}]')
    except Exception as e:
        print(f'  [adv error: {e}]')

    # Merge
    merged = {}
    for team in set(basic_data) | set(adv_data):
        rec = {}
        for d in (basic_data.get(team, {}), adv_data.get(team, {})):
            for k, v in d.items():
                if rec.get(k) is None:
                    rec[k] = v
        # Prefer adv clearances if available
        if rec.get('clearances_adv_pg') is not None:
            rec['clearances_pg'] = rec.pop('clearances_adv_pg')
        else:
            rec.pop('clearances_adv_pg', None)
        merged[team] = rec
    return merged


FIELDNAMES = [
    'season', 'round_number', 'team_name',
    'games',
    # Basic
    'kicks_pg', 'handballs_pg', 'disposals_pg', 'marks_pg',
    'goals_pg', 'behinds_pg', 'goal_assists_pg',
    'inside_50s_pg', 'rebound_50s_pg',
    'tackles_pg', 'hitouts_pg',
    'frees_for_pg', 'frees_ag_pg',
    'clearances_pg', 'clangers_pg',
    # Advanced
    'cp_pg', 'up_pg',
    'eff_disposals_pg', 'disposal_eff_pct',
    'cont_marks_pg', 'marks_i50_pg',
    'one_pct_pg', 'bounces_pg',
    'centre_cl_pg', 'stoppage_cl_pg',
    'metres_gained_total', 'turnovers_pg',
    'intercepts_pg', 'tackles_i50_pg',
    # Derived
    'goal_conv_pct',
    'kicking_ratio',
    'mg_pg',
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season',    type=int, required=True)
    parser.add_argument('--round',     type=int, required=True,
                        help='Round ENTERING (stats are from rounds played so far)')
    parser.add_argument('--overwrite', action='store_true',
                        help='Replace any existing rows for this season+round')
    parser.add_argument('--out',       default=str(SNAP_CSV))
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing rows if file exists
    existing_rows = []
    if out_path.exists():
        with open(out_path) as f:
            existing_rows = list(csv.DictReader(f))

    # Drop old rows for this season+round if overwriting
    if args.overwrite:
        existing_rows = [r for r in existing_rows
                         if not (int(r['season']) == args.season
                                 and int(r['round_number']) == args.round)]

    # Check if already scraped
    already = any(int(r['season']) == args.season
                  and int(r['round_number']) == args.round
                  for r in existing_rows)
    if already and not args.overwrite:
        print(f'Snapshot already exists for {args.season} R{args.round}. '
              f'Use --overwrite to replace.')
        return

    print(f'Scraping Footywire season-to-date stats for {args.season} '
          f'(entering R{args.round})...', flush=True)

    session = requests.Session()
    stats = scrape_season_to_date(args.season, session)

    if not stats:
        print('No data scraped.')
        return

    new_rows = []
    for team, rec in sorted(stats.items()):
        games = rec.get('games') or 1

        # Derived stats
        g  = rec.get('goals_pg')
        bh = rec.get('behinds_pg')
        if g is not None and bh is not None and (g + bh) > 0:
            rec['goal_conv_pct'] = round(g / (g + bh), 4)
        else:
            rec['goal_conv_pct'] = None

        k  = rec.get('kicks_pg')
        hb = rec.get('handballs_pg')
        if k is not None and hb is not None and (k + hb) > 0:
            rec['kicking_ratio'] = round(k / (k + hb), 4)
        else:
            rec['kicking_ratio'] = None

        # MG on Footywire averages page is already a per-game figure (like all other stats).
        # Do NOT divide by games — store directly.
        mg = rec.get('metres_gained_total')
        rec['mg_pg'] = round(mg, 1) if mg is not None else None

        row = {'season': args.season, 'round_number': args.round, 'team_name': team}
        for f in FIELDNAMES[3:]:   # skip season/round/team_name
            row[f] = rec.get(f)
        new_rows.append(row)

    # Write
    all_rows = existing_rows + new_rows
    with open(out_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_rows)

    print(f'Saved {len(new_rows)} teams for {args.season} R{args.round} '
          f'→ {out_path}  ({len(all_rows)} total rows)')

    # Quick sanity check
    print(f'\nSample (sorted by CP/game):')
    for r in sorted(new_rows, key=lambda x: -(float(x.get('cp_pg') or 0)))[:6]:
        print(f"  {r['team_name']:<40} "
              f"CP:{str(r.get('cp_pg','—')):>6}  "
              f"I50:{str(r.get('inside_50s_pg','—')):>5}  "
              f"MG:{str(r.get('mg_pg','—')):>6}  "
              f"DE%:{str(r.get('disposal_eff_pct','—')):>5}  "
              f"ITC:{str(r.get('intercepts_pg','—')):>5}  "
              f"HO:{str(r.get('hitouts_pg','—')):>5}")


if __name__ == '__main__':
    main()
