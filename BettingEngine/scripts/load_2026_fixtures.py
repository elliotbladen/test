#!/usr/bin/env python3
"""
scripts/load_2026_fixtures.py

Load the full 2026 NRL regular-season fixture schedule into the matches table.

SOURCE
------
Official NRL draw PDF (released 14 November 2025), cross-checked against
League Unlimited (leagueunlimited.com/news/43203-2026-nrl-draw/) and Legz.com.au.

ROUND NUMBERING NOTE
---------------------
The existing DB data (R1–R7) uses an offset convention relative to the
official NRL round numbers:
  - DB R1 = Official R1 (Las Vegas games only, 2 matches)
  - DB R2 = Official R1 (remaining domestic games, 6 matches)
  - DB R3 = Official R2
  - DB R4 = Official R3
  ...
  - DB R7 = Official R6

This script continues that convention to maintain consistency with existing data:
  - DB R8  = Official R7   (April 16–19)
  - DB R9  = Official R8   (April 23–26, ANZAC Round)
  - DB R10 = Official R9
  ...
  - DB R28 = Official R27

The existing R1–R7 rows are left untouched (ON CONFLICT DO NOTHING).
Official rounds R1–R6 are included below as a complete reference but will
be skipped on insert if matching rows already exist.

USAGE
-----
    cd /path/to/Betting_model
    python scripts/load_2026_fixtures.py [--dry-run] [--settings config/settings.yaml]
"""

import argparse
import sqlite3
import sys
import yaml
from pathlib import Path

# =============================================================================
# Team and venue name → DB ID mappings
# =============================================================================

TEAM_IDS = {
    'Penrith Panthers':                1,
    'Brisbane Broncos':                2,
    'New Zealand Warriors':            3,
    'Melbourne Storm':                 4,
    'Newcastle Knights':               5,
    'Sydney Roosters':                 6,
    'Canberra Raiders':                7,
    'Cronulla-Sutherland Sharks':      8,
    'Gold Coast Titans':               9,
    'Canterbury-Bankstown Bulldogs':  10,
    'St. George Illawarra Dragons':   11,
    'North Queensland Cowboys':       12,
    'Dolphins':                       13,
    'South Sydney Rabbitohs':         14,
    'Manly-Warringah Sea Eagles':     15,
    'Wests Tigers':                   16,
    'Parramatta Eels':                17,
}

VENUE_IDS = {
    'Accor Stadium':                         1,
    'Suncorp Stadium':                       2,
    'Go Media Stadium':                      3,
    'AAMI Park':                             4,
    'McDonald Jones Stadium':                5,
    'Sharks Stadium':                       40,   # PointsBet Stadium (same venue)
    'BlueBet Stadium':                       7,
    'Cbus Super Stadium':                    8,
    'Jubilee Stadium':                       9,
    '4 Pines Park':                         10,
    'GIO Stadium Canberra':                 11,
    'Allianz Stadium':                      12,
    'WIN Stadium':                          13,
    'CommBank Stadium':                     14,
    'Queensland Country Bank Stadium':      15,
    'TIO Stadium':                          34,
    'Optus Stadium':                        19,
    'Campbelltown Sports Stadium':          27,
    'Leichhardt Oval':                      30,
    'Sky Stadium':                          36,
    'HBF Park':                             37,
    'Kayo Stadium':                         25,
    'Polytec Stadium':                      28,
    'Glen Willow Regional Sports Stadium':  35,
    'Allegiant Stadium':                    39,
    'One NZ Stadium Christchurch':          38,   # Apollo Projects / Orangetheory Stadium
    'Carrington Park':                      32,
    'Sunshine Coast Stadium':              24,
}

# =============================================================================
# Full 2026 fixture data
#
# Format per entry:
#   (db_round, official_round, match_date, kickoff_time, home_team, away_team, venue)
#
# db_round = round number stored in the DB (official_round + 1 for rounds ≥ 3)
# kickoff_time = local AEST/AEDT HH:MM
# =============================================================================

