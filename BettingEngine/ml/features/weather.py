#!/usr/bin/env python3
"""
ml/features/weather.py

Session 6 — Add weather conditions at kickoff to the game log.

Uses Open-Meteo historical API (free, no key required).
Results are cached locally so the API is never hit twice for the same game.

For each game:
  - Looks up venue lat/lng from venues.csv
  - Fetches hourly weather for that date at that location
  - Extracts conditions at kickoff hour
  - Adds rain_mm, wind_kmh, wind_gusts_kmh, temp_c

USAGE
-----
    python ml/features/weather.py \
        --game-log ml/results/game_log_elo.csv \
        --venues   data/import/venues.csv \
        --out      ml/results/game_log_weather.csv \
        --cache    ml/results/weather_cache.json
"""

import argparse
import csv
import json
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

MIN_SAMPLE = 1   # always fetch if we have lat/lng
API_BASE   = 'https://archive-api.open-meteo.com/v1/archive'
SLEEP_SEC  = 0.15  # polite rate limit between API calls


def load_venues(venues_path: str) -> dict:
    """Returns dict: venue_name → {lat, lng}"""
    venues = {}
    with open(venues_path) as f:
        for row in csv.DictReader(f):
            name = row['venue'].strip()
            try:
                venues[name] = {
                    'lat': float(row['lat']),
                    'lng': float(row['lng']),
                }
            except (ValueError, KeyError):
                pass
    return venues


def load_cache(cache_path: str) -> dict:
    p = Path(cache_path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict, cache_path: str):
    with open(cache_path, 'w') as f:
        json.dump(cache, f)


def fetch_weather(lat: float, lng: float, date: str) -> dict | None:
    """
    Fetch hourly weather from Open-Meteo for a single date and location.
    Returns dict keyed by hour (0-23) → {rain, wind, gusts, temp}
    """
    params = {
        'latitude':        lat,
        'longitude':       lng,
        'start_date':      date,
        'end_date':        date,
        'hourly':          'precipitation,wind_speed_10m,wind_gusts_10m,temperature_2m',
        'wind_speed_unit': 'kmh',
        'timezone':        'auto',
    }
    url = API_BASE + '?' + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"    WARNING: API error for {date} lat={lat} lng={lng}: {e}")
        return None

    try:
        hours     = data['hourly']['time']           # list of "YYYY-MM-DDTHH:00"
        rain      = data['hourly']['precipitation']
        wind      = data['hourly']['wind_speed_10m']
        gusts     = data['hourly']['wind_gusts_10m']
        temp      = data['hourly']['temperature_2m']
    except KeyError:
        return None

    result = {}
    for i, ts in enumerate(hours):
        hour = int(ts[11:13])
        result[hour] = {
            'rain_mm':        rain[i],
            'wind_kmh':       wind[i],
            'wind_gusts_kmh': gusts[i],
            'temp_c':         temp[i],
        }
    return result


def get_weather_at_kickoff(cache: dict, lat: float, lng: float,
                            date: str, hour: int) -> dict:
    """
    Return weather at kickoff hour. Uses cache keyed by "lat,lng,date".
    Fetches from API if not cached.
    """
    cache_key = f"{lat},{lng},{date}"
    if cache_key not in cache:
        hourly = fetch_weather(lat, lng, date)
        cache[cache_key] = hourly
        time.sleep(SLEEP_SEC)

    hourly = cache.get(cache_key)
    if not hourly:
        return {'rain_mm': '', 'wind_kmh': '', 'wind_gusts_kmh': '', 'temp_c': ''}

    # Try kickoff hour, fall back to nearest available
    if hour in hourly:
        return hourly[hour]
    # Fallback: closest hour
    closest = min(hourly.keys(), key=lambda h: abs(h - hour))
    return hourly[closest]


def main():
    parser = argparse.ArgumentParser(description='Add weather features to game log')
    parser.add_argument('--game-log', default=str(ROOT / 'ml/results/game_log_elo.csv'))
    parser.add_argument('--venues',   default=str(ROOT / 'data/import/venues.csv'))
    parser.add_argument('--out',      default=str(ROOT / 'ml/results/game_log_weather.csv'))
    parser.add_argument('--cache',    default=str(ROOT / 'ml/results/weather_cache.json'))
    args = parser.parse_args()

    for p in [args.game_log, args.venues]:
        if not Path(p).exists():
            print(f"ERROR: not found: {p}", file=sys.stderr)
            sys.exit(1)

    print("Loading venues ...")
    venues = load_venues(args.venues)
    print(f"  {len(venues)} venues loaded")

    print("Loading game log ...")
    with open(args.game_log) as f:
        rows = list(csv.DictReader(f))
    print(f"  {len(rows)} games")

    print("Loading weather cache ...")
    cache = load_cache(args.cache)
    print(f"  {len(cache)} entries cached")

    # Count how many we'll need to fetch
    need_fetch = sum(
        1 for r in rows
        if r.get('venue') in venues
        and f"{venues[r['venue']]['lat']},{venues[r['venue']]['lng']},{r['date']}" not in cache
    )
    no_venue = sum(1 for r in rows if r.get('venue') not in venues)
    print(f"  Need to fetch: {need_fetch}  No venue match: {no_venue}")
    print(f"  Estimated time: ~{need_fetch * SLEEP_SEC / 60:.1f} min")

    print("\nFetching weather ...")
    out_rows = []
    fetched = 0

    for i, r in enumerate(rows):
        venue = r.get('venue', '').strip()
        loc   = venues.get(venue)

        if loc:
            hour = int(r.get('kickoff_hour', 19))
            w = get_weather_at_kickoff(
                cache, loc['lat'], loc['lng'], r['date'], hour
            )
            if w.get('rain_mm') == '' and f"{loc['lat']},{loc['lng']},{r['date']}" not in cache:
                fetched += 1
        else:
            w = {'rain_mm': '', 'wind_kmh': '', 'wind_gusts_kmh': '', 'temp_c': ''}

        row = dict(r)
        row.update({
            'rain_mm':        w.get('rain_mm', ''),
            'wind_kmh':       w.get('wind_kmh', ''),
            'wind_gusts_kmh': w.get('wind_gusts_kmh', ''),
            'temp_c':         w.get('temp_c', ''),
        })
        out_rows.append(row)

        # Save cache every 100 games
        if i % 100 == 0 and i > 0:
            save_cache(cache, args.cache)
            print(f"  {i}/{len(rows)} processed ...")

    # Final cache save
    save_cache(cache, args.cache)

    # Summary
    has_weather = [r for r in out_rows if r['rain_mm'] != '']
    print(f"\n  Games with weather data: {len(has_weather)}/{len(out_rows)}")

    if has_weather:
        rain_vals = [float(r['rain_mm']) for r in has_weather]
        wind_vals = [float(r['wind_kmh']) for r in has_weather]
        wet_games = sum(1 for v in rain_vals if v > 2.0)
        print(f"  Wet games (rain > 2mm):  {wet_games}  ({wet_games/len(has_weather)*100:.1f}%)")
        print(f"  Rain range:  {min(rain_vals):.1f} – {max(rain_vals):.1f} mm")
        print(f"  Wind range:  {min(wind_vals):.1f} – {max(wind_vals):.1f} km/h")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out_rows[0].keys())
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\n  Written {len(out_rows)} rows → {out}")
    print("\nDone.")


if __name__ == '__main__':
    main()
