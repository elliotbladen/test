#!/usr/bin/env python3
"""
ml/predict.py

ML inference module — called during shadow mode (Phase 3+).

Loads trained models from ml/models/ and produces ML predictions
alongside the tier model prices. Does NOT modify tier model output.
Predictions are logged to tier2_performance or a separate ml_predictions
table for comparison.

USAGE
-----
Standalone (shadow mode, outputs to terminal):
    python ml/predict.py --season 2026 --round 9

As a module (called from prepare_round.py in Phase 3):
    from ml.predict import get_ml_predictions
    ml_preds = get_ml_predictions(match_features)

OUTPUT
------
Returns a dict keyed by match_id:
    {
        match_id: {
            'ml_margin':    float,   # predicted home margin
            'ml_total':     float,   # predicted total points
            'ml_h2h_prob':  float,   # predicted home win probability (0-1)
            'ml_h2h_odds':  float,   # fair home odds derived from ml_h2h_prob
            'model_version': str,    # e.g. 'xgb_v20260501'
            'feature_completeness': float,  # % of features non-null (1.0 = full T1-7)
        }
    }

PHASE GATE
----------
This module will raise NotImplementedError until Phase 3.
Phase 3 begins when:
    - ml/models/margin_model_v*.joblib exists
    - ml/models/total_model_v*.joblib exists
    - ml/models/h2h_model_v*.joblib exists
    - ml/models/feature_columns.json exists
    - Backtest MAE is competitive with tier model on 2024-2025 holdout
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / 'ml' / 'models'


def models_available() -> bool:
    """Return True if trained model files exist in ml/models/."""
    required = [
        MODELS_DIR / 'feature_columns.json',
    ]
    return all(f.exists() for f in required)


def load_models() -> dict:
    """
    Load trained margin, total, and h2h models from ml/models/.
    Returns dict with keys: margin_model, total_model, h2h_model, feature_cols.
    """
    if not models_available():
        raise FileNotFoundError(
            'No trained models found in ml/models/. '
            'Run ml/train.py first (Phase 2).'
        )
    raise NotImplementedError


def build_inference_features(match_id: int, db_path: str) -> dict:
    """
    Build feature dict for a single match from the DB.
    Pulls T1-T7 data where available; fills None for missing tiers.
    """
    raise NotImplementedError


def get_ml_predictions(match_ids: list[int],
                       db_path: Optional[str] = None) -> dict:
    """
    Main inference entry point.
    Called from prepare_round.py in Phase 3.

    Parameters
    ----------
    match_ids : list of match_id integers for the round being priced
    db_path   : optional override for DB path

    Returns
    -------
    dict keyed by match_id with ML predictions
    """
    raise NotImplementedError('predict.py not yet implemented — Phase 3')


def main():
    parser = argparse.ArgumentParser(description='ML shadow mode predictions')
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--round',  type=int, required=True)
    args = parser.parse_args()

    raise NotImplementedError('predict.py not yet implemented — Phase 3')


if __name__ == '__main__':
    main()