FIXTURES = [
    # -------------------------------------------------------------------------
    # OFFICIAL R1 (DB R1 + R2) — Las Vegas + domestic
    # Already in DB; included here for completeness; will be skipped via
    # ON CONFLICT DO NOTHING on composite key (season, round, home_id, away_id)
    # -------------------------------------------------------------------------
    # DB R1 — Las Vegas (2026-02-28 US local = 2026-03-01 AEDT)
    (1, 1, '2026-02-28', '01:15', 'Newcastle Knights',            'North Queensland Cowboys',        'Allegiant Stadium'),
    (1, 1, '2026-02-28', '03:30', 'Canterbury-Bankstown Bulldogs','St. George Illawarra Dragons',    'Allegiant Stadium'),
    # DB R2 — Official R1 domestic
    (2, 1, '2026-03-05', '20:00', 'Melbourne Storm',              'Parramatta Eels',                 'AAMI Park'),
    (2, 1, '2026-03-06', '18:00', 'New Zealand Warriors',         'Sydney Roosters',                 'Go Media Stadium'),
    (2, 1, '2026-03-06', '20:00', 'Brisbane Broncos',             'Penrith Panthers',                'Suncorp Stadium'),
    (2, 1, '2026-03-07', '17:30', 'Cronulla-Sutherland Sharks',   'Gold Coast Titans',               'Sharks Stadium'),
    (2, 1, '2026-03-07', '19:30', 'Manly-Warringah Sea Eagles',   'Canberra Raiders',                '4 Pines Park'),
    (2, 1, '2026-03-08', '16:05', 'Dolphins',                     'South Sydney Rabbitohs',          'Suncorp Stadium'),

    # -------------------------------------------------------------------------
    # DB R3 = Official R2 (12–15 March)  Bye: Canterbury-Bankstown Bulldogs
    # -------------------------------------------------------------------------
    (3, 2, '2026-03-12', '20:00', 'Brisbane Broncos',             'Parramatta Eels',                 'Suncorp Stadium'),
    (3, 2, '2026-03-13', '18:00', 'New Zealand Warriors',         'Canberra Raiders',                'Go Media Stadium'),
    (3, 2, '2026-03-13', '20:00', 'Sydney Roosters',              'South Sydney Rabbitohs',          'Allianz Stadium'),
    (3, 2, '2026-03-14', '15:00', 'Wests Tigers',                 'North Queensland Cowboys',        'Leichhardt Oval'),
    (3, 2, '2026-03-14', '17:30', 'St. George Illawarra Dragons', 'Melbourne Storm',                 'WIN Stadium'),
    (3, 2, '2026-03-14', '19:30', 'Penrith Panthers',             'Cronulla-Sutherland Sharks',      'Carrington Park'),
    (3, 2, '2026-03-15', '16:05', 'Manly-Warringah Sea Eagles',   'Newcastle Knights',               '4 Pines Park'),
    (3, 2, '2026-03-15', '18:15', 'Dolphins',                     'Gold Coast Titans',               'Suncorp Stadium'),

    # -------------------------------------------------------------------------
    # DB R4 = Official R3 (19–22 March)  Bye: Manly-Warringah Sea Eagles
    # -------------------------------------------------------------------------
    (4, 3, '2026-03-19', '20:00', 'Canberra Raiders',             'Canterbury-Bankstown Bulldogs',   'GIO Stadium Canberra'),
    (4, 3, '2026-03-20', '18:00', 'Sydney Roosters',              'Penrith Panthers',                'Allianz Stadium'),
    (4, 3, '2026-03-20', '20:00', 'Melbourne Storm',              'Brisbane Broncos',                'AAMI Park'),
    (4, 3, '2026-03-21', '15:00', 'Newcastle Knights',            'New Zealand Warriors',            'McDonald Jones Stadium'),
    (4, 3, '2026-03-21', '17:30', 'Cronulla-Sutherland Sharks',   'Dolphins',                        'Sharks Stadium'),
    (4, 3, '2026-03-21', '19:30', 'South Sydney Rabbitohs',       'Wests Tigers',                    'Polytec Stadium'),
    (4, 3, '2026-03-22', '16:05', 'Parramatta Eels',              'St. George Illawarra Dragons',    'CommBank Stadium'),
    (4, 3, '2026-03-22', '18:15', 'North Queensland Cowboys',     'Gold Coast Titans',               'Queensland Country Bank Stadium'),

    # -------------------------------------------------------------------------
    # DB R5 = Official R4 (26–29 March)  Bye: South Sydney Rabbitohs
    # -------------------------------------------------------------------------
    (5, 4, '2026-03-26', '20:00', 'Manly-Warringah Sea Eagles',   'Sydney Roosters',                 '4 Pines Park'),
    (5, 4, '2026-03-27', '18:00', 'New Zealand Warriors',         'Wests Tigers',                    'Go Media Stadium'),
    (5, 4, '2026-03-27', '20:00', 'Brisbane Broncos',             'Dolphins',                        'Suncorp Stadium'),
    (5, 4, '2026-03-28', '15:00', 'Canterbury-Bankstown Bulldogs','Newcastle Knights',               'Accor Stadium'),
    (5, 4, '2026-03-28', '17:30', 'Penrith Panthers',             'Parramatta Eels',                 'CommBank Stadium'),
    (5, 4, '2026-03-28', '19:30', 'North Queensland Cowboys',     'Melbourne Storm',                 'Queensland Country Bank Stadium'),
    (5, 4, '2026-03-29', '16:05', 'Canberra Raiders',             'Cronulla-Sutherland Sharks',      'GIO Stadium Canberra'),
    (5, 4, '2026-03-29', '18:15', 'Gold Coast Titans',            'St. George Illawarra Dragons',    'Cbus Super Stadium'),

    # -------------------------------------------------------------------------
    # DB R6 = Official R5 Easter (2–6 April)  Bye: Sydney Roosters
    # -------------------------------------------------------------------------
    (6, 5, '2026-04-02', '20:00', 'Dolphins',                     'Manly-Warringah Sea Eagles',      'Kayo Stadium'),
    (6, 5, '2026-04-03', '16:05', 'South Sydney Rabbitohs',       'Canterbury-Bankstown Bulldogs',   'Accor Stadium'),
    (6, 5, '2026-04-03', '20:00', 'Penrith Panthers',             'Melbourne Storm',                 'CommBank Stadium'),
    (6, 5, '2026-04-04', '17:30', 'St. George Illawarra Dragons', 'North Queensland Cowboys',        'Jubilee Stadium'),
    (6, 5, '2026-04-04', '19:30', 'Gold Coast Titans',            'Brisbane Broncos',                'Cbus Super Stadium'),
    (6, 5, '2026-04-05', '14:00', 'Cronulla-Sutherland Sharks',   'New Zealand Warriors',            'Sharks Stadium'),
    (6, 5, '2026-04-05', '16:05', 'Newcastle Knights',            'Canberra Raiders',                'McDonald Jones Stadium'),
    (6, 5, '2026-04-06', '16:05', 'Parramatta Eels',              'Wests Tigers',                    'CommBank Stadium'),

    # -------------------------------------------------------------------------
    # DB R7 = Official R6 (9–12 April)  Bye: Dolphins
    # -------------------------------------------------------------------------
    (7, 6, '2026-04-09', '19:50', 'Canterbury-Bankstown Bulldogs','Penrith Panthers',                'Accor Stadium'),
    (7, 6, '2026-04-10', '18:00', 'St. George Illawarra Dragons', 'Manly-Warringah Sea Eagles',      'WIN Stadium'),
    (7, 6, '2026-04-10', '20:00', 'Brisbane Broncos',             'North Queensland Cowboys',        'Suncorp Stadium'),
    (7, 6, '2026-04-11', '15:00', 'South Sydney Rabbitohs',       'Canberra Raiders',                'Optus Stadium'),
    (7, 6, '2026-04-11', '17:30', 'Cronulla-Sutherland Sharks',   'Sydney Roosters',                 'Optus Stadium'),
    (7, 6, '2026-04-11', '19:30', 'Melbourne Storm',              'New Zealand Warriors',            'AAMI Park'),
    (7, 6, '2026-04-12', '14:00', 'Parramatta Eels',              'Gold Coast Titans',               'CommBank Stadium'),
    (7, 6, '2026-04-12', '16:05', 'Wests Tigers',                 'Newcastle Knights',               'Campbelltown Sports Stadium'),

    # =========================================================================
    # NEW ROUNDS — not yet in DB
    # =========================================================================

    # -------------------------------------------------------------------------
    # DB R8 = Official R7 (16–19 April)  Bye: Cronulla-Sutherland Sharks
    # -------------------------------------------------------------------------
    (8, 7, '2026-04-16', '19:50', 'North Queensland Cowboys',     'Manly-Warringah Sea Eagles',      'Queensland Country Bank Stadium'),
    (8, 7, '2026-04-17', '18:00', 'Canberra Raiders',             'Melbourne Storm',                 'GIO Stadium Canberra'),
    (8, 7, '2026-04-17', '20:00', 'Dolphins',                     'Penrith Panthers',                'TIO Stadium'),
    (8, 7, '2026-04-18', '15:00', 'New Zealand Warriors',         'Gold Coast Titans',               'Go Media Stadium'),
    (8, 7, '2026-04-18', '17:30', 'South Sydney Rabbitohs',       'St. George Illawarra Dragons',    'Accor Stadium'),
    (8, 7, '2026-04-18', '19:30', 'Wests Tigers',                 'Brisbane Broncos',                'Campbelltown Sports Stadium'),
    (8, 7, '2026-04-19', '14:00', 'Sydney Roosters',              'Newcastle Knights',               'Allianz Stadium'),
    (8, 7, '2026-04-19', '16:05', 'Parramatta Eels',              'Canterbury-Bankstown Bulldogs',   'CommBank Stadium'),

    # -------------------------------------------------------------------------
    # DB R9 = Official R8 ANZAC Round (23–26 April)  Bye: Gold Coast Titans
    # -------------------------------------------------------------------------
    (9, 8, '2026-04-23', '19:50', 'Wests Tigers',                 'Canberra Raiders',                'Leichhardt Oval'),
    (9, 8, '2026-04-24', '18:00', 'North Queensland Cowboys',     'Cronulla-Sutherland Sharks',      'Queensland Country Bank Stadium'),
    (9, 8, '2026-04-24', '20:00', 'Brisbane Broncos',             'Canterbury-Bankstown Bulldogs',   'Suncorp Stadium'),
    (9, 8, '2026-04-25', '16:00', 'St. George Illawarra Dragons', 'Sydney Roosters',                 'Allianz Stadium'),
    (9, 8, '2026-04-25', '18:05', 'New Zealand Warriors',         'Dolphins',                        'Sky Stadium'),
    (9, 8, '2026-04-25', '20:10', 'Melbourne Storm',              'South Sydney Rabbitohs',          'AAMI Park'),
    (9, 8, '2026-04-26', '14:00', 'Newcastle Knights',            'Penrith Panthers',                'McDonald Jones Stadium'),
    (9, 8, '2026-04-26', '16:05', 'Manly-Warringah Sea Eagles',   'Parramatta Eels',                 '4 Pines Park'),

    # -------------------------------------------------------------------------
    # DB R10 = Official R9 (1–3 May)  Bye: St. George Illawarra Dragons
    # -------------------------------------------------------------------------
    (10, 9, '2026-05-01', '18:00', 'Canterbury-Bankstown Bulldogs','North Queensland Cowboys',       'Accor Stadium'),
    (10, 9, '2026-05-01', '20:00', 'Dolphins',                    'Melbourne Storm',                 'Suncorp Stadium'),
    (10, 9, '2026-05-02', '15:00', 'Gold Coast Titans',           'Canberra Raiders',                'Cbus Super Stadium'),
    (10, 9, '2026-05-02', '17:30', 'Parramatta Eels',             'New Zealand Warriors',            'CommBank Stadium'),
    (10, 9, '2026-05-02', '19:30', 'Sydney Roosters',             'Brisbane Broncos',                'Allianz Stadium'),
    (10, 9, '2026-05-03', '14:00', 'Newcastle Knights',           'South Sydney Rabbitohs',          'McDonald Jones Stadium'),
    (10, 9, '2026-05-03', '16:05', 'Cronulla-Sutherland Sharks',  'Wests Tigers',                    'Sharks Stadium'),
    (10, 9, '2026-05-03', '18:15', 'Penrith Panthers',            'Manly-Warringah Sea Eagles',      'CommBank Stadium'),

    # -------------------------------------------------------------------------
    # DB R11 = Official R10 (7–10 May)  Bye: New Zealand Warriors
    # -------------------------------------------------------------------------
    (11, 10, '2026-05-07', '19:50', 'Dolphins',                   'Canterbury-Bankstown Bulldogs',   'Suncorp Stadium'),
    (11, 10, '2026-05-08', '18:00', 'Sydney Roosters',            'Gold Coast Titans',               'Polytec Stadium'),
    (11, 10, '2026-05-08', '20:00', 'North Queensland Cowboys',   'Parramatta Eels',                 'Queensland Country Bank Stadium'),
    (11, 10, '2026-05-09', '15:00', 'St. George Illawarra Dragons','Newcastle Knights',              'WIN Stadium'),
    (11, 10, '2026-05-09', '17:30', 'South Sydney Rabbitohs',     'Cronulla-Sutherland Sharks',      'Accor Stadium'),
    (11, 10, '2026-05-09', '19:30', 'Manly-Warringah Sea Eagles', 'Brisbane Broncos',                '4 Pines Park'),
    (11, 10, '2026-05-10', '14:00', 'Melbourne Storm',            'Wests Tigers',                    'AAMI Park'),
    (11, 10, '2026-05-10', '16:05', 'Canberra Raiders',           'Penrith Panthers',                'GIO Stadium Canberra'),

    # -------------------------------------------------------------------------
    # DB R12 = Official R11 Magic Round (15–17 May)  Bye: Canberra Raiders
    # All at Suncorp Stadium, Brisbane
    # -------------------------------------------------------------------------
    (12, 11, '2026-05-15', '18:00', 'Cronulla-Sutherland Sharks', 'Canterbury-Bankstown Bulldogs',   'Suncorp Stadium'),
    (12, 11, '2026-05-15', '20:00', 'South Sydney Rabbitohs',     'Dolphins',                        'Suncorp Stadium'),
    (12, 11, '2026-05-16', '15:00', 'Wests Tigers',               'Manly-Warringah Sea Eagles',      'Suncorp Stadium'),
    (12, 11, '2026-05-16', '17:30', 'Sydney Roosters',            'North Queensland Cowboys',        'Suncorp Stadium'),
    (12, 11, '2026-05-16', '19:30', 'Parramatta Eels',            'Melbourne Storm',                 'Suncorp Stadium'),
    (12, 11, '2026-05-17', '14:00', 'Gold Coast Titans',          'Newcastle Knights',               'Suncorp Stadium'),
    (12, 11, '2026-05-17', '16:05', 'New Zealand Warriors',       'Brisbane Broncos',                'Suncorp Stadium'),
    (12, 11, '2026-05-17', '18:25', 'Penrith Panthers',           'St. George Illawarra Dragons',    'Suncorp Stadium'),

    # -------------------------------------------------------------------------
    # DB R13 = Official R12 (21–24 May)  SOO I lead-in  7 byes  5 games
    # Byes: Brisbane Broncos, Cronulla-Sutherland Sharks, Newcastle Knights,
    #       Parramatta Eels, Penrith Panthers, Sydney Roosters, Wests Tigers
    # -------------------------------------------------------------------------
    (13, 12, '2026-05-21', '19:50', 'Canberra Raiders',           'Dolphins',                        'GIO Stadium Canberra'),
    (13, 12, '2026-05-22', '20:00', 'Canterbury-Bankstown Bulldogs','Melbourne Storm',               'Accor Stadium'),
    (13, 12, '2026-05-23', '17:30', 'St. George Illawarra Dragons','New Zealand Warriors',           'Jubilee Stadium'),
    (13, 12, '2026-05-23', '19:30', 'Manly-Warringah Sea Eagles', 'Gold Coast Titans',               '4 Pines Park'),
    (13, 12, '2026-05-24', '16:05', 'North Queensland Cowboys',   'South Sydney Rabbitohs',          'Queensland Country Bank Stadium'),

    # -------------------------------------------------------------------------
    # DB R14 = Official R13 (29–31 May)  3 byes  7 games
    # Byes: Dolphins, Gold Coast Titans, South Sydney Rabbitohs
    # -------------------------------------------------------------------------
    (14, 13, '2026-05-29', '20:00', 'Cronulla-Sutherland Sharks', 'Manly-Warringah Sea Eagles',      'Sharks Stadium'),
    (14, 13, '2026-05-30', '15:00', 'Newcastle Knights',          'Parramatta Eels',                 'McDonald Jones Stadium'),
    (14, 13, '2026-05-30', '17:30', 'Wests Tigers',               'Canterbury-Bankstown Bulldogs',   'CommBank Stadium'),
    (14, 13, '2026-05-30', '19:30', 'Melbourne Storm',            'Sydney Roosters',                 'AAMI Park'),
    (14, 13, '2026-05-31', '14:00', 'Brisbane Broncos',           'St. George Illawarra Dragons',    'Suncorp Stadium'),
    (14, 13, '2026-05-31', '16:05', 'Canberra Raiders',           'North Queensland Cowboys',        'GIO Stadium Canberra'),
    (14, 13, '2026-05-31', '18:15', 'Penrith Panthers',           'New Zealand Warriors',            'CommBank Stadium'),

    # -------------------------------------------------------------------------
    # DB R15 = Official R14 (4–8 June)  Bye: New Zealand Warriors  8 games
    # -------------------------------------------------------------------------
    (15, 14, '2026-06-04', '19:50', 'Manly-Warringah Sea Eagles', 'South Sydney Rabbitohs',          '4 Pines Park'),
    (15, 14, '2026-06-05', '18:00', 'Melbourne Storm',            'Newcastle Knights',               'AAMI Park'),
    (15, 14, '2026-06-05', '20:00', 'Canberra Raiders',           'Sydney Roosters',                 'GIO Stadium Canberra'),
    (15, 14, '2026-06-06', '17:30', 'North Queensland Cowboys',   'Dolphins',                        'Queensland Country Bank Stadium'),
    (15, 14, '2026-06-06', '19:30', 'Brisbane Broncos',           'Gold Coast Titans',               'Suncorp Stadium'),
    (15, 14, '2026-06-07', '14:00', 'Wests Tigers',               'Penrith Panthers',                'CommBank Stadium'),
    (15, 14, '2026-06-07', '16:05', 'Cronulla-Sutherland Sharks', 'St. George Illawarra Dragons',    'Sharks Stadium'),
    (15, 14, '2026-06-08', '16:05', 'Canterbury-Bankstown Bulldogs','Parramatta Eels',               'Accor Stadium'),

    # -------------------------------------------------------------------------
    # DB R16 = Official R15 (11–14 June)  SOO II lead-in  7 byes  5 games
    # Byes: Canterbury-Bankstown, Manly, Melbourne Storm, Newcastle Knights,
    #       NQ Cowboys, Penrith Panthers, St. George Illawarra Dragons
    # -------------------------------------------------------------------------
    (16, 15, '2026-06-11', '19:50', 'South Sydney Rabbitohs',     'Brisbane Broncos',                'Accor Stadium'),
    (16, 15, '2026-06-12', '20:00', 'Dolphins',                   'Sydney Roosters',                 'Suncorp Stadium'),
    (16, 15, '2026-06-13', '17:30', 'New Zealand Warriors',       'Cronulla-Sutherland Sharks',      'Go Media Stadium'),
    (16, 15, '2026-06-13', '19:30', 'Parramatta Eels',            'Canberra Raiders',                'CommBank Stadium'),
    (16, 15, '2026-06-14', '16:05', 'Wests Tigers',               'Gold Coast Titans',               'Leichhardt Oval'),

    # -------------------------------------------------------------------------
    # DB R17 = Official R16 (19–21 June)  3 byes  7 games
    # Byes: Brisbane Broncos, Parramatta Eels, South Sydney Rabbitohs
    # -------------------------------------------------------------------------
    (17, 16, '2026-06-19', '20:00', 'Newcastle Knights',          'St. George Illawarra Dragons',    'McDonald Jones Stadium'),
    (17, 16, '2026-06-20', '15:00', 'Wests Tigers',               'Dolphins',                        'Campbelltown Sports Stadium'),
    (17, 16, '2026-06-20', '17:30', 'Gold Coast Titans',          'Penrith Panthers',                'Cbus Super Stadium'),
    (17, 16, '2026-06-20', '19:30', 'Canterbury-Bankstown Bulldogs','Manly-Warringah Sea Eagles',    'Accor Stadium'),
    (17, 16, '2026-06-21', '14:00', 'New Zealand Warriors',       'North Queensland Cowboys',        'One NZ Stadium Christchurch'),
    (17, 16, '2026-06-21', '16:05', 'Melbourne Storm',            'Canberra Raiders',                'AAMI Park'),
    (17, 16, '2026-06-21', '18:15', 'Sydney Roosters',            'Cronulla-Sutherland Sharks',      'Allianz Stadium'),

    # -------------------------------------------------------------------------
    # DB R18 = Official R17 (25–28 June)  Bye: Cronulla-Sutherland Sharks
    # -------------------------------------------------------------------------
    (18, 17, '2026-06-25', '19:50', 'Parramatta Eels',            'South Sydney Rabbitohs',          'CommBank Stadium'),
    (18, 17, '2026-06-26', '18:00', 'Gold Coast Titans',          'Canterbury-Bankstown Bulldogs',   'Cbus Super Stadium'),
    (18, 17, '2026-06-26', '20:00', 'Brisbane Broncos',           'Sydney Roosters',                 'Suncorp Stadium'),
    (18, 17, '2026-06-27', '15:00', 'Dolphins',                   'New Zealand Warriors',            'Suncorp Stadium'),
    (18, 17, '2026-06-27', '17:30', 'North Queensland Cowboys',   'Penrith Panthers',                'Queensland Country Bank Stadium'),
    (18, 17, '2026-06-27', '19:30', 'Manly-Warringah Sea Eagles', 'Melbourne Storm',                 '4 Pines Park'),
    (18, 17, '2026-06-28', '14:00', 'Canberra Raiders',           'St. George Illawarra Dragons',    'GIO Stadium Canberra'),
    (18, 17, '2026-06-28', '16:05', 'Newcastle Knights',          'Wests Tigers',                    'McDonald Jones Stadium'),

    # -------------------------------------------------------------------------
    # DB R19 = Official R18 (3–5 July)  SOO III lead-in  7 byes  5 games
    # Byes: Canberra Raiders, Canterbury-Bankstown, Gold Coast Titans,
    #       Melbourne Storm, North Queensland Cowboys, Sydney Roosters,
    #       New Zealand Warriors
    # -------------------------------------------------------------------------
    (19, 18, '2026-07-03', '20:00', 'Penrith Panthers',           'South Sydney Rabbitohs',          'CommBank Stadium'),
    (19, 18, '2026-07-04', '17:30', 'St. George Illawarra Dragons','Wests Tigers',                   'Jubilee Stadium'),
    (19, 18, '2026-07-04', '19:30', 'Brisbane Broncos',           'Cronulla-Sutherland Sharks',      'Suncorp Stadium'),
    (19, 18, '2026-07-05', '14:00', 'Parramatta Eels',            'Manly-Warringah Sea Eagles',      'CommBank Stadium'),
    (19, 18, '2026-07-05', '16:05', 'Newcastle Knights',          'Dolphins',                        'McDonald Jones Stadium'),

    # -------------------------------------------------------------------------
    # DB R20 = Official R19 (10–12 July)  3 byes  7 games
    # Byes: Brisbane Broncos, Penrith Panthers, St. George Illawarra Dragons
    # -------------------------------------------------------------------------
    (20, 19, '2026-07-10', '20:00', 'Wests Tigers',               'New Zealand Warriors',            'Campbelltown Sports Stadium'),
    (20, 19, '2026-07-11', '15:00', 'Dolphins',                   'Cronulla-Sutherland Sharks',      'Kayo Stadium'),
    (20, 19, '2026-07-11', '17:30', 'Canterbury-Bankstown Bulldogs','Canberra Raiders',              'Accor Stadium'),
    (20, 19, '2026-07-11', '19:30', 'Sydney Roosters',            'Parramatta Eels',                 'Allianz Stadium'),
    (20, 19, '2026-07-12', '14:00', 'South Sydney Rabbitohs',     'Newcastle Knights',               'Accor Stadium'),
    (20, 19, '2026-07-12', '16:05', 'Manly-Warringah Sea Eagles', 'North Queensland Cowboys',        '4 Pines Park'),
    (20, 19, '2026-07-12', '18:15', 'Melbourne Storm',            'Gold Coast Titans',               'AAMI Park'),

    # -------------------------------------------------------------------------
    # DB R21 = Official R20 (16–19 July)  Bye: Parramatta Eels
    # -------------------------------------------------------------------------
    (21, 20, '2026-07-16', '19:50', 'Penrith Panthers',           'Brisbane Broncos',                'CommBank Stadium'),
    (21, 20, '2026-07-17', '18:00', 'Cronulla-Sutherland Sharks', 'Newcastle Knights',               'Sharks Stadium'),
    (21, 20, '2026-07-17', '20:00', 'Sydney Roosters',            'Melbourne Storm',                 'Allianz Stadium'),
    (21, 20, '2026-07-18', '15:00', 'Canberra Raiders',           'South Sydney Rabbitohs',          'GIO Stadium Canberra'),
    (21, 20, '2026-07-18', '17:30', 'New Zealand Warriors',       'St. George Illawarra Dragons',    'Go Media Stadium'),
    (21, 20, '2026-07-18', '19:30', 'Canterbury-Bankstown Bulldogs','Wests Tigers',                  'Accor Stadium'),
    (21, 20, '2026-07-19', '14:00', 'Gold Coast Titans',          'Manly-Warringah Sea Eagles',      'Cbus Super Stadium'),
    (21, 20, '2026-07-19', '16:05', 'Dolphins',                   'North Queensland Cowboys',        'Suncorp Stadium'),

    # -------------------------------------------------------------------------
    # DB R22 = Official R21 (23–26 July)  Bye: Dolphins
    # -------------------------------------------------------------------------
    (22, 21, '2026-07-23', '19:50', 'Parramatta Eels',            'Penrith Panthers',                'CommBank Stadium'),
    (22, 21, '2026-07-24', '18:00', 'Newcastle Knights',          'Sydney Roosters',                 'McDonald Jones Stadium'),
    (22, 21, '2026-07-24', '20:00', 'South Sydney Rabbitohs',     'Melbourne Storm',                 'Accor Stadium'),
    (22, 21, '2026-07-25', '15:00', 'Canberra Raiders',           'Wests Tigers',                    'GIO Stadium Canberra'),
    (22, 21, '2026-07-25', '17:30', 'Canterbury-Bankstown Bulldogs','New Zealand Warriors',          'Accor Stadium'),
    (22, 21, '2026-07-25', '19:30', 'North Queensland Cowboys',   'Brisbane Broncos',                'Queensland Country Bank Stadium'),
    (22, 21, '2026-07-26', '14:00', 'St. George Illawarra Dragons','Gold Coast Titans',              'Jubilee Stadium'),
    (22, 21, '2026-07-26', '16:05', 'Manly-Warringah Sea Eagles', 'Cronulla-Sutherland Sharks',      '4 Pines Park'),

    # -------------------------------------------------------------------------
    # DB R23 = Official R22 (30 July – 2 August)  Bye: Manly-Warringah Sea Eagles
    # -------------------------------------------------------------------------
    (23, 22, '2026-07-30', '19:50', 'North Queensland Cowboys',   'Sydney Roosters',                 'Queensland Country Bank Stadium'),
    (23, 22, '2026-07-31', '18:00', 'St. George Illawarra Dragons','Dolphins',                       'WIN Stadium'),
    (23, 22, '2026-07-31', '20:00', 'Melbourne Storm',            'Canterbury-Bankstown Bulldogs',   'AAMI Park'),
    (23, 22, '2026-08-01', '15:00', 'Gold Coast Titans',          'New Zealand Warriors',            'Cbus Super Stadium'),
    (23, 22, '2026-08-01', '17:30', 'Penrith Panthers',           'Canberra Raiders',                'Glen Willow Regional Sports Stadium'),
    (23, 22, '2026-08-01', '19:30', 'Brisbane Broncos',           'Newcastle Knights',               'Suncorp Stadium'),
    (23, 22, '2026-08-02', '14:00', 'Cronulla-Sutherland Sharks', 'South Sydney Rabbitohs',          'Sharks Stadium'),
    (23, 22, '2026-08-02', '16:05', 'Wests Tigers',               'Parramatta Eels',                 'CommBank Stadium'),

    # -------------------------------------------------------------------------
    # DB R24 = Official R23 (6–9 August)  Bye: Wests Tigers
    # -------------------------------------------------------------------------
    (24, 23, '2026-08-06', '19:50', 'Gold Coast Titans',          'North Queensland Cowboys',        'Cbus Super Stadium'),
    (24, 23, '2026-08-07', '18:00', 'New Zealand Warriors',       'Penrith Panthers',                'Go Media Stadium'),
    (24, 23, '2026-08-07', '20:00', 'Sydney Roosters',            'Canterbury-Bankstown Bulldogs',   'Allianz Stadium'),
    (24, 23, '2026-08-08', '15:00', 'Melbourne Storm',            'Manly-Warringah Sea Eagles',      'HBF Park'),
    (24, 23, '2026-08-08', '17:30', 'Dolphins',                   'Brisbane Broncos',                'Suncorp Stadium'),
    (24, 23, '2026-08-08', '19:30', 'South Sydney Rabbitohs',     'Parramatta Eels',                 'Allianz Stadium'),
    (24, 23, '2026-08-09', '14:00', 'Canberra Raiders',           'Newcastle Knights',               'GIO Stadium Canberra'),
    (24, 23, '2026-08-09', '16:05', 'St. George Illawarra Dragons','Cronulla-Sutherland Sharks',     'Jubilee Stadium'),

    # -------------------------------------------------------------------------
    # DB R25 = Official R24 (13–16 August)  Bye: Melbourne Storm
    # -------------------------------------------------------------------------
    (25, 24, '2026-08-13', '19:50', 'Penrith Panthers',           'Sydney Roosters',                 'CommBank Stadium'),
    (25, 24, '2026-08-14', '18:00', 'Manly-Warringah Sea Eagles', 'Dolphins',                        '4 Pines Park'),
    (25, 24, '2026-08-14', '20:00', 'Canterbury-Bankstown Bulldogs','South Sydney Rabbitohs',        'Accor Stadium'),
    (25, 24, '2026-08-15', '15:00', 'Cronulla-Sutherland Sharks', 'Canberra Raiders',                'Sharks Stadium'),
    (25, 24, '2026-08-15', '17:30', 'Parramatta Eels',            'North Queensland Cowboys',        'CommBank Stadium'),
    (25, 24, '2026-08-15', '19:30', 'Brisbane Broncos',           'New Zealand Warriors',            'Suncorp Stadium'),
    (25, 24, '2026-08-16', '14:00', 'Newcastle Knights',          'Gold Coast Titans',               'McDonald Jones Stadium'),
    (25, 24, '2026-08-16', '16:05', 'Wests Tigers',               'St. George Illawarra Dragons',    'CommBank Stadium'),

    # -------------------------------------------------------------------------
    # DB R26 = Official R25 (20–23 August)  Bye: North Queensland Cowboys
    # -------------------------------------------------------------------------
    (26, 25, '2026-08-20', '19:50', 'Melbourne Storm',            'Penrith Panthers',                'AAMI Park'),
    (26, 25, '2026-08-21', '18:00', 'Canberra Raiders',           'Brisbane Broncos',                'GIO Stadium Canberra'),
    (26, 25, '2026-08-21', '20:00', 'Dolphins',                   'Parramatta Eels',                 'Suncorp Stadium'),
    (26, 25, '2026-08-22', '15:00', 'Newcastle Knights',          'Manly-Warringah Sea Eagles',      'McDonald Jones Stadium'),
    (26, 25, '2026-08-22', '17:30', 'South Sydney Rabbitohs',     'New Zealand Warriors',            'Accor Stadium'),
    (26, 25, '2026-08-22', '19:30', 'St. George Illawarra Dragons','Canterbury-Bankstown Bulldogs',  'Allianz Stadium'),
    (26, 25, '2026-08-23', '14:00', 'Gold Coast Titans',          'Cronulla-Sutherland Sharks',      'Cbus Super Stadium'),
    (26, 25, '2026-08-23', '16:05', 'Sydney Roosters',            'Wests Tigers',                    'Allianz Stadium'),

    # -------------------------------------------------------------------------
    # DB R27 = Official R26 (27–30 August)  Bye: Canberra Raiders
    # -------------------------------------------------------------------------
    (27, 26, '2026-08-27', '19:50', 'Brisbane Broncos',           'Melbourne Storm',                 'Suncorp Stadium'),
    (27, 26, '2026-08-28', '18:00', 'Manly-Warringah Sea Eagles', 'St. George Illawarra Dragons',    '4 Pines Park'),
    (27, 26, '2026-08-28', '20:00', 'Penrith Panthers',           'Canterbury-Bankstown Bulldogs',   'CommBank Stadium'),
    (27, 26, '2026-08-29', '15:00', 'Gold Coast Titans',          'South Sydney Rabbitohs',          'Cbus Super Stadium'),
    (27, 26, '2026-08-29', '17:30', 'Sydney Roosters',            'Dolphins',                        'Allianz Stadium'),
    (27, 26, '2026-08-29', '19:30', 'North Queensland Cowboys',   'Wests Tigers',                    'Queensland Country Bank Stadium'),
    (27, 26, '2026-08-30', '14:00', 'New Zealand Warriors',       'Newcastle Knights',               'Go Media Stadium'),
    (27, 26, '2026-08-30', '16:05', 'Parramatta Eels',            'Cronulla-Sutherland Sharks',      'CommBank Stadium'),

    # -------------------------------------------------------------------------
    # DB R28 = Official R27 (3–6 September)  Bye: Newcastle Knights
    # -------------------------------------------------------------------------
    (28, 27, '2026-09-03', '19:50', 'Canterbury-Bankstown Bulldogs','Brisbane Broncos',              'Accor Stadium'),
    (28, 27, '2026-09-04', '18:00', 'Gold Coast Titans',          'Dolphins',                        'Cbus Super Stadium'),
    (28, 27, '2026-09-04', '20:00', 'South Sydney Rabbitohs',     'Sydney Roosters',                 'Allianz Stadium'),
    (28, 27, '2026-09-05', '15:00', 'New Zealand Warriors',       'Manly-Warringah Sea Eagles',      'Go Media Stadium'),
    (28, 27, '2026-09-05', '17:30', 'North Queensland Cowboys',   'Canberra Raiders',                'Queensland Country Bank Stadium'),
    (28, 27, '2026-09-05', '19:30', 'Cronulla-Sutherland Sharks', 'Melbourne Storm',                 'Sharks Stadium'),
    (28, 27, '2026-09-06', '14:00', 'St. George Illawarra Dragons','Parramatta Eels',               'WIN Stadium'),
    (28, 27, '2026-09-06', '16:05', 'Penrith Panthers',           'Wests Tigers',                    'CommBank Stadium'),
]


