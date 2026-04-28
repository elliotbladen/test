#!/usr/bin/env python3
"""
scripts/seed_afl_teams.py

Seeds AFL team home base coordinates (for Tier 3 travel calculation),
links teams to their primary venues, and initialises ELO ratings.

Run once after migration 017_afl_foundation.sql.

USAGE
-----
    python3 scripts/seed_afl_teams.py
    python3 scripts/seed_afl_teams.py --db data/model.db
"""

import argparse
import sqlite3
from pathlib import Path

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'data' / 'model.db'

# ---------------------------------------------------------------------------
# AFL team home bases — city coordinates for travel calculation (Tier 3)
# ---------------------------------------------------------------------------
AFL_HOME_BASES = {
    'Adelaide Crows':              {'city': 'Adelaide',    'lat': -34.9285, 'lng': 138.6007},
    'Brisbane Lions':              {'city': 'Brisbane',    'lat': -27.4698, 'lng': 153.0251},
    'Carlton Blues':               {'city': 'Melbourne',   'lat': -37.8136, 'lng': 144.9631},
    'Collingwood Magpies':         {'city': 'Melbourne',   'lat': -37.8136, 'lng': 144.9631},
    'Essendon Bombers':            {'city': 'Melbourne',   'lat': -37.8136, 'lng': 144.9631},
    'Fremantle Dockers':           {'city': 'Perth',       'lat': -31.9505, 'lng': 115.8605},
    'Geelong Cats':                {'city': 'Geelong',     'lat': -38.1499, 'lng': 144.3617},
    'Gold Coast Suns':             {'city': 'Gold Coast',  'lat': -28.0167, 'lng': 153.4000},
    'Greater Western Sydney Giants':{'city': 'Sydney',     'lat': -33.8688, 'lng': 151.2093},
    'Hawthorn Hawks':              {'city': 'Melbourne',   'lat': -37.8136, 'lng': 144.9631},
    'Melbourne Demons':            {'city': 'Melbourne',   'lat': -37.8136, 'lng': 144.9631},
    'North Melbourne Kangaroos':   {'city': 'Melbourne',   'lat': -37.8136, 'lng': 144.9631},
    'Port Adelaide Power':         {'city': 'Adelaide',    'lat': -34.9285, 'lng': 138.6007},
    'Richmond Tigers':             {'city': 'Melbourne',   'lat': -37.8136, 'lng': 144.9631},
    'St Kilda Saints':             {'city': 'Melbourne',   'lat': -37.8136, 'lng': 144.9631},
    'Sydney Swans':                {'city': 'Sydney',      'lat': -33.8688, 'lng': 151.2093},
    'West Coast Eagles':           {'city': 'Perth',       'lat': -31.9505, 'lng': 115.8605},
    'Western Bulldogs':            {'city': 'Melbourne',   'lat': -37.8136, 'lng': 144.9631},
}

# ---------------------------------------------------------------------------
# AFL venue coordinates (for travel calculation to venue)
# ---------------------------------------------------------------------------
AFL_VENUE_COORDS = {
    'MCG':                   {'lat': -37.8200, 'lng': 144.9834},
    'Marvel Stadium':        {'lat': -37.8165, 'lng': 144.9476},
    'Adelaide Oval':         {'lat': -34.9158, 'lng': 138.5963},
    'Optus Stadium':         {'lat': -31.9510, 'lng': 115.8883},
    'GMHBA Stadium':         {'lat': -38.1554, 'lng': 144.3550},
    'Gabba':                 {'lat': -27.4858, 'lng': 153.0381},
    'Engie Stadium':         {'lat': -33.8474, 'lng': 151.0046},
    'SCG':                   {'lat': -33.8914, 'lng': 151.2246},
    'People First Stadium':  {'lat': -28.0034, 'lng': 153.3946},
    'UTAS Stadium':          {'lat': -41.4305, 'lng': 147.1386},
    'Blundestone Arena':     {'lat': -42.8821, 'lng': 147.3272},
    'Norwood Oval':          {'lat': -34.9212, 'lng': 138.6280},
    'TIO Traeger Park':      {'lat': -23.6980, 'lng': 133.8807},
    'Mars Stadium':          {'lat': -37.5472, 'lng': 143.8405},
    'Cazalys Stadium':       {'lat': -16.9186, 'lng': 145.7781},
}

# ---------------------------------------------------------------------------
# AFL team primary venues
# ---------------------------------------------------------------------------
AFL_PRIMARY_VENUES = {
    'Adelaide Crows':               'Adelaide Oval',
    'Brisbane Lions':               'Gabba',
    'Carlton Blues':                'Marvel Stadium',
    'Collingwood Magpies':          'MCG',
    'Essendon Bombers':             'Marvel Stadium',
    'Fremantle Dockers':            'Optus Stadium',
    'Geelong Cats':                 'GMHBA Stadium',
    'Gold Coast Suns':              'People First Stadium',
    'Greater Western Sydney Giants':'Engie Stadium',
    'Hawthorn Hawks':               'MCG',
    'Melbourne Demons':             'MCG',
    'North Melbourne Kangaroos':    'Marvel Stadium',
    'Port Adelaide Power':          'Adelaide Oval',
    'Richmond Tigers':              'MCG',
    'St Kilda Saints':              'Marvel Stadium',
    'Sydney Swans':                 'SCG',
    'West Coast Eagles':            'Optus Stadium',
    'Western Bulldogs':             'Marvel Stadium',
}

