#!/usr/bin/env python3
"""
scripts/seed_afl_style_2026.py

Seeds AFL team style ratings and key position ratings for 2026.
Based on 2024 season performance + early 2026 form.

Ratings scale: -1.0 to +1.0 (0 = league average)
  +0.8 to +1.0  = elite
  +0.4 to +0.8  = above average
  -0.4 to +0.4  = average
  -0.8 to -0.4  = below average
  -1.0 to -0.8  = poor

Key position ratings: 0-10 scale
  9-10 = elite (Jeremy Cameron, Harris Andrews, Max Gawn tier)
  7-8  = very good
  5-6  = solid
  3-4  = below average
  1-2  = weak

USAGE
-----
    python3 scripts/seed_afl_style_2026.py
    python3 scripts/seed_afl_style_2026.py --round 9
"""

import argparse
import sqlite3
from pathlib import Path

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'data' / 'model.db'

# ---------------------------------------------------------------------------
# 2026 Team style ratings (as_of_round = 1 — pre-season baseline)
# Sources: 2024 AFL season stats + 2025 form + early 2026 results
#
# Families:
#   cp_rating           : contested possession dominance
#   clearance_rating    : clearance efficiency
#   forward_entry_rating: inside 50s volume + quality
#   scoring_eff_rating  : goal conversion rate
#   defensive_reb_rating: rebound 50s + intercepts (defensive pressure style)
#   ruck_rating         : hitouts to advantage
# ---------------------------------------------------------------------------
STYLE_RATINGS_2026 = {
    # team_name: {cp, clearance, forward_entry, scoring_eff, defensive_reb, ruck}

    # ── ELITE CONTESTED POSSESSION ──────────────────────────────────────────
    'Brisbane Lions': {
        # High CP, strong clearances, dominant forward entries
        'cp_rating':            0.75,
        'clearance_rating':     0.70,
        'forward_entry_rating': 0.80,
        'scoring_eff_rating':   0.55,
        'defensive_reb_rating': 0.40,
        'ruck_rating':          0.60,   # Daniher solid but not elite
    },
    'Geelong Cats': {
        # Outside/spread game, not CP-dominant, elite defensive rebound
        'cp_rating':            0.10,
        'clearance_rating':     0.20,
        'forward_entry_rating': 0.65,
        'scoring_eff_rating':   0.70,   # Cameron = elite conversion
        'defensive_reb_rating': 0.85,   # best defensive rebound in comp
        'ruck_rating':          0.50,
    },
    'Collingwood Magpies': {
        # High pressure, contested, aggressive style
        'cp_rating':            0.60,
        'clearance_rating':     0.55,
        'forward_entry_rating': 0.70,
        'scoring_eff_rating':   0.45,
        'defensive_reb_rating': 0.50,
        'ruck_rating':          0.65,   # Grundy era legacy, still solid
    },
    'Sydney Swans': {
        # Pressure-based, high work rate, contested
        'cp_rating':            0.65,
        'clearance_rating':     0.60,
        'forward_entry_rating': 0.60,
        'scoring_eff_rating':   0.50,
        'defensive_reb_rating': 0.55,
        'ruck_rating':          0.45,
    },
    'Greater Western Sydney Giants': {
        # CP-dominant midfield, high clearance, strong ruck
        'cp_rating':            0.70,
        'clearance_rating':     0.65,
        'forward_entry_rating': 0.65,
        'scoring_eff_rating':   0.40,   # conversion is their weakness
        'defensive_reb_rating': 0.35,
        'ruck_rating':          0.75,   # Flynn dominant
    },
    'Carlton Blues': {
        # Improved CP, strong midfield core (Cripps)
        'cp_rating':            0.65,
        'clearance_rating':     0.60,
        'forward_entry_rating': 0.55,
        'scoring_eff_rating':   0.45,
        'defensive_reb_rating': 0.30,
        'ruck_rating':          0.55,
    },
    'Hawthorn Hawks': {
        # Young team — high pressure, work rate improving
        'cp_rating':            0.40,
        'clearance_rating':     0.35,
        'forward_entry_rating': 0.50,
        'scoring_eff_rating':   0.55,
        'defensive_reb_rating': 0.40,
        'ruck_rating':          0.30,
    },

    # ── AVERAGE / MIXED STYLES ───────────────────────────────────────────────
    'Western Bulldogs': {
        # Speed and spread, not CP-dominant but high inside 50s
        'cp_rating':            0.20,
        'clearance_rating':     0.25,
        'forward_entry_rating': 0.60,
        'scoring_eff_rating':   0.40,
        'defensive_reb_rating': 0.20,
        'ruck_rating':          0.35,
    },
    'Port Adelaide Power': {
        # Physical, high CP historically, rebounding defense
        'cp_rating':            0.55,
        'clearance_rating':     0.50,
        'forward_entry_rating': 0.50,
        'scoring_eff_rating':   0.45,
        'defensive_reb_rating': 0.55,
        'ruck_rating':          0.40,
    },
    'Melbourne Demons': {
        # CP was elite 2021-22, declining since. Still above avg.
        'cp_rating':            0.45,
        'clearance_rating':     0.40,   # Gawn-led clearances
        'forward_entry_rating': 0.40,
        'scoring_eff_rating':   0.35,
        'defensive_reb_rating': 0.30,
        'ruck_rating':          0.90,   # Gawn = elite ruck
    },
    'Fremantle Dockers': {
        # CP-based, physical, improving forward pressure
        'cp_rating':            0.50,
        'clearance_rating':     0.45,
        'forward_entry_rating': 0.45,
        'scoring_eff_rating':   0.30,   # conversion historically weak
        'defensive_reb_rating': 0.50,
        'ruck_rating':          0.55,
    },
    'Adelaide Crows': {
        # Speed-based, improving CP under Nicks
        'cp_rating':            0.30,
        'clearance_rating':     0.25,
        'forward_entry_rating': 0.50,
        'scoring_eff_rating':   0.45,
        'defensive_reb_rating': 0.35,
        'ruck_rating':          0.30,
    },
    'Gold Coast Suns': {
        # Athletic, high-speed outside game. CP growing.
        'cp_rating':            0.25,
        'clearance_rating':     0.20,
        'forward_entry_rating': 0.55,
        'scoring_eff_rating':   0.35,
        'defensive_reb_rating': 0.25,
        'ruck_rating':          0.40,
    },
    'St Kilda Saints': {
        # Average across the board, improving
        'cp_rating':            0.15,
        'clearance_rating':     0.10,
        'forward_entry_rating': 0.40,
        'scoring_eff_rating':   0.35,
        'defensive_reb_rating': 0.20,
        'ruck_rating':          0.20,
    },

    # ── BELOW AVERAGE / REBUILDING ───────────────────────────────────────────
    'Richmond Tigers': {
        # In rebuild — lost CP core, low ratings across board
        'cp_rating':           -0.30,
        'clearance_rating':    -0.25,
        'forward_entry_rating':-0.10,
        'scoring_eff_rating':   0.20,
        'defensive_reb_rating':-0.20,
        'ruck_rating':         -0.10,
    },
    'Essendon Bombers': {
        # Improving but still below avg CP and clearances
        'cp_rating':           -0.20,
        'clearance_rating':    -0.15,
        'forward_entry_rating': 0.20,
        'scoring_eff_rating':   0.25,
        'defensive_reb_rating': 0.10,
        'ruck_rating':          0.15,
    },
    'West Coast Eagles': {
        # Deep rebuild — poor across all dimensions
        'cp_rating':           -0.70,
        'clearance_rating':    -0.65,
        'forward_entry_rating':-0.60,
        'scoring_eff_rating':  -0.30,
        'defensive_reb_rating':-0.55,
        'ruck_rating':         -0.50,
    },
    'North Melbourne Kangaroos': {
        # Worst team in comp — all metrics poor
        'cp_rating':           -0.80,
        'clearance_rating':    -0.75,
        'forward_entry_rating':-0.70,
        'scoring_eff_rating':  -0.40,
        'defensive_reb_rating':-0.65,
        'ruck_rating':         -0.60,
    },
}

