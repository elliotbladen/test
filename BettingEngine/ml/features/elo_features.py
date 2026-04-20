#!/usr/bin/env python3
"""
ml/features/elo_features.py

Session 3 — Add per-game ELO differential to the game log.

Replays the full ELO sequence from bootstrap_elo_historical.py but
captures the PRE-GAME ratings for every match (what the model actually
knew before the game was played).

This is the critical distinction:
  bootstrap_elo_historical.py  → end-of-season ratings for DB
  this script                  → pre-game snapshot for every game (ML feature)

USAGE
-----
    python ml/features/elo_features.py \
        --xlsx '/Users/elliotbladen/Downloads/nrl (4).xlsx' \
        --game-log ml/results/game_log_travel.csv \
        --out ml/results/game_log_elo.csv

OUTPUT COLUMNS ADDED
--------------------
    home_elo            pre-game ELO rating for home team
    away_elo            pre-game ELO rating for away team
    elo_diff            home_elo - away_elo
    home_elo_win_prob   expected win probability for home team (from ELO)
    elo_predicted_margin  (elo_diff * 0.04) + 3.5 home advantage
"""

import argparse
import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

STARTING_ELO     = 1500.0
K_FACTOR         = 20
REVERSION_RATE   = 0.25
HOME_ADVANTAGE   = 3.5
POINTS_PER_ELO   = 0.04

ERA_K = {
    2009: 20, 2010: 20, 2011: 20, 2012: 20, 2013: 20,
    2014: 20, 2015: 20, 2016: 20, 2017: 20, 2018: 20,
    2019: 20, 2020: 28, 2021: 24, 2022: 20, 2023: 20,
    2024: 20, 2025: 20, 2026: 20,
}

NAME_MAP = {
    'Canterbury Bulldogs':       'Canterbury-Bankstown Bulldogs',
    'Cronulla Sharks':           'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':          'Manly-Warringah Sea Eagles',
    'North QLD Cowboys':         'North Queensland Cowboys',
    'St George Dragons':         'St. George Illawarra Dragons',
    'St George Illawarra':       'St. George Illawarra Dragons',
    'Brisbane':                  'Brisbane Broncos',
    'Canberra':                  'Canberra Raiders',
    'Gold Coast':                'Gold Coast Titans',
    'Melbourne':                 'Melbourne Storm',
    'Newcastle':                 'Newcastle Knights',
    'Parramatta':                'Parramatta Eels',
    'Penrith':                   'Penrith Panthers',
    'South Sydney':              'South Sydney Rabbitohs',
    'Sydney Roosters':           'Sydney Roosters',
    'Wests Tigers':              'Wests Tigers',
    'Warriors':                  'New Zealand Warriors',
    'NZ Warriors':               'New Zealand Warriors',
    'Dolphins':                  'Dolphins',
}

def canon(name): return NAME_MAP.get(str(name).strip(), str(name).strip())
def expected(r_h, r_a): return 1.0 / (1.0 + 10.0 ** ((r_a - r_h) / 400.0))
def revert(ratings, season):
    rate = 0.40 if season == 2020 else (0.30 if season == 2021 else REVERSION_RATE)
    return {n: round(e * (1 - rate) + STARTING_ELO * rate, 2) for n, e in ratings.items()}


def load_xlsx(xlsx_path):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    games = []
    for row in rows[2:]:
        if not row[0]: continue
        raw = row[0]
        d = raw.date() if hasattr(raw, 'date') else None
        if not d: continue
        try:
            hs = int(float(str(row[5])))
            aws = int(float(str(row[6])))
        except (TypeError, ValueError):
            continue
        h = canon(str(row[2]).strip())
        a = canon(str(row[3]).strip())
        games.append({'date': d, 'season': d.year, 'home': h, 'away': a, 'hs': hs, 'aws': aws})
    return sorted(games, key=lambda g: g['date'])


def build_elo_timeline(games):
    """
    Replay all games, capturing PRE-GAME ELO for each match.
    Returns dict keyed by (date_str, home, away) → (home_elo, away_elo)
    """
    ratings = {}
    snapshots = {}
    current_season = None

    for g in games:
        season = g['season']

        # Season boundary reversion
        if current_season is not None and season != current_season and ratings:
            ratings = revert(ratings, season)
        current_season = season

        h, a = g['home'], g['away']
        if h not in ratings: ratings[h] = STARTING_ELO
        if a not in ratings: ratings[a] = STARTING_ELO

        r_h, r_a = ratings[h], ratings[a]

        # Snapshot BEFORE the game
        key = (g['date'].strftime('%Y-%m-%d'), h, a)
        snapshots[key] = (round(r_h, 2), round(r_a, 2))

        # Update ratings AFTER
        k = ERA_K.get(season, 20)
        e_h = expected(r_h, r_a)
        s_h = 1.0 if g['hs'] > g['aws'] else (0.0 if g['hs'] < g['aws'] else 0.5)
        delta_h = k * (s_h - e_h)
        delta_a = k * ((1 - s_h) - (1 - e_h))
        ratings[h] = r_h + delta_h
        ratings[a] = r_a + delta_a

    return snapshots


def main():
    parser = argparse.ArgumentParser(description='Add ELO features to game log')
    parser.add_argument('--xlsx',     required=True)
    parser.add_argument('--game-log', default=str(ROOT / 'ml/results/game_log_travel.csv'))
    parser.add_argument('--out',      default=str(ROOT / 'ml/results/game_log_elo.csv'))
    args = parser.parse_args()

    print("Loading xlsx and replaying ELO timeline ...")
    games = load_xlsx(args.xlsx)
    snapshots = build_elo_timeline(games)
    print(f"  {len(snapshots)} pre-game ELO snapshots built")

    print("Loading game log ...")
    with open(args.game_log) as f:
        rows = list(csv.DictReader(f))
    print(f"  {len(rows)} games")

    matched = missed = 0
    out_rows = []
    for r in rows:
        key = (r['date'], r['home_team'], r['away_team'])
        snap = snapshots.get(key)
        if snap:
            h_elo, a_elo = snap
            elo_diff   = round(h_elo - a_elo, 2)
            win_prob   = round(expected(h_elo, a_elo), 4)
            pred_margin = round(elo_diff * POINTS_PER_ELO + HOME_ADVANTAGE, 2)
            matched += 1
        else:
            h_elo = a_elo = elo_diff = win_prob = pred_margin = ''
            missed += 1

        row = dict(r)
        row.update({
            'home_elo':            h_elo,
            'away_elo':            a_elo,
            'elo_diff':            elo_diff,
            'home_elo_win_prob':   win_prob,
            'elo_predicted_margin': pred_margin,
        })
        out_rows.append(row)

    print(f"\n  Matched: {matched}   Unmatched: {missed}")

    # Quick sanity check
    sample = [r for r in out_rows if r['elo_diff'] != ''][:3]
    print(f"\n  Sample:")
    for r in sample:
        print(f"    {r['date']}  {r['home_team']:<32} vs {r['away_team']:<32}"
              f"  elo_diff={r['elo_diff']:>7}  pred={r['elo_predicted_margin']:>5}  "
              f"actual={r['actual_margin']}")

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
