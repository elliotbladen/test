#!/usr/bin/env python3
"""
ml/features/build_features.py

Session 5 — Assemble final feature matrix for ML training.

Reads game_log_features.csv (output of Sessions 1-4), selects and
encodes feature columns, applies season decay weights, and writes
the training-ready feature matrix.

USAGE
-----
    python ml/features/build_features.py
    python ml/features/build_features.py \
        --game-log ml/results/game_log_features.csv \
        --out      ml/results/features.csv
"""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

DECAY_RATE   = 0.80
BASE_SEASON  = 2025

REST_CLASS_MAP = {
    'first_game': 0,
    'short':      1,
    'normal':     2,
    'long':       3,
    'bye':        4,
}

def season_weight(season: int) -> float:
    return round(DECAY_RATE ** max(0, BASE_SEASON - season), 4)

def safe_float(v, default=None):
    try:
        f = float(v)
        return f if f == f else default  # NaN check
    except (TypeError, ValueError):
        return default

def encode_rest(cls: str) -> int:
    return REST_CLASS_MAP.get(cls, 2)  # default normal


def build_feature_row(r: dict) -> dict:
    season = int(r['season'])
    return {
        # Identifiers
        'season':              season,
        'date':                r['date'],
        'home_team':           r['home_team'],
        'away_team':           r['away_team'],
        'venue':               r['venue'],

        # T1 — ELO
        'elo_diff':            safe_float(r.get('elo_diff')),
        'home_elo_win_prob':   safe_float(r.get('home_elo_win_prob')),
        'elo_predicted_margin': safe_float(r.get('elo_predicted_margin')),

        # T3 — Rest
        'home_rest_days':      safe_float(r.get('home_rest_days')),
        'away_rest_days':      safe_float(r.get('away_rest_days')),
        'rest_diff':           safe_float(r.get('rest_diff')),
        'home_rest_class':     encode_rest(r.get('home_rest_class', 'normal')),
        'away_rest_class':     encode_rest(r.get('away_rest_class', 'normal')),
        'home_had_bye':        1 if r.get('home_rest_class') == 'bye' else 0,
        'away_had_bye':        1 if r.get('away_rest_class') == 'bye' else 0,

        # T3 — Form
        'home_prev_margin':    safe_float(r.get('home_prev_margin')),
        'away_prev_margin':    safe_float(r.get('away_prev_margin')),
        'home_off_big_win':    int(r.get('home_off_big_win', 0) or 0),
        'home_off_big_loss':   int(r.get('home_off_big_loss', 0) or 0),
        'away_off_big_win':    int(r.get('away_off_big_win', 0) or 0),
        'away_off_big_loss':   int(r.get('away_off_big_loss', 0) or 0),
        'home_win_streak':     safe_float(r.get('home_win_streak'), 0),
        'away_win_streak':     safe_float(r.get('away_win_streak'), 0),
        'home_loss_streak':    safe_float(r.get('home_loss_streak'), 0),
        'away_loss_streak':    safe_float(r.get('away_loss_streak'), 0),

        # T3 — Travel (null for pre-2021)
        'home_travel_km':      safe_float(r.get('home_travel_km')),
        'away_travel_km':      safe_float(r.get('away_travel_km')),
        'travel_diff':         safe_float(r.get('travel_diff')),
        'is_neutral_venue':    safe_float(r.get('is_neutral_venue')),

        # T4 — Venue
        'venue_avg_total':     safe_float(r.get('venue_avg_total')),
        'venue_home_win_pct':  safe_float(r.get('venue_home_win_pct')),
        'venue_sample':        safe_float(r.get('venue_sample'), 0),

        # T6 — Referee (null for games without enough ref history)
        'ref_total_diff':      safe_float(r.get('ref_total_diff')),
        'ref_penalty_rate':    safe_float(r.get('ref_penalty_rate')),
        'ref_home_bias':       safe_float(r.get('ref_home_bias')),
        'ref_home_win_pct':    safe_float(r.get('ref_home_win_pct')),

        # T7 — Weather (null for games without data)
        'rain_mm':             safe_float(r.get('rain_mm')),
        'wind_kmh':            safe_float(r.get('wind_kmh')),
        'wind_gusts_kmh':      safe_float(r.get('wind_gusts_kmh')),
        'temp_c':              safe_float(r.get('temp_c')),

        # Targets
        'actual_margin':       safe_float(r.get('actual_margin')),
        'actual_total':        safe_float(r.get('actual_total')),
        'home_win':            int(r.get('home_win', 0) or 0),

        # Training weight
        'season_weight':       season_weight(season),
    }


def main():
    parser = argparse.ArgumentParser(description='Build final ML feature matrix')
    parser.add_argument('--game-log', default=str(ROOT / 'ml/results/game_log_features.csv'))
    parser.add_argument('--out',      default=str(ROOT / 'ml/results/features.csv'))
    args = parser.parse_args()

    if not Path(args.game_log).exists():
        print(f"ERROR: not found: {args.game_log}", file=sys.stderr)
        sys.exit(1)

    print("Building feature matrix ...")
    with open(args.game_log) as f:
        raw = list(csv.DictReader(f))

    rows = [build_feature_row(r) for r in raw]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"  {len(rows)} rows written → {out}")
    seasons = sorted(set(r['season'] for r in rows))
    print(f"  Seasons: {seasons[0]} – {seasons[-1]}")
    print(f"  Features: {len(rows[0]) - 6} (excl. identifiers + targets + weight)")
    print("\nDone.")


if __name__ == '__main__':
    main()
