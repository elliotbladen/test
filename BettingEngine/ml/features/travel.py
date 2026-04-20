#!/usr/bin/env python3
"""
ml/features/travel.py

Session 2 — Add travel distances to the game log.

Reads ml/results/game_log.csv + data/import/venues.csv and produces
ml/results/game_log_travel.csv with travel km added for each team.

Each team's home base is either:
  1. Their designated home venue (from venues.csv team_home column)
  2. Fallback: the venue they play at most often in the dataset

Travel distance = haversine km from team home base to match venue.

OUTPUT COLUMNS ADDED
--------------------
    home_base_city      city of home team's home ground
    away_base_city      city of away team's home ground
    venue_city          city of the match venue
    home_travel_km      km home team travelled to this venue
    away_travel_km      km away team travelled to this venue
    travel_diff         away_travel_km - home_travel_km
    is_neutral_venue    1 if neither team is playing at their home ground

USAGE
-----
    python ml/features/travel.py
    python ml/features/travel.py \
        --game-log ml/results/game_log.csv \
        --venues   data/import/venues.csv \
        --out      ml/results/game_log_travel.csv
"""

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

GAME_LOG_DEFAULT = ROOT / 'ml'  / 'results' / 'game_log.csv'
VENUES_DEFAULT   = ROOT / 'data' / 'import'  / 'venues.csv'
OUT_DEFAULT      = ROOT / 'ml'  / 'results' / 'game_log_travel.csv'


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------

def haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return round(R * 2 * math.asin(math.sqrt(a)), 1)


# ---------------------------------------------------------------------------
# Load venues
# ---------------------------------------------------------------------------

def load_venues(venues_csv: str) -> dict:
    """
    Returns dict keyed by venue name:
        {venue: {'city': str, 'lat': float, 'lng': float, 'team_home': str}}
    """
    venues = {}
    with open(venues_csv) as f:
        for row in csv.DictReader(f):
            try:
                venues[row['venue']] = {
                    'city':      row['city'],
                    'lat':       float(row['lat']),
                    'lng':       float(row['lng']),
                    'team_home': row['team_home'].strip(),
                }
            except (ValueError, KeyError):
                continue
    return venues


# ---------------------------------------------------------------------------
# Derive team home bases
# ---------------------------------------------------------------------------

def build_team_home_bases(venues: dict, game_log: list[dict]) -> dict:
    """
    For each team, find their home base coordinates.

    Priority:
    1. Explicit team_home assignment in venues.csv
    2. Most frequently used home venue in the game log
    """
    # Build from explicit assignments first
    team_bases = {}
    for venue_name, v in venues.items():
        if v['team_home']:
            team_bases[v['team_home']] = {
                'venue': venue_name,
                'city':  v['city'],
                'lat':   v['lat'],
                'lng':   v['lng'],
            }

    # Fallback: most common home venue per team
    home_venue_counts = defaultdict(lambda: defaultdict(int))
    for row in game_log:
        home_venue_counts[row['home_team']][row['venue']] += 1

    for team, counts in home_venue_counts.items():
        if team not in team_bases:
            most_common = max(counts, key=counts.get)
            if most_common in venues:
                v = venues[most_common]
                team_bases[team] = {
                    'venue': most_common,
                    'city':  v['city'],
                    'lat':   v['lat'],
                    'lng':   v['lng'],
                }

    return team_bases


# ---------------------------------------------------------------------------
# Main enrichment
# ---------------------------------------------------------------------------

