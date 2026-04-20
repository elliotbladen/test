#!/usr/bin/env python3
"""
scripts/load_geo_data.py

One-time loader for static geographic data used by Tier 3 travel calculations.

Populates:
  - venues.lat, venues.lng  (for all known NRL venues)
  - team_home_bases          (one row per NRL team)

Coordinates are approximate centroids of each venue or team home city.
Safe to re-run: uses INSERT OR REPLACE / UPDATE logic.

USAGE
-----
    cd /path/to/Betting_model
    python scripts/load_geo_data.py [--dry-run] [--settings config/settings.yaml]
"""

import argparse
import sqlite3
import sys
import yaml
from pathlib import Path

# =============================================================================
# VENUE COORDINATES
# key = venue_name (must match exactly what is in the venues table)
# value = (lat, lng, human-readable city/location note)
# =============================================================================
VENUE_COORDS = {
    # NSW
    'Accor Stadium':                    (-33.847,  151.063, 'Sydney Olympic Park, NSW'),
    'Allianz Stadium':                  (-33.891,  151.225, 'Moore Park, Sydney NSW'),
    'CommBank Stadium':                 (-33.808,  150.986, 'Parramatta, NSW'),
    'BlueBet Stadium':                  (-33.749,  150.688, 'Penrith, NSW'),
    'McDonald Jones Stadium':           (-32.916,  151.773, 'Newcastle, NSW'),
    'PointsBet Stadium':                (-34.028,  151.154, 'Cronulla, NSW'),
    'Sharks Stadium':                   (-34.028,  151.154, 'Cronulla, NSW'),
    '4 Pines Park':                     (-33.763,  151.269, 'Brookvale, NSW'),
    'Jubilee Stadium':                  (-33.961,  151.131, 'Kogarah, NSW'),
    'Leichhardt Oval':                  (-33.878,  151.160, 'Leichhardt, NSW'),
    'Belmore Sports Ground':            (-33.918,  151.081, 'Belmore, NSW'),
    'Campbelltown Sports Stadium':      (-34.078,  150.813, 'Campbelltown, NSW'),
    'WIN Stadium':                      (-34.432,  150.893, 'Wollongong, NSW'),
    'SCG':                              (-33.892,  151.224, 'Moore Park, Sydney NSW'),
    'Scully Park':                      (-31.097,  150.921, 'Tamworth, NSW'),
    'C.ex Coffs International Stadium': (-30.301,  153.123, 'Coffs Harbour, NSW'),
    'Carrington Park':                  (-33.418,  149.575, 'Bathurst, NSW'),
    'Glen Willow Regional Sports Stadium': (-32.588, 149.592, 'Mudgee, NSW'),
    'Salter Oval':                      (-24.856,  152.342, 'Bundaberg, QLD'),  # noted NSW in sched but QLD geographically
    'Polytec Stadium':                  (-33.878,  151.160, 'Leichhardt, NSW'),  # former Leichhardt Oval name

    # QLD
    'Suncorp Stadium':                  (-27.465,  153.009, 'Brisbane, QLD'),
    'Cbus Super Stadium':               (-28.073,  153.381, 'Robina, Gold Coast QLD'),
    'Kayo Stadium':                     (-27.229,  153.105, 'Redcliffe, QLD'),
    'Queensland Country Bank Stadium':  (-19.258,  146.826, 'Townsville, QLD'),
    'The Gabba':                        (-27.485,  153.038, 'Brisbane, QLD'),
    'Sunshine Coast Stadium':           (-26.678,  153.071, 'Bokarina, Sunshine Coast QLD'),
    'McDonalds Park':                   (-27.229,  153.105, 'Redcliffe, QLD'),  # alternate Dolphins venue

    # VIC
    'AAMI Park':                        (-37.820,  144.984, 'Melbourne, VIC'),
    'Marvel Stadium':                   (-37.816,  144.947, 'Docklands, Melbourne VIC'),

    # ACT
    'GIO Stadium Canberra':             (-35.244,  149.100, 'Canberra, ACT'),

    # WA
    'Optus Stadium':                    (-31.951,  115.889, 'East Perth, WA'),
    'HBF Park':                         (-31.958,  115.864, 'Perth, WA'),

    # NT
    'TIO Stadium':                      (-12.446,  130.842, 'Darwin, NT'),

    # NZ
    'Go Media Stadium':                 (-36.921,  174.809, 'Mt Smart, Auckland NZ'),
    'FMG Stadium':                      (-37.777,  175.280, 'Hamilton, Waikato NZ'),
    'Sky Stadium':                      (-41.285,  174.779, 'Wellington, NZ'),
    'McLean Park':                      (-39.493,  176.914, 'Napier, NZ'),
    'Apollo Projects Stadium':          (-43.540,  172.528, 'Christchurch, NZ'),

    # USA
    'Allegiant Stadium':                ( 36.091, -115.184, 'Las Vegas, Nevada USA'),
}

