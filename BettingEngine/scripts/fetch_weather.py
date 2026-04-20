"""
scripts/fetch_weather.py

Fetch weather conditions for all matches in a given round and upsert into
the weather_conditions table.

Data sources:
  - Open-Meteo (free, no key)  — all Australian venues
  - MetService (NZ met service) — Auckland venues (Go Media Stadium)

The integration seam is fetch_weather_for_match().  To replace with an
agent/OpenClaw call, swap out that function's body only — the caller and
DB upsert logic remain unchanged.

Usage:
    python scripts/fetch_weather.py --season 2026 --round 7
    python scripts/fetch_weather.py --season 2026 --round 7 --mock-clear
    python scripts/fetch_weather.py --season 2026 --round 7 --dry-run
"""

import argparse
import sqlite3
import sys
import urllib.request
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'data' / 'model.db'

sys.path.insert(0, str(ROOT))
from pricing.tier7_environment import classify_condition, compute_dew_risk

# Auckland venue IDs — use MetService instead of Open-Meteo
AUCKLAND_VENUE_IDS = {3}   # Go Media Stadium


# ---------------------------------------------------------------------------
# Open-Meteo fetch
# ---------------------------------------------------------------------------
# OpenClaw integration note:
# fetch_weather_for_match() calls either _fetch_open_meteo() or
# _fetch_metservice() depending on venue.  To replace with an agent call:
#   1. Remove the urllib.request call below.
#   2. Replace with your agent/OpenClaw invocation that returns the same
#      standardised dict (temp_c, dew_point_c, humidity_pct, wind_kmh,
#      precipitation_mm).
#   3. The classification and DB upsert logic above is unchanged.

