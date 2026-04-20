#!/usr/bin/env python3
"""
ml/backtest.py

Walk-forward backtest of ML models against historical data.

Simulates how the model would have performed if deployed round by round.
For each test season, the model is trained only on data available BEFORE
that season (no look-ahead). Results are logged to ml/results/.

This is different from train.py (which uses a fixed train/val/test split).
Walk-forward gives a more realistic picture of real-world performance.

USAGE
-----
    # Backtest across 2022-2025 using rolling training window
    python ml/backtest.py \
        --features ml/results/features_historical.csv \
        --test-seasons 2022 2023 2024 2025 \
        --min-train-seasons 5 \
        --out ml/results/backtest_results.csv

BACKTEST LOGIC
--------------
For each test season S:
    train on seasons [S - window : S - 1]
    predict on season S
    compare ML margin/total/H2H vs:
        - actual result
        - tier model price (if available in DB)
        - market closing line (if available in DB)

OUTPUT COLUMNS
--------------
    season, round, home_team, away_team,
    actual_margin, actual_total, home_win,
    ml_margin, ml_total, ml_h2h_prob,
    tier_margin, tier_total,              ← from DB if available
    market_margin, market_total,          ← closing line from DB if available
    ml_margin_error, tier_margin_error,
    ml_total_error,  tier_total_error,
    ml_h2h_correct,  tier_h2h_correct,

METRICS SUMMARY
---------------
Per season and overall:
    ML MAE margin  vs  Tier MAE margin  vs  Market MAE margin
    ML MAE total   vs  Tier MAE total   vs  Market MAE total
    ML H2H acc     vs  Tier H2H acc

The goal: ML should be competitive with or better than the tier model
before it earns a place in the production blend.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_walk_forward(features_csv: str,
                     test_seasons: list[int],
                     min_train_seasons: int,
                     db_path: str) -> list[dict]:
    """
    Run walk-forward backtest. Returns list of per-game result dicts.
    """
    raise NotImplementedError


def compute_summary_metrics(results: list[dict]) -> dict:
    """
    Aggregate MAE and accuracy metrics across the backtest period.
    Returns per-season and overall summary.
    """
    raise NotImplementedError


def main():
    parser = argparse.ArgumentParser(description='Walk-forward ML backtest')
    parser.add_argument('--features',          required=True)
    parser.add_argument('--test-seasons',      nargs='+', type=int, required=True)
    parser.add_argument('--min-train-seasons', type=int, default=5)
    parser.add_argument('--out',               default='ml/results/backtest_results.csv')
    args = parser.parse_args()

    raise NotImplementedError('backtest.py not yet implemented — Phase 2')


if __name__ == '__main__':
    main()