def resolve_ids(fixtures: list) -> list:
    """
    Resolve team and venue names to DB IDs.
    Returns list of resolved tuples, and a list of mapping errors.
    """
    resolved = []
    errors   = []

    for row in fixtures:
        db_round, official_round, match_date, kickoff, home_name, away_name, venue_name = row

        home_id  = TEAM_IDS.get(home_name)
        away_id  = TEAM_IDS.get(away_name)
        venue_id = VENUE_IDS.get(venue_name)

        if home_id is None:
            errors.append(f"  UNKNOWN TEAM: {home_name!r}")
        if away_id is None:
            errors.append(f"  UNKNOWN TEAM: {away_name!r}")
        if venue_id is None:
            errors.append(f"  UNKNOWN VENUE: {venue_name!r}")

        if home_id and away_id and venue_id:
            kickoff_dt = f"{match_date} {kickoff}:00"
            resolved.append((
                db_round, match_date, kickoff_dt,
                home_id, away_id, venue_id,
                home_name, away_name, venue_name,
            ))

    return resolved, errors


def load_fixtures(conn, resolved: list, dry_run: bool) -> tuple:
    inserted = skipped = 0

    for (db_round, match_date, kickoff_dt,
         home_id, away_id, venue_id,
         home_name, away_name, venue_name) in resolved:

        # Check for existing row using composite key
        existing = conn.execute(
            """SELECT match_id FROM matches
               WHERE season=2026 AND round_number=?
                 AND home_team_id=? AND away_team_id=?""",
            (db_round, home_id, away_id)
        ).fetchone()

        if existing:
            skipped += 1
            continue

        marker = '(dry-run)' if dry_run else 'inserted'
        if not dry_run:
            conn.execute(
                """INSERT INTO matches
                       (sport, competition, season, round_number,
                        match_date, kickoff_datetime,
                        home_team_id, away_team_id, venue_id,
                        status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ('NRL', 'NRL Premiership', 2026, db_round,
                 match_date, kickoff_dt,
                 home_id, away_id, venue_id,
                 'scheduled')
            )

        print(f"  R{db_round:2d} {match_date}  {home_name:<42} vs {away_name:<42}  @{venue_name}  {marker}")
        inserted += 1

    if not dry_run:
        conn.commit()

    return inserted, skipped


def main():
    parser = argparse.ArgumentParser(description='Load full 2026 NRL fixture schedule')
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

    # Resolve IDs
    resolved, errors = resolve_ids(FIXTURES)
    if errors:
        print("MAPPING ERRORS (must fix before loading):")
        for e in errors:
            print(e)
        print()
        if errors:
            conn.close()
            sys.exit(1)

    print(f"Resolved {len(resolved)} fixtures  ({len(FIXTURES) - len(resolved)} skipped due to mapping errors)\n")
    print(f"{'─'*110}")

    inserted, skipped = load_fixtures(conn, resolved, args.dry_run)

    print(f"{'─'*110}")
    print(f"\n  Inserted: {inserted}")
    print(f"  Skipped (already exist): {skipped}")

    # Summary by round
    if not args.dry_run:
        print()
        rows = conn.execute("""
            SELECT round_number, COUNT(*) as cnt,
                   MIN(match_date) as first_date, MAX(match_date) as last_date
            FROM matches WHERE season=2026
            GROUP BY round_number ORDER BY round_number
        """).fetchall()
        total = sum(r['cnt'] for r in rows)
        print(f"  Rounds now in DB: {[r['round_number'] for r in rows]}")
        print(f"  Total matches in season: {total}")

        # Highlight DB R8 (Official R7)
        r8 = [r for r in rows if r['round_number'] == 8]
        if r8:
            print(f"\n  DB Round 8 (Official R7): {r8[0]['cnt']} games  "
                  f"{r8[0]['first_date']} to {r8[0]['last_date']}")
            r8_games = conn.execute("""
                SELECT h.team_name as home, a.team_name as away, m.match_date
                FROM matches m
                JOIN teams h ON m.home_team_id = h.team_id
                JOIN teams a ON m.away_team_id = a.team_id
                WHERE m.season=2026 AND m.round_number=8
                ORDER BY m.match_date, m.match_id
            """).fetchall()
            for g in r8_games:
                print(f"    {g['match_date']}  {g['home']} vs {g['away']}")

        print()
        print("  ROUND NUMBERING NOTE")
        print("  ---------------------")
        print("  DB rounds are offset by +1 from official NRL rounds (from R3 onwards),")
        print("  because the official R1 was split into DB R1 (Las Vegas) + DB R2 (domestic).")
        print()
        print("  DB R8  = Official R7  (Apr 16–19, next game week)")
        print("  DB R9  = Official R8  (Apr 23–26, ANZAC Round)")
        print("  DB R28 = Official R27 (Sep 3–6, final regular season round)")
        print()
        print("  To price: python scripts/price_round.py --season 2026 --round 8")

    conn.close()


if __name__ == '__main__':
    main()