def enrich_with_travel(game_log: list[dict],
                       venues: dict,
                       team_bases: dict) -> list[dict]:
    missing_venues = set()
    missing_teams  = set()
    rows = []

    for g in game_log:
        venue_name = g['venue']
        home_team  = g['home_team']
        away_team  = g['away_team']

        venue_info     = venues.get(venue_name)
        home_base      = team_bases.get(home_team)
        away_base      = team_bases.get(away_team)

        if not venue_info:
            missing_venues.add(venue_name)

        if not home_base:
            missing_teams.add(home_team)
        if not away_base:
            missing_teams.add(away_team)

        if venue_info and home_base and away_base:
            home_travel = haversine_km(
                home_base['lat'], home_base['lng'],
                venue_info['lat'], venue_info['lng']
            )
            away_travel = haversine_km(
                away_base['lat'], away_base['lng'],
                venue_info['lat'], venue_info['lng']
            )
            travel_diff     = round(away_travel - home_travel, 1)
            is_neutral      = 1 if (home_travel > 50 and away_travel > 50) else 0
            home_base_city  = home_base['city']
            away_base_city  = away_base['city']
            venue_city      = venue_info['city']
        else:
            home_travel = away_travel = travel_diff = ''
            is_neutral      = ''
            home_base_city  = ''
            away_base_city  = ''
            venue_city      = venue_info['city'] if venue_info else ''

        row = dict(g)
        row.update({
            'home_base_city':  home_base_city,
            'away_base_city':  away_base_city,
            'venue_city':      venue_city,
            'home_travel_km':  home_travel,
            'away_travel_km':  away_travel,
            'travel_diff':     travel_diff,
            'is_neutral_venue': is_neutral,
        })
        rows.append(row)

    if missing_venues:
        print(f"\n  WARNING: {len(missing_venues)} venues not in venues.csv:")
        for v in sorted(missing_venues):
            print(f"    - {v}")
        print(f"  Travel will be blank for these games. Add them to data/import/venues.csv to fix.")

    if missing_teams:
        print(f"\n  WARNING: {len(missing_teams)} teams have no home base:")
        for t in sorted(missing_teams):
            print(f"    - {t}")

    return rows


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(rows: list[dict]):
    total    = len(rows)
    has_travel = [r for r in rows if r['home_travel_km'] != '']
    no_travel  = total - len(has_travel)

    print(f"\n  {'─'*55}")
    print(f"  Travel summary")
    print(f"  {'─'*55}")
    print(f"  Total games:           {total}")
    print(f"  Games with travel:     {len(has_travel)}")
    print(f"  Games missing travel:  {no_travel}")

    if has_travel:
        away_kms = [float(r['away_travel_km']) for r in has_travel]
        print(f"\n  Away team travel stats:")
        print(f"    Min:    {min(away_kms):.0f} km")
        print(f"    Median: {sorted(away_kms)[len(away_kms)//2]:.0f} km")
        print(f"    Max:    {max(away_kms):.0f} km")

        big_travel = [r for r in has_travel if float(r['away_travel_km']) > 1500]
        print(f"\n  Big travel games (away >1500km): {len(big_travel)}")
        shown = set()
        for r in big_travel[:8]:
            key = f"{r['away_team']} → {r['venue_city']}"
            if key not in shown:
                print(f"    {r['away_team']:<38} → {r['venue_city']:<15} "
                      f"{float(r['away_travel_km']):.0f} km")
                shown.add(key)

        neutral = [r for r in has_travel if r['is_neutral_venue'] == 1]
        print(f"\n  Neutral venue games: {len(neutral)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Add travel distances to game log')
    parser.add_argument('--game-log', default=str(GAME_LOG_DEFAULT))
    parser.add_argument('--venues',   default=str(VENUES_DEFAULT))
    parser.add_argument('--out',      default=str(OUT_DEFAULT))
    args = parser.parse_args()

    for path, label in [(args.game_log, 'game log'), (args.venues, 'venues CSV')]:
        if not Path(path).exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr)
            sys.exit(1)

    print(f"Loading game log ...")
    with open(args.game_log) as f:
        game_log = list(csv.DictReader(f))
    print(f"  {len(game_log)} games")

    print(f"Loading venues ...")
    venues = load_venues(args.venues)
    print(f"  {len(venues)} venues")

    print(f"Building team home bases ...")
    team_bases = build_team_home_bases(venues, game_log)
    print(f"  {len(team_bases)} teams mapped")
    for team, base in sorted(team_bases.items()):
        print(f"    {team:<40} → {base['city']} ({base['venue']})")

    print(f"\nCalculating travel distances ...")
    rows = enrich_with_travel(game_log, venues, team_bases)

    print_summary(rows)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n  Written {len(rows)} rows → {out}")
    print("\nDone.")


if __name__ == '__main__':
    main()