# =============================================================================
# TEAM HOME BASES
# key = team_name (must match teams.team_name exactly)
# value = (city, lat, lng, notes)
# Home base = team's primary home venue / training base.
# Used as the origin point for computing travel distance to each game's venue.
# =============================================================================
TEAM_HOME_BASES = {
    'Penrith Panthers':                 ('Penrith',     -33.749,  150.688, 'BlueBet Stadium, Penrith NSW'),
    'Brisbane Broncos':                 ('Brisbane',    -27.465,  153.009, 'Suncorp Stadium, Brisbane QLD'),
    'New Zealand Warriors':             ('Auckland',    -36.921,  174.809, 'Go Media Stadium, Auckland NZ'),
    'Melbourne Storm':                  ('Melbourne',   -37.820,  144.984, 'AAMI Park, Melbourne VIC'),
    'Newcastle Knights':                ('Newcastle',   -32.916,  151.773, 'McDonald Jones Stadium, Newcastle NSW'),
    'Sydney Roosters':                  ('Sydney',      -33.891,  151.225, 'Allianz Stadium, Sydney NSW'),
    'Canberra Raiders':                 ('Canberra',    -35.244,  149.100, 'GIO Stadium, Canberra ACT'),
    'Cronulla-Sutherland Sharks':       ('Cronulla',    -34.028,  151.154, 'PointsBet Stadium, Cronulla NSW'),
    'Gold Coast Titans':                ('Gold Coast',  -28.073,  153.381, 'Cbus Super Stadium, Gold Coast QLD'),
    'Canterbury-Bankstown Bulldogs':    ('Canterbury',  -33.918,  151.081, 'Belmore area, Sydney NSW'),
    'St. George Illawarra Dragons':     ('Wollongong',  -34.432,  150.893, 'WIN Stadium, Wollongong NSW'),
    'North Queensland Cowboys':         ('Townsville',  -19.258,  146.826, 'Queensland Country Bank Stadium, Townsville QLD'),
    'Dolphins':                         ('Redcliffe',   -27.229,  153.105, 'Kayo Stadium, Redcliffe QLD'),
    'South Sydney Rabbitohs':           ('Sydney',      -33.892,  151.224, 'Allianz Stadium area, Sydney NSW'),
    'Manly-Warringah Sea Eagles':       ('Brookvale',   -33.763,  151.269, '4 Pines Park, Brookvale NSW'),
    'Wests Tigers':                     ('Parramatta',  -33.808,  150.986, 'CommBank Stadium, Parramatta NSW'),
    'Parramatta Eels':                  ('Parramatta',  -33.808,  150.986, 'CommBank Stadium, Parramatta NSW'),
}


def apply_migration(conn):
    """Run migration 006 DDL (idempotent — ALTER TABLE fails silently if column exists)."""
    try:
        conn.execute("ALTER TABLE venues ADD COLUMN lat REAL")
    except Exception:
        pass  # already exists
    try:
        conn.execute("ALTER TABLE venues ADD COLUMN lng REAL")
    except Exception:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_home_bases (
            home_base_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id       INTEGER NOT NULL UNIQUE REFERENCES teams(team_id),
            city          TEXT    NOT NULL,
            lat           REAL    NOT NULL,
            lng           REAL    NOT NULL,
            notes         TEXT,
            created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_home_bases_team_id ON team_home_bases(team_id)"
    )
    conn.commit()