def _fetch_open_meteo(lat: float, lng: float, date: str, kickoff_hour: int) -> dict:
    """
    Fetch hourly weather from Open-Meteo for (lat, lng) on date.
    Extract the hour matching kickoff_hour (0–23).

    API: https://api.open-meteo.com/v1/forecast
    Hourly variables: temperature_2m, dew_point_2m, relative_humidity_2m,
                      wind_speed_10m, precipitation
    Timezone: auto (returns data in the venue's local timezone)

    Returns dict: temp_c, dew_point_c, humidity_pct, wind_kmh, precipitation_mm
    Raises RuntimeError on API failure.
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lng}"
        f"&hourly=temperature_2m,dew_point_2m,relative_humidity_2m,"
        f"wind_speed_10m,precipitation"
        f"&timezone=auto"
        f"&start_date={date}&end_date={date}"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        raise RuntimeError(f'Open-Meteo request failed: {exc}') from exc

    hourly = data.get('hourly', {})
    times  = hourly.get('time', [])

    # Find index for kickoff_hour
    idx = None
    for i, t in enumerate(times):
        # t is like '2026-04-10T19:00'
        try:
            h = int(t.split('T')[1].split(':')[0])
        except (IndexError, ValueError):
            continue
        if h == kickoff_hour:
            idx = i
            break

    if idx is None:
        # Fallback: use midday if exact hour not found
        for i, t in enumerate(times):
            try:
                h = int(t.split('T')[1].split(':')[0])
            except (IndexError, ValueError):
                continue
            if h == 12:
                idx = i
                break
        if idx is None:
            idx = 0

    def _val(key):
        vals = hourly.get(key, [])
        v = vals[idx] if idx < len(vals) else None
        return float(v) if v is not None else None

    return {
        'temp_c':           _val('temperature_2m'),
        'dew_point_c':      _val('dew_point_2m'),
        'humidity_pct':     _val('relative_humidity_2m'),
        'wind_kmh':         _val('wind_speed_10m'),
        'precipitation_mm': _val('precipitation'),
        'data_source':      'open_meteo',
    }


def _fetch_metservice(lat: float, lng: float, date: str, kickoff_hour: int) -> dict:
    """
    Fetch hourly weather from MetService for Auckland venues.

    API: https://api.metservice.com/publicforecast/v1/forecast
    Parses the first matching forecast period that covers kickoff_hour.

    Falls back to Open-Meteo silently if MetService is unavailable.
    """
    url = f"https://api.metservice.com/publicforecast/v1/forecast?lat={lat}&lon={lng}"
    try:
        req = urllib.request.Request(url, headers={'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception:
        # MetService unavailable — fall back to Open-Meteo
        return _fetch_open_meteo(lat, lng, date, kickoff_hour)

    # MetService response: look for a 'forecasts' or 'data' array with hourly entries.
    # Structure varies; try common keys.
    entries = (
        data.get('forecasts')
        or data.get('data', {}).get('forecasts')
        or []
    )

    best = None
    for entry in entries:
        # Each entry may have a 'time' ISO string and weather fields
        t = entry.get('time') or entry.get('dateTimeISO') or ''
        try:
            h = int(str(t).split('T')[1].split(':')[0]) if 'T' in str(t) else -1
        except (IndexError, ValueError):
            h = -1
        if h == kickoff_hour:
            best = entry
            break
    if best is None and entries:
        best = entries[0]   # fallback: use first available period

    if not best:
        return _fetch_open_meteo(lat, lng, date, kickoff_hour)

    def _get(*keys):
        for k in keys:
            v = best.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return None

    return {
        'temp_c':           _get('temp', 'temperature', 'air_temperature'),
        'dew_point_c':      _get('dew_point', 'dewPoint', 'dew_point_c'),
        'humidity_pct':     _get('humidity', 'relative_humidity', 'relativeHumidity'),
        'wind_kmh':         _get('wind_speed', 'windSpeed', 'wind_kmh'),
        'precipitation_mm': _get('rain', 'precipitation', 'precip_mm'),
        'data_source':      'metservice',
    }


# ---------------------------------------------------------------------------
# Main fetch integration seam
# ---------------------------------------------------------------------------

def fetch_weather_for_match(
    match_id: int,
    venue_id: int,
    venue_name: str,
    lat: float,
    lng: float,
    kickoff_datetime: str,
) -> dict:
    """
    Fetch raw weather for a single match and return a standardised dict.

    This is the OpenClaw integration seam.  The returned dict must contain:
        temp_c, dew_point_c, humidity_pct, wind_kmh, precipitation_mm, data_source

    To replace with an agent call:
        1. Remove the _fetch_open_meteo / _fetch_metservice calls.
        2. Return the same keys from your agent's weather response.

    Args:
        match_id:         DB match_id (for logging only).
        venue_id:         DB venue_id (determines data source).
        venue_name:       Human-readable name (for logging only).
        lat, lng:         Venue coordinates.
        kickoff_datetime: ISO local datetime, e.g. '2026-04-10T19:50:00'.

    Returns raw weather dict (without classification or delta).
    Raises RuntimeError if all sources fail.
    """
    try:
        dt   = datetime.fromisoformat(kickoff_datetime)
        date = dt.strftime('%Y-%m-%d')
        hour = dt.hour
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f'Cannot parse kickoff_datetime {kickoff_datetime!r}: {exc}') from exc

    if venue_id in AUCKLAND_VENUE_IDS:
        return _fetch_metservice(lat, lng, date, hour)
    else:
        return _fetch_open_meteo(lat, lng, date, hour)


# ---------------------------------------------------------------------------
# Classification + upsert
# ---------------------------------------------------------------------------

def _mock_clear_row(match_id: int, venue_id: int, kickoff_datetime: str) -> dict:
    return {
        'match_id':         match_id,
        'venue_id':         venue_id,
        'kickoff_time':     kickoff_datetime,
        'temp_c':           20.0,
        'dew_point_c':      5.0,
        'humidity_pct':     40.0,
        'wind_kmh':         5.0,
        'precipitation_mm': 0.0,
        'condition_type':   'clear',
        'dew_risk':         0,
        'totals_delta':     0.0,
        'data_source':      'mock_clear',
    }


def build_weather_row(
    match_id: int,
    venue_id: int,
    kickoff_datetime: str,
    raw: dict,
) -> dict:
    """Classify raw weather data and assemble the full DB row."""
    temp_c           = raw.get('temp_c') or 0.0
    dew_point_c      = raw.get('dew_point_c') or 0.0
    wind_kmh         = raw.get('wind_kmh') or 0.0
    precipitation_mm = raw.get('precipitation_mm') or 0.0

    dew_risk_bool = compute_dew_risk(kickoff_datetime, temp_c, dew_point_c)
    condition_type, totals_delta = classify_condition(precipitation_mm, wind_kmh, dew_risk_bool)

    return {
        'match_id':         match_id,
        'venue_id':         venue_id,
        'kickoff_time':     kickoff_datetime,
        'temp_c':           round(temp_c, 1) if temp_c is not None else None,
        'dew_point_c':      round(dew_point_c, 1) if dew_point_c is not None else None,
        'humidity_pct':     round(raw.get('humidity_pct') or 0.0, 1),
        'wind_kmh':         round(wind_kmh, 1),
        'precipitation_mm': round(precipitation_mm, 2),
        'condition_type':   condition_type,
        'dew_risk':         int(dew_risk_bool),
        'totals_delta':     totals_delta,
        'data_source':      raw.get('data_source', 'open_meteo'),
    }


def upsert_weather(conn: sqlite3.Connection, row: dict, dry_run: bool = False) -> None:
    if dry_run:
        return
    conn.execute(
        """
        INSERT INTO weather_conditions
            (match_id, venue_id, kickoff_time, temp_c, dew_point_c, humidity_pct,
             wind_kmh, precipitation_mm, condition_type, dew_risk, totals_delta,
             data_source, fetched_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(match_id) DO UPDATE SET
            venue_id          = excluded.venue_id,
            kickoff_time      = excluded.kickoff_time,
            temp_c            = excluded.temp_c,
            dew_point_c       = excluded.dew_point_c,
            humidity_pct      = excluded.humidity_pct,
            wind_kmh          = excluded.wind_kmh,
            precipitation_mm  = excluded.precipitation_mm,
            condition_type    = excluded.condition_type,
            dew_risk          = excluded.dew_risk,
            totals_delta      = excluded.totals_delta,
            data_source       = excluded.data_source,
            fetched_at        = CURRENT_TIMESTAMP
        """,
        (
            row['match_id'], row['venue_id'], row['kickoff_time'],
            row['temp_c'], row['dew_point_c'], row['humidity_pct'],
            row['wind_kmh'], row['precipitation_mm'], row['condition_type'],
            row['dew_risk'], row['totals_delta'], row['data_source'],
        ),
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Fetch T7 weather for a round')
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--round', type=int, required=True, dest='round_number')
    parser.add_argument('--mock-clear', action='store_true',
                        help='Skip API calls — insert clear conditions for all games')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    matches = conn.execute(
        """
        SELECT m.match_id, m.venue_id, m.kickoff_datetime,
               v.venue_name, v.lat, v.lng
        FROM matches m
        LEFT JOIN venues v ON v.venue_id = m.venue_id
        WHERE m.season = ? AND m.round_number = ?
        ORDER BY m.match_date, m.match_id
        """,
        (args.season, args.round_number),
    ).fetchall()

    if not matches:
        print(f'No matches found for S{args.season} R{args.round_number}', file=sys.stderr)
        sys.exit(1)

    print(f'Fetching T7 weather for S{args.season} R{args.round_number} '
          f'({len(matches)} games)'
          + (' [mock-clear]' if args.mock_clear else '')
          + (' [dry-run]' if args.dry_run else ''))
    print()

    ok = 0
    for m in matches:
        mid        = m['match_id']
        vid        = m['venue_id']
        vname      = m['venue_name'] or f'venue_id={vid}'
        lat        = m['lat']
        lng        = m['lng']
        kickoff    = m['kickoff_datetime']

        if lat is None or lng is None:
            print(f'  match={mid}  {vname}: SKIP — no lat/lng in venues table')
            continue

        try:
            if args.mock_clear:
                row = _mock_clear_row(mid, vid, kickoff)
            else:
                raw = fetch_weather_for_match(mid, vid, vname, lat, lng, kickoff)
                row = build_weather_row(mid, vid, kickoff, raw)

            upsert_weather(conn, row, dry_run=args.dry_run)

            dew_str = ' [dew]' if row['dew_risk'] else ''
            print(f'  match={mid}  {vname:<32}  '
                  f'{row["condition_type"]:<28}  '
                  f'T={row["temp_c"]}°C  '
                  f'Dp={row["dew_point_c"]}°C  '
                  f'W={row["wind_kmh"]}km/h  '
                  f'P={row["precipitation_mm"]}mm  '
                  f'Δtot={row["totals_delta"]:+.1f}{dew_str}  '
                  f'[{row["data_source"]}]')
            ok += 1

        except Exception as exc:
            print(f'  match={mid}  {vname}: ERROR — {exc}')

    if not args.dry_run:
        conn.commit()

    print()
    print(f'Done — {ok}/{len(matches)} weather rows written.')
    conn.close()


if __name__ == '__main__':
    main()