# ---------------------------------------------------------------------------
# Key position ratings (as_of_round 1, 2026)
# kf_rating / kd_rating / ruck_rating: 0-10 scale
# ---------------------------------------------------------------------------
KEY_POSITION_2026 = {
    'Brisbane Lions': {
        'kf_player_name': 'Joe Daniher',   'kf_rating': 7.5, 'kf_goals_pg': 2.1,
        'kd_player_name': 'Harris Andrews', 'kd_rating': 9.5,
        'kf2_player_name': 'Zac Bailey',    'kf2_rating': 6.5,
        'kd2_player_name': 'Brandon Starcevich', 'kd2_rating': 7.0,
        'ruck_player_name': 'Oscar McInerney', 'ruck_rating': 7.0,
    },
    'Geelong Cats': {
        'kf_player_name': 'Jeremy Cameron', 'kf_rating': 9.5, 'kf_goals_pg': 2.8,
        'kd_player_name': 'Tom Stewart',    'kd_rating': 8.5,
        'kf2_player_name': 'Tom Hawkins',   'kf2_rating': 7.0,
        'kd2_player_name': 'Jake Kolodjashnij', 'kd2_rating': 7.0,
        'ruck_player_name': 'Rhys Stanley',  'ruck_rating': 6.5,
    },
    'Collingwood Magpies': {
        'kf_player_name': 'Mason Cox',      'kf_rating': 6.5, 'kf_goals_pg': 1.5,
        'kd_player_name': 'Darcy Moore',    'kd_rating': 9.0,
        'kf2_player_name': 'Brody Mihocek', 'kf2_rating': 6.5,
        'kd2_player_name': 'Jeremy Howe',   'kd2_rating': 7.5,
        'ruck_player_name': 'Mason Cox',     'ruck_rating': 6.5,
    },
    'Sydney Swans': {
        'kf_player_name': 'Logan McDonald', 'kf_rating': 7.0, 'kf_goals_pg': 1.8,
        'kd_player_name': 'Dane Rampe',     'kd_rating': 7.5,
        'kf2_player_name': 'Joel Amartey',  'kf2_rating': 6.5,
        'kd2_player_name': 'Tom McCartin',  'kd2_rating': 7.5,
        'ruck_player_name': 'Peter Ladhams', 'ruck_rating': 7.0,
    },
    'Greater Western Sydney Giants': {
        'kf_player_name': 'Jesse Hogan',    'kf_rating': 7.5, 'kf_goals_pg': 2.0,
        'kd_player_name': 'Sam Taylor',     'kd_rating': 8.5,
        'kf2_player_name': 'Harry Himmelberg', 'kf2_rating': 6.5,
        'kd2_player_name': 'Lachie Whitfield', 'kd2_rating': 6.0,
        'ruck_player_name': 'Kieren Briggs', 'ruck_rating': 8.0,
    },
    'Carlton Blues': {
        'kf_player_name': 'Harry McKay',    'kf_rating': 8.5, 'kf_goals_pg': 2.4,
        'kd_player_name': 'Jacob Weitering', 'kd_rating': 9.0,
        'kf2_player_name': 'Charlie Curnow', 'kf2_rating': 8.5,
        'kd2_player_name': 'Liam Jones',    'kd2_rating': 6.5,
        'ruck_player_name': 'Tom De Koning', 'ruck_rating': 7.5,
    },
    'Hawthorn Hawks': {
        'kf_player_name': 'Mitch Lewis',    'kf_rating': 8.0, 'kf_goals_pg': 2.2,
        'kd_player_name': 'James Sicily',   'kd_rating': 8.5,
        'kf2_player_name': 'Jack Gunston',  'kf2_rating': 6.5,
        'kd2_player_name': 'Josh Weddle',   'kd2_rating': 6.5,
        'ruck_player_name': 'Lloyd Meek',   'ruck_rating': 6.5,
    },
    'Western Bulldogs': {
        'kf_player_name': 'Aaron Naughton', 'kf_rating': 8.5, 'kf_goals_pg': 2.3,
        'kd_player_name': 'Alex Keath',     'kd_rating': 7.0,
        'kf2_player_name': 'Jamarra Ugle-Hagan', 'kf2_rating': 7.5,
        'kd2_player_name': 'Zaine Cordy',   'kd2_rating': 6.5,
        'ruck_player_name': 'Tim English',   'ruck_rating': 8.0,
    },
    'Port Adelaide Power': {
        'kf_player_name': 'Charlie Dixon',  'kf_rating': 8.0, 'kf_goals_pg': 2.1,
        'kd_player_name': 'Trent McKenzie', 'kd_rating': 7.0,
        'kf2_player_name': 'Mitch Georgiades', 'kf2_rating': 7.0,
        'kd2_player_name': 'Aliir Aliir',   'kd2_rating': 7.5,
        'ruck_player_name': 'Ivan Soldo',   'ruck_rating': 7.0,
    },
    'Melbourne Demons': {
        'kf_player_name': 'Tom McDonald',   'kf_rating': 7.0, 'kf_goals_pg': 1.8,
        'kd_player_name': 'Steven May',     'kd_rating': 8.5,
        'kf2_player_name': 'Ben Brown',     'kf2_rating': 7.0,
        'kd2_player_name': 'Jake Lever',    'kd2_rating': 8.0,
        'ruck_player_name': 'Max Gawn',     'ruck_rating': 9.5,
    },
    'Fremantle Dockers': {
        'kf_player_name': 'Rory Lobb',      'kf_rating': 7.0, 'kf_goals_pg': 1.7,
        'kd_player_name': 'Alex Pearce',    'kd_rating': 8.0,
        'kf2_player_name': 'Matt Taberner', 'kf2_rating': 6.5,
        'kd2_player_name': 'Luke Ryan',     'kd2_rating': 7.5,
        'ruck_player_name': 'Sean Darcy',   'ruck_rating': 8.0,
    },
    'Adelaide Crows': {
        'kf_player_name': 'Taylor Walker',  'kf_rating': 7.5, 'kf_goals_pg': 1.9,
        'kd_player_name': 'Jordan Butts',   'kd_rating': 7.5,
        'kf2_player_name': 'Darcy Fogarty', 'kf2_rating': 7.0,
        'kd2_player_name': 'Rory Laird',    'kd2_rating': 7.5,
        'ruck_player_name': 'Reilly OBrien', 'ruck_rating': 7.0,
    },
    'Gold Coast Suns': {
        'kf_player_name': 'Ben King',       'kf_rating': 8.0, 'kf_goals_pg': 2.0,
        'kd_player_name': 'Sam Collins',    'kd_rating': 7.5,
        'kf2_player_name': 'Mabior Chol',   'kf2_rating': 6.5,
        'kd2_player_name': 'Jack Lukosius', 'kd2_rating': 6.5,
        'ruck_player_name': 'Jarrod Witts', 'ruck_rating': 8.0,
    },
    'St Kilda Saints': {
        'kf_player_name': 'Max King',       'kf_rating': 7.5, 'kf_goals_pg': 1.8,
        'kd_player_name': 'Dougal Howard',  'kd_rating': 7.0,
        'kf2_player_name': 'Tim Membrey',   'kf2_rating': 6.5,
        'kd2_player_name': 'Jimmy Webster', 'kd2_rating': 6.5,
        'ruck_player_name': 'Rowan Marshall', 'ruck_rating': 7.5,
    },
    'Richmond Tigers': {
        'kf_player_name': 'Tom Lynch',      'kf_rating': 7.5, 'kf_goals_pg': 2.0,
        'kd_player_name': 'Dylan Grimes',   'kd_rating': 7.5,
        'kf2_player_name': 'Shai Bolton',   'kf2_rating': 6.0,
        'kd2_player_name': 'Noah Balta',    'kd2_rating': 6.5,
        'ruck_player_name': 'Toby Nankervis', 'ruck_rating': 6.5,
    },
    'Essendon Bombers': {
        'kf_player_name': 'Peter Wright',   'kf_rating': 7.0, 'kf_goals_pg': 1.8,
        'kd_player_name': 'Mason Redman',   'kd_rating': 7.0,
        'kf2_player_name': 'Ben Hobbs',     'kf2_rating': 6.0,
        'kd2_player_name': 'Andrew McGrath', 'kd2_rating': 6.5,
        'ruck_player_name': 'Sam Draper',   'ruck_rating': 7.5,
    },
    'West Coast Eagles': {
        'kf_player_name': 'Jack Darling',   'kf_rating': 6.5, 'kf_goals_pg': 1.5,
        'kd_player_name': 'Tom Barrass',    'kd_rating': 7.5,
        'kf2_player_name': 'Jake Waterman', 'kf2_rating': 6.0,
        'kd2_player_name': 'Jeremy McGovern', 'kd2_rating': 7.0,
        'ruck_player_name': 'Bailey Williams', 'ruck_rating': 6.5,
    },
    'North Melbourne Kangaroos': {
        'kf_player_name': 'Nick Larkey',    'kf_rating': 7.0, 'kf_goals_pg': 1.9,
        'kd_player_name': 'Aidan Corr',     'kd_rating': 6.5,
        'kf2_player_name': 'Cam Zurhaar',   'kf2_rating': 6.0,
        'kd2_player_name': 'Tristan Xerri', 'kd2_rating': 6.0,
        'ruck_player_name': 'Tristan Xerri', 'ruck_rating': 6.5,
    },
}