# ---------------------------------------------------------------------------
# Initial ELO ratings (approximate — based on 2023-2025 ladder positions)
# All start at 1500 baseline; adjust based on historical performance.
# Scale: top team ~1620, bottom team ~1380.
# ---------------------------------------------------------------------------
AFL_INITIAL_ELO = {
    'Brisbane Lions':               1620,  # back-to-back premiers 2023-2024
    'Geelong Cats':                 1600,  # perennial contender
    'Collingwood Magpies':          1590,  # 2023 premiers
    'Sydney Swans':                 1570,  # 2024 premiers
    'Carlton Blues':                1545,
    'Greater Western Sydney Giants':1540,
    'Hawthorn Hawks':               1530,
    'Port Adelaide Power':          1520,
    'Western Bulldogs':             1510,
    'Melbourne Demons':             1505,
    'Fremantle Dockers':            1490,
    'West Coast Eagles':            1470,
    'Adelaide Crows':               1465,
    'Essendon Bombers':             1460,
    'Richmond Tigers':              1440,
    'St Kilda Saints':              1430,
    'Gold Coast Suns':              1415,
    'North Melbourne Kangaroos':    1395,
}


def seed(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    # -- Update venue coordinates -----------------------------------------
    print('Seeding AFL venue coordinates...')
    for venue_name, coords in AFL_VENUE_COORDS.items():
        cur.execute("""
            UPDATE venues
            SET venue_notes = COALESCE(venue_notes, '') ||
                ' lat=' || ? || ' lng=' || ?
            WHERE venue_name = ?
              AND venue_notes NOT LIKE '%lat=%'
        """, (coords['lat'], coords['lng'], venue_name))

    # -- Seed team home bases --------------------------------------------
    print('Seeding AFL team home bases...')

    # Check if team_home_bases has lat/lng columns
    cols = [r[1] for r in cur.execute("PRAGMA table_info(team_home_bases)").fetchall()]
    has_lat = 'latitude' in cols or 'lat' in cols

    for team_name, base in AFL_HOME_BASES.items():
        row = cur.execute(
            "SELECT team_id FROM teams WHERE team_name = ? AND league = 'AFL'",
            (team_name,)
        ).fetchone()
        if not row:
            print(f'  WARNING: team not found — {team_name}')
            continue
        team_id = row['team_id']

        if has_lat:
            lat_col = 'latitude' if 'latitude' in cols else 'lat'
            lng_col = 'longitude' if 'longitude' in cols else 'lng'
            cur.execute(f"""
                INSERT OR REPLACE INTO team_home_bases
                    (team_id, city, {lat_col}, {lng_col})
                VALUES (?, ?, ?, ?)
            """, (team_id, base['city'], base['lat'], base['lng']))
        else:
            cur.execute("""
                INSERT OR IGNORE INTO team_home_bases (team_id, city)
                VALUES (?, ?)
            """, (team_id, base['city']))

    # -- Link primary venues to teams ------------------------------------
    print('Linking AFL teams to primary venues...')
    for team_name, venue_name in AFL_PRIMARY_VENUES.items():
        team_row = cur.execute(
            "SELECT team_id FROM teams WHERE team_name = ? AND league = 'AFL'",
            (team_name,)
        ).fetchone()
        venue_row = cur.execute(
            "SELECT venue_id FROM venues WHERE venue_name = ?",
            (venue_name,)
        ).fetchone()

        if not team_row or not venue_row:
            print(f'  WARNING: could not link {team_name} → {venue_name}')
            continue

        cur.execute("""
            UPDATE venues SET home_team_id = ?
            WHERE venue_id = ?
              AND (home_team_id IS NULL)
        """, (team_row['team_id'], venue_row['venue_id']))

    # -- Seed initial ELO into afl_team_stats ----------------------------
    print('Seeding initial AFL ELO ratings (2026 season)...')
    for team_name, elo in AFL_INITIAL_ELO.items():
        row = cur.execute(
            "SELECT team_id FROM teams WHERE team_name = ? AND league = 'AFL'",
            (team_name,)
        ).fetchone()
        if not row:
            continue
        team_id = row['team_id']
        cur.execute("""
            INSERT OR IGNORE INTO afl_team_stats
                (team_id, season, as_of_date, elo_rating, games_played, data_source)
            VALUES (?, 2026, '2026-01-01', ?, 0, 'seed_afl_teams.py')
        """, (team_id, elo))

    conn.commit()
    conn.close()

    print()
    print('AFL seed complete.')
    print('Next steps:')
    print('  1. Load 2026 AFL fixture:  python3 scripts/load_afl_fixtures.py')
    print('  2. Import team stats:      python3 scripts/build_afl_team_stats.py')
    print('  3. Run first AFL pricing:  python3 scripts/prepare_afl_round.py --round 1')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=str(DB_PATH))
    args = parser.parse_args()
    seed(Path(args.db))


if __name__ == '__main__':
    main()