def load_venue_coords(conn, dry_run: bool) -> tuple:
    written = skipped = not_found = 0
    venues = conn.execute("SELECT venue_id, venue_name FROM venues").fetchall()
    venue_map = {row['venue_name']: row['venue_id'] for row in venues}

    for venue_name, (lat, lng, location_note) in VENUE_COORDS.items():
        if venue_name not in venue_map:
            print(f"  NOT FOUND in DB: {venue_name!r}")
            not_found += 1
            continue

        venue_id = venue_map[venue_name]
        marker = '(dry-run)' if dry_run else 'written'
        if not dry_run:
            conn.execute(
                "UPDATE venues SET lat=?, lng=? WHERE venue_id=?",
                (lat, lng, venue_id)
            )
        print(f"  venue_id={venue_id:<3}  {venue_name:<45}  lat={lat:>9.4f}  lng={lng:>9.4f}  {marker}")
        written += 1

    if not dry_run:
        conn.commit()
    return written, not_found, skipped


def load_team_home_bases(conn, dry_run: bool) -> tuple:
    written = skipped = not_found = 0
    teams = conn.execute("SELECT team_id, team_name FROM teams").fetchall()
    team_map = {row['team_name']: row['team_id'] for row in teams}

    for team_name, (city, lat, lng, notes) in TEAM_HOME_BASES.items():
        if team_name not in team_map:
            print(f"  NOT FOUND in DB: {team_name!r}")
            not_found += 1
            continue

        team_id = team_map[team_name]
        marker = '(dry-run)' if dry_run else 'written'
        if not dry_run:
            conn.execute("""
                INSERT INTO team_home_bases (team_id, city, lat, lng, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(team_id) DO UPDATE SET
                    city  = excluded.city,
                    lat   = excluded.lat,
                    lng   = excluded.lng,
                    notes = excluded.notes
            """, (team_id, city, lat, lng, notes))
        print(f"  team_id={team_id:<3}  {team_name:<45}  {city:<15}  lat={lat:>9.4f}  lng={lng:>9.4f}  {marker}")
        written += 1

    if not dry_run:
        conn.commit()
    return written, not_found, skipped


def main():
    parser = argparse.ArgumentParser(description='Load geo data for Tier 3 travel calculations')
    parser.add_argument('--dry-run',  action='store_true')
    parser.add_argument('--settings', default='config/settings.yaml')
    args = parser.parse_args()

    with open(args.settings) as f:
        settings = yaml.safe_load(f)
    db_path = settings['database']['path']
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print(f"DB  : {db_path}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'WRITE'}")
    print()

    print("Applying migration 006 (idempotent)...")
    if not args.dry_run:
        apply_migration(conn)
        print("  Done.\n")
    else:
        print("  Skipped (dry-run).\n")

    print(f"{'─'*70}")
    print("Venue coordinates:")
    print(f"{'─'*70}")
    v_written, v_not_found, _ = load_venue_coords(conn, args.dry_run)
    print(f"{'─'*70}")
    print(f"  Written={v_written}  NotFound={v_not_found}\n")

    print(f"{'─'*70}")
    print("Team home bases:")
    print(f"{'─'*70}")
    t_written, t_not_found, _ = load_team_home_bases(conn, args.dry_run)
    print(f"{'─'*70}")
    print(f"  Written={t_written}  NotFound={t_not_found}\n")

    # Verification
    if not args.dry_run:
        null_venues = conn.execute(
            "SELECT COUNT(*) FROM venues WHERE lat IS NULL"
        ).fetchone()[0]
        total_venues = conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0]
        print(f"Venues with coords: {total_venues - null_venues} / {total_venues}")

        hb_count = conn.execute("SELECT COUNT(*) FROM team_home_bases").fetchone()[0]
        team_count = conn.execute("SELECT COUNT(*) FROM teams WHERE league='NRL'").fetchone()[0]
        print(f"Team home bases:    {hb_count} / {team_count} NRL teams")

    conn.close()


if __name__ == '__main__':
    main()
