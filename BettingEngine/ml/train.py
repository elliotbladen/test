#!/usr/bin/env python3
"""
ml/train.py

Train XGBoost models on the NRL feature matrix.

Three models:
    margin_model  — predict actual margin (regression)
    total_model   — predict actual total  (regression)
    h2h_model     — predict home win      (classification)

USAGE
-----
    python ml/train.py
    python ml/train.py --features ml/results/features.csv \
                       --train-seasons 2009 2023 \
                       --val-season 2024 \
                       --test-season 2025
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.metrics import (mean_absolute_error, mean_squared_error,
                              accuracy_score, log_loss, brier_score_loss)

ROOT      = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / 'ml' / 'models'

FEATURE_COLS = [
    'elo_diff', 'home_elo_win_prob', 'elo_predicted_margin',
    'home_rest_days', 'away_rest_days', 'rest_diff',
    'home_rest_class', 'away_rest_class',
    'home_had_bye', 'away_had_bye',
    'home_prev_margin', 'away_prev_margin',
    'home_off_big_win', 'home_off_big_loss',
    'away_off_big_win', 'away_off_big_loss',
    'home_win_streak', 'away_win_streak',
    'home_loss_streak', 'away_loss_streak',
    'home_travel_km', 'away_travel_km', 'travel_diff', 'is_neutral_venue',
    'venue_avg_total', 'venue_home_win_pct',
    'ref_total_diff', 'ref_penalty_rate', 'ref_home_bias', 'ref_home_win_pct',
    'rain_mm', 'wind_kmh', 'wind_gusts_kmh', 'temp_c',
]


def load_features(csv_path: str) -> list[dict]:
    with open(csv_path) as f:
        return list(csv.DictReader(f))


def to_arrays(rows: list[dict], feature_cols: list[str]):
    """Convert list of dicts to numpy arrays. None → NaN (XGBoost handles natively)."""
    X, w = [], []
    for r in rows:
        feats = []
        for col in feature_cols:
            v = r.get(col)
            try:
                feats.append(float(v) if v not in (None, '', 'None') else float('nan'))
            except (TypeError, ValueError):
                feats.append(float('nan'))
        X.append(feats)
        w.append(float(r.get('season_weight', 1.0)))
    return np.array(X, dtype=np.float32), np.array(w, dtype=np.float32)


def split(rows, train_seasons, val_season, test_season):
    train = [r for r in rows if int(r['season']) in train_seasons]
    val   = [r for r in rows if int(r['season']) == val_season]
    test  = [r for r in rows if int(r['season']) == test_season]
    return train, val, test


def train_regression(X_tr, y_tr, w_tr, X_val, y_val, label):
    model = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        verbosity=0,
        early_stopping_rounds=30,
    )
    model.fit(X_tr, y_tr, sample_weight=w_tr,
              eval_set=[(X_val, y_val)], verbose=False)
    return model


def train_classifier(X_tr, y_tr, w_tr, X_val, y_val):
    model = xgb.XGBClassifier(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        verbosity=0,
        early_stopping_rounds=30,
        use_label_encoder=False,
        eval_metric='logloss',
    )
    model.fit(X_tr, y_tr, sample_weight=w_tr,
              eval_set=[(X_val, y_val)], verbose=False)
    return model


def evaluate_regression(model, X, y, label):
    pred = model.predict(X)
    mae  = mean_absolute_error(y, pred)
    rmse = mean_squared_error(y, pred) ** 0.5
    print(f"    {label:<12}  MAE={mae:.2f}  RMSE={rmse:.2f}")
    return mae, rmse, pred


def evaluate_classifier(model, X, y, label):
    pred_prob = model.predict_proba(X)[:, 1]
    pred_cls  = (pred_prob >= 0.5).astype(int)
    acc   = accuracy_score(y, pred_cls)
    ll    = log_loss(y, pred_prob)
    brier = brier_score_loss(y, pred_prob)
    print(f"    {label:<12}  Acc={acc*100:.1f}%  LogLoss={ll:.4f}  Brier={brier:.4f}")
    return acc, ll, brier


def feature_importance_table(model, feature_cols):
    scores = model.feature_importances_
    pairs  = sorted(zip(feature_cols, scores), key=lambda x: -x[1])
    print(f"\n    {'Feature':<28}  Importance")
    print(f"    {'─'*28}  {'─'*10}")
    for name, score in pairs:
        if score > 0.005:
            bar = '█' * int(score * 100)
            print(f"    {name:<28}  {score:.4f}  {bar}")


def main():
    parser = argparse.ArgumentParser(description='Train NRL ML models')
    parser.add_argument('--features',      default=str(ROOT / 'ml/results/features.csv'))
    parser.add_argument('--train-seasons', nargs=2, type=int, default=[2009, 2023],
                        metavar=('FROM', 'TO'))
    parser.add_argument('--val-season',    type=int, default=2024)
    parser.add_argument('--test-season',   type=int, default=2025)
    args = parser.parse_args()

    train_seasons = list(range(args.train_seasons[0], args.train_seasons[1] + 1))

    print(f"\n{'═'*65}")
    print(f"  NRL ML Training")
    print(f"  Train: {train_seasons[0]}–{train_seasons[-1]}  "
          f"Val: {args.val_season}  Test: {args.test_season}")
    print(f"{'═'*65}")

    print(f"\nLoading features ...")
    rows = load_features(args.features)
    print(f"  {len(rows)} games total")

    train_rows, val_rows, test_rows = split(
        rows, train_seasons, args.val_season, args.test_season
    )
    print(f"  Train: {len(train_rows)}  Val: {len(val_rows)}  Test: {len(test_rows)}")

    if not train_rows or not val_rows or not test_rows:
        print("ERROR: empty split — check season ranges", file=sys.stderr)
        sys.exit(1)

    X_tr, w_tr = to_arrays(train_rows, FEATURE_COLS)
    X_val, _   = to_arrays(val_rows,   FEATURE_COLS)
    X_te, _    = to_arrays(test_rows,  FEATURE_COLS)

    y_tr_mgn  = np.array([float(r['actual_margin']) for r in train_rows])
    y_val_mgn = np.array([float(r['actual_margin']) for r in val_rows])
    y_te_mgn  = np.array([float(r['actual_margin']) for r in test_rows])

    y_tr_tot  = np.array([float(r['actual_total']) for r in train_rows])
    y_val_tot = np.array([float(r['actual_total']) for r in val_rows])
    y_te_tot  = np.array([float(r['actual_total']) for r in test_rows])

    y_tr_h2h  = np.array([int(r['home_win']) for r in train_rows])
    y_val_h2h = np.array([int(r['home_win']) for r in val_rows])
    y_te_h2h  = np.array([int(r['home_win']) for r in test_rows])

    # ── Margin model ──
    print(f"\n{'─'*65}")
    print(f"  MARGIN MODEL")
    print(f"{'─'*65}")
    margin_model = train_regression(X_tr, y_tr_mgn, w_tr, X_val, y_val_mgn, 'margin')
    print(f"  Validation:")
    evaluate_regression(margin_model, X_val, y_val_mgn, 'margin')
    print(f"  Test (2025):")
    _, _, margin_preds = evaluate_regression(margin_model, X_te, y_te_mgn, 'margin')
    print(f"  Feature importance:")
    feature_importance_table(margin_model, FEATURE_COLS)

    # ── Total model ──
    print(f"\n{'─'*65}")
    print(f"  TOTAL MODEL")
    print(f"{'─'*65}")
    total_model = train_regression(X_tr, y_tr_tot, w_tr, X_val, y_val_tot, 'total')
    print(f"  Validation:")
    evaluate_regression(total_model, X_val, y_val_tot, 'total')
    print(f"  Test (2025):")
    evaluate_regression(total_model, X_te, y_te_tot, 'total')
    print(f"  Feature importance:")
    feature_importance_table(total_model, FEATURE_COLS)

    # ── H2H model ──
    print(f"\n{'─'*65}")
    print(f"  H2H MODEL (win/loss)")
    print(f"{'─'*65}")
    h2h_model = train_classifier(X_tr, y_tr_h2h, w_tr, X_val, y_val_h2h)
    print(f"  Validation:")
    evaluate_classifier(h2h_model, X_val, y_val_h2h, 'h2h')
    print(f"  Test (2025):")
    acc_2025, _, _ = evaluate_classifier(h2h_model, X_te, y_te_h2h, 'h2h')
    print(f"  Feature importance:")
    feature_importance_table(h2h_model, FEATURE_COLS)

    # ── Comparison vs ELO-only baseline ──
    print(f"\n{'─'*65}")
    print(f"  COMPARISON — 2025 test")
    print(f"{'─'*65}")
    elo_preds = np.array([
        float(r['elo_predicted_margin']) if r['elo_predicted_margin'] not in ('', None) else 3.5
        for r in test_rows
    ])
    naive_preds = np.full(len(test_rows), 3.5)

    ml_mae    = mean_absolute_error(y_te_mgn, margin_preds)
    elo_mae   = mean_absolute_error(y_te_mgn, elo_preds)
    naive_mae = mean_absolute_error(y_te_mgn, naive_preds)
    elo_acc   = accuracy_score(y_te_h2h, (elo_preds > 0).astype(int))

    print(f"  Margin MAE:")
    print(f"    ML model:     {ml_mae:.2f} pts")
    print(f"    ELO only:     {elo_mae:.2f} pts")
    print(f"    Naive (+3.5): {naive_mae:.2f} pts")
    print(f"  Win accuracy:")
    print(f"    ML model:     {acc_2025*100:.1f}%")
    print(f"    ELO only:     {elo_acc*100:.1f}%")

    # ── Save models ──
    print(f"\n{'─'*65}")
    print(f"  Saving models ...")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    version = datetime.now().strftime('%Y%m%d')

    import joblib
    margin_path = MODELS_DIR / f'margin_model_v{version}.joblib'
    total_path  = MODELS_DIR / f'total_model_v{version}.joblib'
    h2h_path    = MODELS_DIR / f'h2h_model_v{version}.joblib'
    cols_path   = MODELS_DIR / 'feature_columns.json'

    joblib.dump(margin_model, margin_path)
    joblib.dump(total_model,  total_path)
    joblib.dump(h2h_model,    h2h_path)
    with open(cols_path, 'w') as f:
        json.dump(FEATURE_COLS, f, indent=2)

    print(f"    {margin_path.name}")
    print(f"    {total_path.name}")
    print(f"    {h2h_path.name}")
    print(f"    feature_columns.json")
    print(f"\nDone.")


if __name__ == '__main__':
    main()
