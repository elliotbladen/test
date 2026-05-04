#!/usr/bin/env python3
"""
ml/rebuild_models.py

Build feature matrix directly from rlp_match_data.csv + rlp_ref_*.csv,
then train and save the three XGBoost models (margin, total, h2h).

Run this whenever models are missing (gitignored binaries) or need refresh:
    python ml/rebuild_models.py

Models are saved to ml/models/ as:
    margin_model_v<YYYYMMDD>.joblib
    total_model_v<YYYYMMDD>.joblib
    h2h_model_v<YYYYMMDD>.joblib
    feature_columns.json
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score, mean_absolute_error

ROOT       = Path(__file__).resolve().parent.parent
RLP_GAMES  = ROOT / 'ml' / 'data' / 'rlp_match_data.csv'
RLP_REFS   = ROOT / 'ml' / 'data' / 'rlp_ref_data.csv'
RLP_RMATCH = ROOT / 'ml' / 'data' / 'rlp_ref_match_data.csv'
MODELS_DIR = ROOT / 'ml' / 'models'

FIRST_SEASON = 2009
LAST_SEASON  = 2025

STARTING_ELO   = 1500.0
REVERSION_RATE = 0.25
HOME_ADVANTAGE = 3.5
ERA_K = {y: 20 for y in range(2009, 2030)}
ERA_K.update({2020: 28, 2021: 24})

MIN_SAMPLE_VENUE = 5
MIN_SAMPLE_REF   = 10
DECAY_RATE       = 0.80
BASE_SEASON      = 2025

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

NAME_MAP = {
    'Canterbury Bulldogs':            'Canterbury-Bankstown Bulldogs',
    'Cronulla Sharks':                'Cronulla-Sutherland Sharks',
    'Cronulla-Sutherland Sharks':     'Cronulla-Sutherland Sharks',
    'Manly Sea Eagles':               'Manly-Warringah Sea Eagles',
    'Manly Warringah Sea Eagles':     'Manly-Warringah Sea Eagles',
    'Manly-Warringah Sea Eagles':     'Manly-Warringah Sea Eagles',
    'North QLD Cowboys':              'North Queensland Cowboys',
    'North Queensland Cowboys':       'North Queensland Cowboys',
    'St George Dragons':              'St. George Illawarra Dragons',
    'St George Illawarra':            'St. George Illawarra Dragons',
    'St. George Illawarra Dragons':   'St. George Illawarra Dragons',
    'St George Illawarra Dragons':    'St. George Illawarra Dragons',
    'Brisbane':                       'Brisbane Broncos',
    'Brisbane Broncos':               'Brisbane Broncos',
    'Canberra':                       'Canberra Raiders',
    'Canberra Raiders':               'Canberra Raiders',
    'Gold Coast':                     'Gold Coast Titans',
    'Gold Coast Titans':              'Gold Coast Titans',
    'Melbourne':                      'Melbourne Storm',
    'Melbourne Storm':                'Melbourne Storm',
    'Newcastle':                      'Newcastle Knights',
    'Newcastle Knights':              'Newcastle Knights',
    'Parramatta':                     'Parramatta Eels',
    'Parramatta Eels':                'Parramatta Eels',
    'Penrith':                        'Penrith Panthers',
    'Penrith Panthers':               'Penrith Panthers',
    'South Sydney':                   'South Sydney Rabbitohs',
    'South Sydney Rabbitohs':         'South Sydney Rabbitohs',
    'Sydney Roosters':                'Sydney Roosters',
    'Wests Tigers':                   'Wests Tigers',
    'Warriors':                       'New Zealand Warriors',
    'NZ Warriors':                    'New Zealand Warriors',
    'New Zealand Warriors':           'New Zealand Warriors',
    'Dolphins':                       'Dolphins',
}


def canon(name: str) -> str:
    s = str(name).strip()
    return NAME_MAP.get(s, s)


def safe_float(v):
    if v in (None, '', 'None', 'NA', 'na'):
        return None
    try:
        f = float(v)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None


def elo_win_prob(diff: float) -> float:
    return 1.0 / (1.0 + 10 ** (-diff / 400.0))


def rest_cls(days):
    if days is None:
        return None
    if days <= 6:  return 1
    if days <= 9:  return 2
    if days <= 13: return 3
    return 4


def season_weight(season: int) -> float:
    return DECAY_RATE ** max(0, BASE_SEASON - season)


# ── 1. Load RLP games ─────────────────────────────────────────────────────────

def load_games():
    rows = []
    with open(RLP_GAMES) as f:
        for row in csv.DictReader(f):
            cy = row.get('competition_year', '')
            if not cy.startswith('NRL '):
                continue
            try:
                season = int(cy.split()[-1])
            except ValueError:
                continue
            if season < FIRST_SEASON or season > LAST_SEASON:
                continue
            hs = safe_float(row.get('home_team_score'))
            as_ = safe_float(row.get('away_team_score'))
            if hs is None or as_ is None:
                continue
            rows.append({
                'rlp_id':   row['match_id'],
                'season':   season,
                'date':     row['date'],
                'venue_id': row['venue_id'],
                'home':     canon(row['home_team']),
                'away':     canon(row['away_team']),
                'hs':       int(hs),
                'as_':      int(as_),
                'margin':   int(hs) - int(as_),
                'total':    int(hs) + int(as_),
                'home_win': 1 if hs > as_ else 0,
                'h_pen':    safe_float(row.get('home_team_penalties')),
                'a_pen':    safe_float(row.get('away_team_penalties')),
            })
    rows.sort(key=lambda r: (r['date'], r['rlp_id']))
    return rows


# ── 2. ELO (pre-game) ────────────────────────────────────────────────────────

def add_elo(games):
    elo = defaultdict(lambda: STARTING_ELO)
    cur_season = None

    for g in games:
        if g['season'] != cur_season:
            if cur_season is not None:
                for t in list(elo.keys()):
                    elo[t] += REVERSION_RATE * (STARTING_ELO - elo[t])
            cur_season = g['season']

        he = elo[g['home']]
        ae = elo[g['away']]
        diff = he - ae
        exp  = elo_win_prob(diff)
        act  = 1.0 if g['margin'] > 0 else 0.0
        k    = ERA_K.get(g['season'], 20)

        g['elo_diff']              = round(diff, 1)
        g['home_elo_win_prob']     = round(exp, 4)
        g['elo_predicted_margin']  = round(diff * 0.04 + HOME_ADVANTAGE, 2)

        elo[g['home']] += k * (act - exp)
        elo[g['away']] += k * ((1 - act) - (1 - exp))


# ── 3. Rest / form ────────────────────────────────────────────────────────────

def add_form(games):
    last   = {}   # team → {'date': str, 'margin': int}
    wins   = defaultdict(int)
    losses = defaultdict(int)

    for g in games:
        gd = g['date']

        def rest(team):
            lg = last.get(team)
            if not lg: return None
            from datetime import date as _date
            d1 = _date.fromisoformat(gd)
            d2 = _date.fromisoformat(lg['date'])
            diff = (d1 - d2).days
            return diff if diff > 0 else None

        hrd = rest(g['home'])
        ard = rest(g['away'])
        hpm = (last.get(g['home']) or {}).get('margin')
        apm = (last.get(g['away']) or {}).get('margin')

        g['home_rest_days']    = hrd
        g['away_rest_days']    = ard
        g['rest_diff']         = (hrd - ard) if (hrd and ard) else None
        g['home_rest_class']   = rest_cls(hrd)
        g['away_rest_class']   = rest_cls(ard)
        g['home_had_bye']      = 1 if (hrd and hrd >= 14) else 0
        g['away_had_bye']      = 1 if (ard and ard >= 14) else 0
        g['home_prev_margin']  = hpm
        g['away_prev_margin']  = apm
        g['home_off_big_win']  = 1 if (hpm and hpm >= 20) else 0
        g['home_off_big_loss'] = 1 if (hpm and hpm <= -20) else 0
        g['away_off_big_win']  = 1 if (apm and apm >= 20) else 0
        g['away_off_big_loss'] = 1 if (apm and apm <= -20) else 0
        g['home_win_streak']   = wins[g['home']]
        g['away_win_streak']   = wins[g['away']]
        g['home_loss_streak']  = losses[g['home']]
        g['away_loss_streak']  = losses[g['away']]

        hm = g['margin']
        if hm > 0:
            wins[g['home']] += 1;   losses[g['home']] = 0
            losses[g['away']] += 1; wins[g['away']] = 0
        elif hm < 0:
            losses[g['home']] += 1; wins[g['home']] = 0
            wins[g['away']] += 1;   losses[g['away']] = 0

        last[g['home']] = {'date': gd, 'margin': hm}
        last[g['away']] = {'date': gd, 'margin': -hm}


# ── 4. Venue ──────────────────────────────────────────────────────────────────

def add_venue(games):
    totals = defaultdict(list)
    hw     = defaultdict(list)
    for g in games:
        vid = g['venue_id']
        n   = len(totals[vid])
        if n >= MIN_SAMPLE_VENUE:
            g['venue_avg_total']    = round(sum(totals[vid]) / n, 2)
            g['venue_home_win_pct'] = round(sum(hw[vid]) / n, 3)
        else:
            g['venue_avg_total']    = None
            g['venue_home_win_pct'] = None
        totals[vid].append(g['total'])
        hw[vid].append(g['home_win'])


# ── 5. Referee ────────────────────────────────────────────────────────────────

def add_referee(games):
    ref_names = {}
    with open(RLP_REFS) as f:
        for row in csv.DictReader(f):
            ref_names[row['ref_id']] = row['full_name'].strip()

    assignments = {}
    with open(RLP_RMATCH) as f:
        for row in csv.DictReader(f):
            if row['match_id'] not in assignments:
                assignments[row['match_id']] = row['ref_id']

    for g in games:
        rid = assignments.get(g['rlp_id'])
        g['ref_name'] = ref_names.get(rid, '') if rid else ''

    ref_hist = defaultdict(list)
    for g in games:
        rname = g['ref_name']
        prior = ref_hist[rname]
        n     = len(prior)
        if n >= MIN_SAMPLE_REF:
            all_totals = [p['total'] for p in prior]
            avg_t = sum(all_totals) / n
            g['ref_total_diff']   = round(sum(t - avg_t for t in all_totals) / n, 3)
            pen = [p for p in prior if p.get('h_pen') is not None and p.get('a_pen') is not None]
            if pen:
                g['ref_penalty_rate'] = round(sum(p['h_pen'] + p['a_pen'] for p in pen) / len(pen), 3)
                g['ref_home_bias']    = round(sum(p['h_pen'] - p['a_pen'] for p in pen) / len(pen), 3)
            else:
                g['ref_penalty_rate'] = None
                g['ref_home_bias']    = None
            g['ref_home_win_pct'] = round(sum(p['home_win'] for p in prior) / n, 3)
        else:
            g['ref_total_diff']   = None
            g['ref_penalty_rate'] = None
            g['ref_home_bias']    = None
            g['ref_home_win_pct'] = None
        if rname:
            ref_hist[rname].append(g)


# ── 6. Arrays ─────────────────────────────────────────────────────────────────

def to_arrays(rows):
    X, w, ym, yt, yh = [], [], [], [], []
    for g in rows:
        feats = []
        for col in FEATURE_COLS:
            v = g.get(col)
            feats.append(float('nan') if v is None else float(v))
        X.append(feats)
        w.append(season_weight(g['season']))
        ym.append(float(g['margin']))
        yt.append(float(g['total']))
        yh.append(int(g['home_win']))
    return (np.array(X, np.float32), np.array(w, np.float32),
            np.array(ym, np.float32), np.array(yt, np.float32),
            np.array(yh, np.int32))


# ── 7. Train ──────────────────────────────────────────────────────────────────

def train_reg(X_tr, y_tr, w_tr, X_val, y_val, label):
    m = xgb.XGBRegressor(
        n_estimators=400, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=10,
        reg_alpha=0.1, reg_lambda=1.0, random_state=42, verbosity=0,
        early_stopping_rounds=30,
    )
    m.fit(X_tr, y_tr, sample_weight=w_tr, eval_set=[(X_val, y_val)], verbose=False)
    mae = mean_absolute_error(y_val, m.predict(X_val))
    print(f"  {label:<12}  val MAE = {mae:.2f} pts")
    return m


def train_cls(X_tr, y_tr, w_tr, X_val, y_val):
    m = xgb.XGBClassifier(
        n_estimators=400, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=10,
        reg_alpha=0.1, reg_lambda=1.0, random_state=42, verbosity=0,
        early_stopping_rounds=30, eval_metric='logloss',
    )
    m.fit(X_tr, y_tr, sample_weight=w_tr, eval_set=[(X_val, y_val)], verbose=False)
    acc = accuracy_score(y_val, (m.predict_proba(X_val)[:, 1] >= 0.5).astype(int))
    print(f"  {'h2h':<12}  val Acc  = {acc*100:.1f}%")
    return m


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"  NRL ML -- Rebuild Models  ({FIRST_SEASON}-{LAST_SEASON})")
    print(f"{'='*60}\n")

    print("Loading games ...")
    games = load_games()
    print(f"  {len(games)} games loaded")

    print("Building features ...")
    add_elo(games)
    add_form(games)
    add_venue(games)
    add_referee(games)

    # Travel / weather → NaN for historical (XGBoost handles natively)
    for g in games:
        g.setdefault('home_travel_km',  None)
        g.setdefault('away_travel_km',  None)
        g.setdefault('travel_diff',     None)
        g.setdefault('is_neutral_venue',0)
        g.setdefault('rain_mm',         None)
        g.setdefault('wind_kmh',        None)
        g.setdefault('wind_gusts_kmh',  None)
        g.setdefault('temp_c',          None)

    # Write referee log to ml/data/ so it survives git (not in ml/results/*.csv)
    ref_log_path = ROOT / 'ml' / 'data' / 'game_log_referee.csv'
    # Compute per-game ref_total_diff relative to season avg
    season_avgs = {}
    for s in set(g['season'] for g in games):
        sg = [g for g in games if g['season'] == s]
        season_avgs[s] = sum(g['total'] for g in sg) / len(sg)
    with open(ref_log_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'referee', 'ref_total_diff', 'ref_penalty_rate', 'ref_home_bias', 'ref_home_win_pct'
        ])
        writer.writeheader()
        for g in games:
            if not g.get('ref_name'):
                continue
            s_avg = season_avgs.get(g['season'], 45.0)
            h_pen = g.get('h_pen')
            a_pen = g.get('a_pen')
            writer.writerow({
                'referee':         g['ref_name'],
                'ref_total_diff':  round(g['total'] - s_avg, 3),
                'ref_penalty_rate': round(h_pen + a_pen, 3) if (h_pen is not None and a_pen is not None) else '',
                'ref_home_bias':    round(h_pen - a_pen, 3) if (h_pen is not None and a_pen is not None) else '',
                'ref_home_win_pct': g['home_win'],
            })
    print(f"  Referee log -> ml/data/game_log_referee.csv  ({len(games)} rows)")

    train = [g for g in games if g['season'] <= 2023]
    val   = [g for g in games if g['season'] == 2024]
    test  = [g for g in games if g['season'] == 2025]
    print(f"  Split — train: {len(train)}  val: {len(val)}  test: {len(test)}\n")

    if not train or not val or not test:
        print("ERROR: empty split", file=sys.stderr)
        sys.exit(1)

    X_tr, w_tr, ym_tr, yt_tr, yh_tr = to_arrays(train)
    X_val, _, ym_val, yt_val, yh_val = to_arrays(val)
    X_te, _,  ym_te,  yt_te,  yh_te  = to_arrays(test)

    print("Training ...")
    margin_m = train_reg(X_tr, ym_tr, w_tr, X_val, ym_val, 'margin')
    total_m  = train_reg(X_tr, yt_tr, w_tr, X_val, yt_val, 'total')
    h2h_m    = train_cls(X_tr, yh_tr, w_tr, X_val, yh_val)

    m_mae = mean_absolute_error(ym_te, margin_m.predict(X_te))
    t_mae = mean_absolute_error(yt_te, total_m.predict(X_te))
    h_acc = accuracy_score(yh_te, (h2h_m.predict_proba(X_te)[:, 1] >= 0.5).astype(int))
    print(f"\n  Test 2025: margin MAE={m_mae:.2f}  total MAE={t_mae:.2f}  H2H={h_acc*100:.1f}%")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    version = datetime.now().strftime('%Y%m%d')
    joblib.dump(margin_m, MODELS_DIR / f'margin_model_v{version}.joblib')
    joblib.dump(total_m,  MODELS_DIR / f'total_model_v{version}.joblib')
    joblib.dump(h2h_m,    MODELS_DIR / f'h2h_model_v{version}.joblib')
    with open(MODELS_DIR / 'feature_columns.json', 'w') as f:
        json.dump(FEATURE_COLS, f, indent=2)

    print(f"\n  Saved -> ml/models/*_v{version}.joblib")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