def seed(db_path: Path, as_of_round: int = 1):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    # Apply migration first
    migration = ROOT / 'db' / 'migrations' / '019_afl_style_ratings.sql'
    if migration.exists():
        cur.executescript(migration.read_text())
        print('Applied migration 019_afl_style_ratings.sql')

    season = 2026
    inserted_style = 0
    inserted_kp    = 0

    for team_name, ratings in STYLE_RATINGS_2026.items():
        row = cur.execute(
            "SELECT team_id FROM teams WHERE team_name = ? AND league = 'AFL'",
            (team_name,)
        ).fetchone()
        if not row:
            print(f'  WARNING: team not found — {team_name}')
            continue
        team_id = row['team_id']

        cur.execute("""
            INSERT OR REPLACE INTO afl_team_style_ratings
                (team_id, season, as_of_round,
                 cp_rating, clearance_rating, forward_entry_rating,
                 scoring_eff_rating, defensive_reb_rating, ruck_rating,
                 games_in_window, data_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'manual_2026')
        """, (
            team_id, season, as_of_round,
            ratings['cp_rating'],
            ratings['clearance_rating'],
            ratings['forward_entry_rating'],
            ratings['scoring_eff_rating'],
            ratings['defensive_reb_rating'],
            ratings['ruck_rating'],
        ))
        inserted_style += 1

    for team_name, kp in KEY_POSITION_2026.items():
        row = cur.execute(
            "SELECT team_id FROM teams WHERE team_name = ? AND league = 'AFL'",
            (team_name,)
        ).fetchone()
        if not row:
            continue
        team_id = row['team_id']

        cur.execute("""
            INSERT OR REPLACE INTO afl_key_position_ratings
                (team_id, season, as_of_round,
                 kf_player_name, kf_rating, kf_goals_pg,
                 kd_player_name, kd_rating,
                 kf2_player_name, kf2_rating,
                 kd2_player_name, kd2_rating,
                 ruck_player_name, ruck_rating,
                 data_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual_2026')
        """, (
            team_id, season, as_of_round,
            kp.get('kf_player_name'), kp.get('kf_rating'), kp.get('kf_goals_pg', 0),
            kp.get('kd_player_name'), kp.get('kd_rating'),
            kp.get('kf2_player_name'), kp.get('kf2_rating'),
            kp.get('kd2_player_name'), kp.get('kd2_rating'),
            kp.get('ruck_player_name'), kp.get('ruck_rating'),
        ))
        inserted_kp += 1

    conn.commit()
    conn.close()

    print(f'Style ratings seeded:    {inserted_style} teams')
    print(f'Key position seeded:     {inserted_kp} teams')
    print()
    print('Next: python3 scripts/build_afl_t2_matchups.py --round 1')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db',    default=str(DB_PATH))
    parser.add_argument('--round', type=int, default=1)
    args = parser.parse_args()
    seed(Path(args.db), args.round)


if __name__ == '__main__':
    main()
