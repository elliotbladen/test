#!/usr/bin/env python3
"""
scripts/prepare_afl_round.py

AFL round pricing — Rules engine (T1–T5) with ML shadow comparison.

Architecture:
    T1: Rules-based baseline — ELO margin + team scoring rates (explicit, auditable)
    T2: Style matchup — 5-family z-score engine from Footywire snapshots
    T3: Situational — rest, travel, form momentum, occasion
    T4: Venue — fortress ratings, venue scoring tendencies
    T5: Injuries — player quality × position impact model
    ML: Shadow mode — XGBoost run separately for divergence comparison only

The ML is NOT used in the primary pricing path.  It runs in parallel so that
divergences between the rules engine and the data-learned model can be flagged
as confidence signals (large divergence = higher uncertainty).

USAGE
-----
    python3 scripts/prepare_afl_round.py --season 2026 --round 7
"""

import argparse
import csv
import math
import pickle
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pricing.afl_tier3_situational import compute_t3
from pricing.afl_tier4_venue import compute_t4
from pricing.afl_tier5_injury import compute_t5
from pricing.afl_tier6_emotional import compute_t6
from pricing.afl_tier7_weather import compute_t7

import numpy as np
import pandas as pd

ROOT       = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / 'ml/afl/results/models'
FEATURES   = ROOT / 'ml/afl/results/features_afl.csv'
SNAP_CSV   = ROOT / 'data/footywire_snapshots.csv'
HIST_CSV   = ROOT / 'data/footywire_team_stats.csv'

# ── R7 2026 fixture (hardcoded — load from DB once fixture ingestion is built) ─
FIXTURE = {
    7: [
        ('Western Bulldogs',              'Sydney Swans',                  'Marvel Stadium',   '2026-04-23'),
        ('Richmond Tigers',               'Melbourne Demons',               'MCG',              '2026-04-24'),
        ('Hawthorn Hawks',                'Gold Coast Suns',               'UTAS Stadium',     '2026-04-25'),
        ('Essendon Bombers',              'Collingwood Magpies',           'MCG',              '2026-04-25'),
        ('Port Adelaide Power',           'Geelong Cats',                  'Adelaide Oval',    '2026-04-25'),
        ('Fremantle Dockers',             'Carlton Blues',                 'Optus Stadium',    '2026-04-25'),
        ('St Kilda Saints',               'West Coast Eagles',             'Marvel Stadium',   '2026-04-26'),
        ('Brisbane Lions',                'Adelaide Crows',                'The Gabba',        '2026-04-26'),
        ('Greater Western Sydney Giants', 'North Melbourne Kangaroos',     'Manuka Oval',      '2026-04-26'),
    ]
}

# ── T5 Injuries — update manually before each round ──────────────────────────
# Format: { 'Team Name': [{'player': str, 'position': str, 'quality': str}, ...] }
# Positions: key_forward, key_defender, ruck, midfielder, winger, utility
# Quality:   elite, good, average, depth
#
INJURIES = {
    7: {
        # Sources: ESPN, SEN, ZeroHanger, bets.com.au — R7 2026 team lists
        'Western Bulldogs': [
            {'player': 'Sam Darcy',       'position': 'key_forward',  'quality': 'elite'},   # ACL — season done
            {'player': 'Tom Liberatore',  'position': 'midfielder',   'quality': 'good'},    # concussion
            {'player': 'Rory Lobb',       'position': 'ruck',         'quality': 'good'},    # injured
            {'player': "James O'Donnell", 'position': 'key_defender', 'quality': 'average'}, # injured
        ],
        'Sydney Swans': [
            {'player': 'Isaac Heeney',    'position': 'midfielder',   'quality': 'elite'},   # calf
        ],
        'Richmond Tigers': [
            {'player': 'Sam Banks',       'position': 'midfielder',   'quality': 'average'}, # collarbone
            {'player': 'Maurice Rioli',   'position': 'winger',       'quality': 'good'},    # hamstring
            {'player': 'Tim Taranto',     'position': 'midfielder',   'quality': 'good'},    # concussion
        ],
        'Melbourne Demons': [
            {'player': 'Harrison Petty',  'position': 'key_defender', 'quality': 'good'},    # concussion
        ],
        'Hawthorn Hawks': [
            {'player': 'James Sicily',    'position': 'key_defender', 'quality': 'elite'},   # 1-match ban (MRO)
            {'player': 'Dylan Moore',     'position': 'winger',       'quality': 'good'},    # 1-match ban (MRO)
        ],
        'Carlton Blues': [
            {'player': 'Harry McKay',     'position': 'key_forward',  'quality': 'elite'},   # injured
            {'player': 'Marc Pittonet',   'position': 'ruck',         'quality': 'average'}, # injured
            {'player': 'Elijah Hollands', 'position': 'midfielder',   'quality': 'average'}, # injured
        ],
        'Port Adelaide Power': [
            {'player': 'Todd Marshall',   'position': 'key_forward',  'quality': 'good'},    # late out
        ],
        'Geelong Cats': [
            {'player': 'Sam De Koning',   'position': 'key_defender', 'quality': 'good'},    # late out
        ],
        'Brisbane Lions': [
            {'player': 'Noah Answerth',   'position': 'key_defender', 'quality': 'average'}, # injured
            {'player': 'Jarrod Berry',    'position': 'midfielder',   'quality': 'good'},    # injured
        ],
        'Adelaide Crows': [
            {'player': 'Alex Neal-Bullen','position': 'utility',      'quality': 'average'}, # injured
        ],
    }
}

# ── T6 Emotional flags — update manually before each round ───────────────────
# Format: { round_num: { 'Team Name': [{'flag_type': str, 'flag_strength': str,
#                                        'player_name': str, 'notes': str}] } }
# flag_type values: milestone | new_coach | star_return | shame_blowout |
#                   farewell | personal_tragedy | rivalry_derby | must_win
# flag_strength: minor | normal | major
#
EMOTIONAL_FLAGS = {
    7: {
        'Essendon Bombers': [
            {'flag_type': 'rivalry_derby', 'flag_strength': 'major',
             'player_name': None, 'notes': 'ANZAC Day vs Collingwood — biggest regular-season game'},
        ],
        'Collingwood Magpies': [
            {'flag_type': 'rivalry_derby', 'flag_strength': 'major',
             'player_name': None, 'notes': 'ANZAC Day vs Essendon — biggest regular-season game'},
        ],
    }
}

# ── T7 Weather — update on game day ──────────────────────────────────────────
# Format: { round_num: { (home_team, away_team): {
#               'precip_mm': float, 'wind_kmh': float,
#               'temp_c': float, 'dew_point_c': float,
#               'kickoff': 'HH:MM'  (local 24h time)
#           } } }
# Leave entry empty ({}) or omit for clear/unknown conditions.
#
# Rain tiers:  0–5mm = light (-4.5),  5–10mm = moderate (-7.0),  >10mm = heavy (-9.0)
# Wind tiers:  20–29 km/h = moderate (-2.8),  30–39 = strong (-6.0),  ≥40 = very strong (-8.0)
# Cold:        temp_c < 5°C → -3.5 pts (UTAS/MCG July night games)
# Dew:         kickoff ≥18:30, dew_point >12°C, spread <5°C
# MCG wind:    wind_venue_factor=1.1 applied automatically when venue == 'MCG'
# Marvel roof: pass empty {} when roof is confirmed closed
#
WEATHER = {
    7: {
        # Example — fill in on game day:
        # ('Essendon Bombers', 'Collingwood Magpies'): {
        #     'precip_mm': 0.0, 'wind_kmh': 18.0,
        #     'temp_c': 16.0, 'dew_point_c': 9.0, 'kickoff': '15:20',
        # },
    }
}

# Home advantage in ELO points (from game_log.py)
HOME_ADV_ELO = 65.0     # aligned with game_log.py (8.5 pts / 0.13 ≈ 65 ELO pts)
POINTS_PER_ELO = 0.13

# T1 rules-baseline constants
LEAGUE_AVG_PER_TEAM = 83.5   # 2022-2025 actual avg: 83.6 per team (167.2 combined)
T1_REGRESSION       = 0.25   # 25 % regression to league mean for scoring rates

# ── T2 config ─────────────────────────────────────────────────────────────────
T2_FAMILIES = {
    'A': {
        'label': 'Contested',
        # Research: raw clearances are weak margin predictors (5/10 GF winners lost clearance battle).
        # Contested possessions + ruck dominance (hitouts) are the meaningful signals.
        # Clearances reduced to minor — only kept to capture stoppage chain initiation.
        'stats': [('cp_pg', 0.50, True), ('hitouts_pg', 0.30, True),
                  ('centre_cl_pg', 0.15, True), ('stoppage_cl_pg', 0.05, True)],
        'inner_cap': 3.0,
    },
    'B': {
        'label': 'Territory',
        # Research: metres gained R=0.82 — strongest single AFL predictor. Lifted to 0.55.
        'stats': [('mg_pg', 0.55, True), ('disposal_eff_pct', 0.30, True),
                  ('kicking_ratio', 0.15, True)],
        'inner_cap': 3.0,
    },
    'C': {
        'label': 'Fwd Entry',
        'stats': [('inside_50s_pg', 0.35, True), ('marks_i50_pg', 0.30, True),
                  ('goal_conv_pct', 0.25, True), ('tackles_i50_pg', 0.10, True)],
        'inner_cap': 4.0,
    },
    'D': {
        'label': 'Defence',
        'stats': [('intercepts_pg', 0.40, True), ('rebound_50s_pg', 0.30, True),
                  ('one_pct_pg', 0.20, True), ('cont_marks_pg', 0.10, True)],
        'inner_cap': 3.0,
    },
    'E': {
        'label': 'Pressure',
        'stats': [('tackles_pg', 0.40, True), ('turnovers_pg', 0.30, False),
                  ('clangers_pg', 0.30, False)],
        'inner_cap': 2.0,
    },
}
T2_MAX = 7.0
T2_TOT_SCALE = 0.30
T2_TOT_MAX   = 3.0

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_models():
    margin_model = pickle.load(open(MODELS_DIR / 'margin_model.pkl', 'rb'))
    total_model  = pickle.load(open(MODELS_DIR / 'total_model.pkl',  'rb'))
    h2h_model    = pickle.load(open(MODELS_DIR / 'h2h_model.pkl',    'rb'))
    return margin_model, total_model, h2h_model


def get_current_elo(features_df: pd.DataFrame) -> dict:
    """Latest ELO for each team from the features CSV (post R6)."""
    elo = {}
    for _, row in features_df.sort_values('date').iterrows():
        elo[row['home_team']] = row['home_elo']
        elo[row['away_team']] = row['away_elo']
    return elo


def get_recent_form(features_df: pd.DataFrame, team: str, before_date: str, n: int = 5) -> dict:
    """Win%, avg margin over last n games for a team."""
    mask = ((features_df['home_team'] == team) | (features_df['away_team'] == team)) & \
           (features_df['date'] < before_date)
    recent = features_df[mask].tail(n)
    if recent.empty:
        return {'win_pct': 0.5, 'avg_margin': 0.0, 'last_margin': 0.0, 'games': 0}
    wins, margins = [], []
    for _, g in recent.iterrows():
        if g['home_team'] == team:
            margins.append(g['home_margin'])
            wins.append(1 if g['home_margin'] > 0 else 0)
        else:
            margins.append(-g['home_margin'])
            wins.append(1 if g['home_margin'] < 0 else 0)
    return {
        'win_pct':     sum(wins) / len(wins),
        'avg_margin':  sum(margins) / len(margins),
        'last_margin': margins[-1],
        'games':       len(margins),
    }


def get_venue_stats(features_df: pd.DataFrame, venue: str) -> dict:
    v = features_df[features_df['venue'] == venue]
    if v.empty:
        return {'venue_games': 0, 'venue_avg_total': 165.0, 'venue_home_win_pct': 0.60}
    totals = v['home_score'] + v['away_score']
    return {
        'venue_games':        len(v),
        'venue_avg_total':    totals.mean(),
        'venue_home_win_pct': (v['home_margin'] > 0).mean(),
    }


FEATURE_COLS = [
    'elo_diff', 'elo_win_prob', 'home_rest_days', 'away_rest_days', 'rest_diff',
    'home_travel_km', 'away_travel_km', 'travel_diff_km',
    'home_win_pct', 'home_avg_margin', 'home_last_margin',
    'home_off_big_win', 'home_off_big_loss', 'home_win_streak', 'home_loss_streak',
    'away_win_pct', 'away_avg_margin', 'away_last_margin',
    'away_off_big_win', 'away_off_big_loss', 'away_win_streak', 'away_loss_streak',
    'form_win_pct_diff', 'form_margin_diff',
    'venue_games', 'venue_avg_total', 'venue_home_win_pct',
    'is_final',
]


def build_feature_row(home: str, away: str, venue: str, date: str,
                      elo: dict, features_df: pd.DataFrame) -> dict:
    home_elo = elo.get(home, 1500.0)
    away_elo = elo.get(away, 1500.0)
    elo_diff = (home_elo + HOME_ADV_ELO) - away_elo
    elo_win_prob = 1 / (1 + 10 ** (-elo_diff / 400))

    hf = get_recent_form(features_df, home, date)
    af = get_recent_form(features_df, away, date)
    vs = get_venue_stats(features_df, venue)

    # Streak calc
    def streak(df, team, before, home_or_away):
        mask = (df[f'{home_or_away}_team'] == team) & (df['date'] < before)
        recent = df[mask].tail(5)
        w = s = 0
        for _, g in recent.iloc[::-1].iterrows():
            won = (g['home_margin'] > 0) if home_or_away == 'home' else (g['home_margin'] < 0)
            if won:
                w += 1; s = 0
            else:
                s += 1; w = 0
        return w, s

    hw, hl = streak(features_df, home, date, 'home')
    aw, al = streak(features_df, away, date, 'away')

    return {
        'elo_diff':          elo_diff,
        'elo_win_prob':      elo_win_prob,
        'home_rest_days':    7.0,
        'away_rest_days':    7.0,
        'rest_diff':         0.0,
        'home_travel_km':    0.0,
        'away_travel_km':    500.0,
        'travel_diff_km':   -500.0,
        'home_win_pct':      hf['win_pct'],
        'home_avg_margin':   hf['avg_margin'],
        'home_last_margin':  hf['last_margin'],
        'home_form_games':   hf['games'],
        'home_off_big_win':  int(hf['last_margin'] > 30),
        'home_off_big_loss': int(hf['last_margin'] < -30),
        'home_win_streak':   hw,
        'home_loss_streak':  hl,
        'away_win_pct':      af['win_pct'],
        'away_avg_margin':   af['avg_margin'],
        'away_last_margin':  af['last_margin'],
        'away_form_games':   af['games'],
        'away_off_big_win':  int(af['last_margin'] > 30),
        'away_off_big_loss': int(af['last_margin'] < -30),
        'away_win_streak':   aw,
        'away_loss_streak':  al,
        'form_win_pct_diff': hf['win_pct'] - af['win_pct'],
        'form_margin_diff':  hf['avg_margin'] - af['avg_margin'],
        'is_final':          0,
        'venue_games':       vs['venue_games'],
        'venue_avg_total':   vs['venue_avg_total'],
        'venue_home_win_pct':vs['venue_home_win_pct'],
    }


# ── T2 style engine ───────────────────────────────────────────────────────────

def load_style_snapshot(season: int, round_num: int) -> dict:
    """Load most recent snapshot at or before round_num. Falls back to full-season."""
    # Try snapshots first
    if SNAP_CSV.exists():
        rows = {}
        with open(SNAP_CSV) as f:
            for r in csv.DictReader(f):
                if int(r['season']) == season and int(r['round_number']) <= round_num:
                    rows[r['team_name']] = r
        if rows:
            return rows

    # Fallback: full-season averages from prior year
    fallback = {}
    if HIST_CSV.exists():
        with open(HIST_CSV) as f:
            for r in csv.DictReader(f):
                if int(r['season']) == season - 1:
                    fallback[r['team_name']] = r
    return fallback


def compute_league_norms(rows: dict) -> dict:
    all_fields = {f for fam in T2_FAMILIES.values() for f, _, _ in fam['stats']}
    norms = {}
    for field in all_fields:
        vals = []
        for r in rows.values():
            v = r.get(field)
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
        if len(vals) > 1:
            mean = sum(vals) / len(vals)
            std  = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))
            norms[field] = (mean, max(std, 0.001))
        else:
            norms[field] = (0.0, 1.0)
    return norms


def family_score(team_row: dict, family_def: dict, norms: dict) -> float:
    total_w, total_z = 0.0, 0.0
    for field, weight, higher_better in family_def['stats']:
        try:
            val = float(team_row.get(field, 0) or 0)
        except (TypeError, ValueError):
            continue
        mean, std = norms.get(field, (0.0, 1.0))
        z = (val - mean) / std
        if not higher_better:
            z = -z
        total_z += z * weight
        total_w += weight
    return total_z / total_w if total_w > 0 else 0.0


def compute_t2(home_row, away_row, norms) -> dict:
    if home_row is None or away_row is None:
        return {'t2_handicap': 0.0, 't2_totals': 0.0, 'families': {}}

    families = {}
    total_pts = 0.0
    for fk, fdef in T2_FAMILIES.items():
        hz = family_score(home_row, fdef, norms)
        az = family_score(away_row, fdef, norms)
        diff = hz - az
        raw_pts = diff * (fdef['inner_cap'] / 1.5)   # 1.5 z ≈ inner_cap pts
        pts = max(-fdef['inner_cap'], min(fdef['inner_cap'], raw_pts))
        families[fk] = {'home_z': round(hz, 2), 'away_z': round(az, 2), 'pts': round(pts, 2)}
        total_pts += pts

    t2_hcp = max(-T2_MAX, min(T2_MAX, total_pts))
    t2_tot = max(-T2_TOT_MAX, min(T2_TOT_MAX, total_pts * T2_TOT_SCALE))
    return {'t2_handicap': round(t2_hcp, 2), 't2_totals': round(t2_tot, 2), 'families': families}


# ── H2H from margin ──────────────────────────────────────────────────────────

def margin_to_h2h(margin: float, std: float = 36.0) -> tuple[float, float]:
    """Convert expected margin to win probability using normal distribution."""
    from scipy import stats as scipy_stats
    home_prob = scipy_stats.norm.cdf(margin / std)  # P(margin > 0)
    away_prob = 1 - home_prob
    return round(home_prob, 4), round(away_prob, 4)


def prob_to_odds(p: float) -> float:
    return round(1 / p, 2) if p > 0 else 999.99


# Residual std of total_model on 2021-2026 games (excl COVID 2020)
# Calculated from: python3 -c "... total_model residuals post-2020 ..."
TOTAL_STD = 22.7

def total_to_ou_odds(model_total: float, market_line: float,
                     std: float = TOTAL_STD) -> tuple[float, float, float, float]:
    """
    Given model predicted total and a market line, return fair O/U probabilities and odds.

    Args:
        model_total:  our fair total (from T1+T2+T3)
        market_line:  the bookmaker's over/under line
        std:          std dev of totals around model prediction (22.7 from 2021-2026)

    Returns:
        (p_over, p_under, odds_over, odds_under)
    """
    from scipy import stats as scipy_stats
    # P(actual > market_line) given model_total as the mean
    p_over  = 1 - scipy_stats.norm.cdf((market_line - model_total) / std)
    p_under = 1 - p_over
    return round(p_over, 4), round(p_under, 4), prob_to_odds(p_over), prob_to_odds(p_under)


def get_team_avg_scored(features_df: pd.DataFrame, team: str,
                        before_date: str, n: int = 8) -> float:
    """Average points scored by a team in their last n games (home or away)."""
    home = features_df[(features_df['home_team'] == team) &
                       (features_df['date'] < before_date)][['date', 'home_score']].rename(
                           columns={'home_score': 'score'})
    away = features_df[(features_df['away_team'] == team) &
                       (features_df['date'] < before_date)][['date', 'away_score']].rename(
                           columns={'away_score': 'score'})
    games = pd.concat([home, away]).sort_values('date').tail(n)
    if games.empty:
        return LEAGUE_AVG_PER_TEAM
    return float(games['score'].mean())


def compute_t1_rules(home: str, away: str, home_elo: float, away_elo: float,
                     features_df: pd.DataFrame, date: str, cal: dict) -> dict:
    """
    Pure rules-based T1 baseline for AFL.

    Margin : ELO differential × scaling factor — explicit and auditable.
    Total  : team scoring-rate averages, regressed to league mean.
              No venue or rest adjustments here — those belong to T3 / T4.
    """
    elo_diff  = (home_elo + HOME_ADV_ELO) - away_elo
    t1_margin = round(elo_diff * POINTS_PER_ELO + cal['margin_correction'], 1)

    home_rate = get_team_avg_scored(features_df, home, date)
    away_rate = get_team_avg_scored(features_df, away, date)

    # 25 % regression to league mean so small-sample teams don't dominate
    home_rate = home_rate * (1 - T1_REGRESSION) + LEAGUE_AVG_PER_TEAM * T1_REGRESSION
    away_rate = away_rate * (1 - T1_REGRESSION) + LEAGUE_AVG_PER_TEAM * T1_REGRESSION
    t1_total  = round(home_rate + away_rate + cal['total_correction'], 1)

    return {
        't1_margin': t1_margin,
        't1_total':  t1_total,
        'elo_diff':  round(elo_diff, 1),
        'home_rate': round(home_rate, 1),
        'away_rate': round(away_rate, 1),
    }


def compute_ml_bias(ml_total_model, features_df: pd.DataFrame,
                    calibration_seasons: tuple = (2022, 2023, 2024, 2025)) -> dict:
    """
    Compute ML total model bias on recent holdout seasons.

    Runs the XGBoost total model on all games from calibration_seasons,
    computes mean(actual - predicted), and returns a correction to apply
    to every new ML prediction so the shadow output is properly anchored.

    Returns:
        {'bias': float, 'n': int, 'mae': float}
        Apply as: ml_total_calibrated = ml_total_raw + bias
    """
    cal_df = features_df[
        features_df['season'].isin(calibration_seasons)
    ].dropna(subset=['total_score']).copy()

    if len(cal_df) < 20:
        return {'bias': 0.0, 'n': 0, 'mae': 0.0}

    X_cal = pd.DataFrame([
        build_feature_row.__wrapped__(r) if hasattr(build_feature_row, '__wrapped__')
        else {
            'elo_diff':           (float(r.get('home_elo', 1500)) + HOME_ADV_ELO) - float(r.get('away_elo', 1500)),
            'elo_win_prob':       1 / (1 + 10 ** (-((float(r.get('home_elo', 1500)) + HOME_ADV_ELO) - float(r.get('away_elo', 1500))) / 400)),
            'home_rest_days':     7.0,
            'away_rest_days':     7.0,
            'rest_diff':          0.0,
            'home_travel_km':     0.0,
            'away_travel_km':     500.0,
            'travel_diff_km':    -500.0,
            'home_win_pct':       float(r.get('home_win_pct', 0.5) or 0.5),
            'home_avg_margin':    float(r.get('home_avg_margin', 0.0) or 0.0),
            'home_last_margin':   float(r.get('home_last_margin', 0.0) or 0.0),
            'home_form_games':    5,
            'home_off_big_win':   int(float(r.get('home_last_margin', 0) or 0) > 30),
            'home_off_big_loss':  int(float(r.get('home_last_margin', 0) or 0) < -30),
            'home_win_streak':    0,
            'home_loss_streak':   0,
            'away_win_pct':       float(r.get('away_win_pct', 0.5) or 0.5),
            'away_avg_margin':    float(r.get('away_avg_margin', 0.0) or 0.0),
            'away_last_margin':   float(r.get('away_last_margin', 0.0) or 0.0),
            'away_form_games':    5,
            'away_off_big_win':   int(float(r.get('away_last_margin', 0) or 0) > 30),
            'away_off_big_loss':  int(float(r.get('away_last_margin', 0) or 0) < -30),
            'away_win_streak':    0,
            'away_loss_streak':   0,
            'form_win_pct_diff':  float(r.get('home_win_pct', 0.5) or 0.5) - float(r.get('away_win_pct', 0.5) or 0.5),
            'form_margin_diff':   float(r.get('home_avg_margin', 0.0) or 0.0) - float(r.get('away_avg_margin', 0.0) or 0.0),
            'is_final':           int(r.get('is_final', 0) or 0),
            'venue_games':        float(r.get('venue_games', 30) or 30),
            'venue_avg_total':    float(r.get('venue_avg_total', 165.0) or 165.0),
            'venue_home_win_pct': float(r.get('venue_home_win_pct', 0.60) or 0.60),
        }
        for _, r in cal_df.iterrows()
    ])[FEATURE_COLS]

    preds  = ml_total_model.predict(X_cal)
    actual = cal_df['total_score'].values
    bias   = float(np.mean(actual - preds))
    mae    = float(np.mean(np.abs(actual - preds)))
    return {'bias': round(bias, 1), 'n': len(cal_df), 'mae': round(mae, 1)}


def compute_season_calibration(features_df: pd.DataFrame, season: int) -> dict:
    """
    Compute mean residual of the rules T1 on current season results.

    - Margin correction: bias of ELO predictions vs actual margins.
    - Total correction : bias of team-rate predictions vs actual totals.

    Re-anchors the model if 2026 is scoring systematically above/below
    what current ELO ratings and form averages would predict.
    """
    season_df = features_df[features_df['season'] == season].dropna(
        subset=['home_margin', 'home_elo', 'away_elo', 'total_score'])
    if len(season_df) < 5:
        return {'margin_correction': 0.0, 'total_correction': 0.0, 'n': 0}

    elo_margins, rate_totals = [], []
    for _, row in season_df.iterrows():
        elo_diff = (float(row['home_elo']) + HOME_ADV_ELO) - float(row['away_elo'])
        elo_margins.append(elo_diff * POINTS_PER_ELO)

        h = get_team_avg_scored(season_df, row['home_team'], row['date'])
        a = get_team_avg_scored(season_df, row['away_team'], row['date'])
        h = h * (1 - T1_REGRESSION) + LEAGUE_AVG_PER_TEAM * T1_REGRESSION
        a = a * (1 - T1_REGRESSION) + LEAGUE_AVG_PER_TEAM * T1_REGRESSION
        rate_totals.append(h + a)

    margin_bias = float(np.mean(season_df['home_margin'].values - np.array(elo_margins)))
    total_bias  = float(np.mean(season_df['total_score'].values  - np.array(rate_totals)))

    return {
        'margin_correction': round(margin_bias, 2),
        'total_correction':  round(total_bias,  2),
        'n': len(season_df),
    }


def rest_days(features_df: pd.DataFrame, team: str, game_date: str):
    mask = ((features_df['home_team'] == team) | (features_df['away_team'] == team)) & \
           (features_df['date'] < game_date)
    last = features_df[mask].tail(1)
    if last.empty:
        return None
    return (datetime.strptime(game_date, '%Y-%m-%d') -
            datetime.strptime(last.iloc[0]['date'], '%Y-%m-%d')).days


def last_margin(features_df: pd.DataFrame, team: str, game_date: str):
    mask = ((features_df['home_team'] == team) | (features_df['away_team'] == team)) & \
           (features_df['date'] < game_date)
    last = features_df[mask].tail(1)
    if last.empty:
        return None
    row = last.iloc[0]
    return row['home_margin'] if row['home_team'] == team else -row['home_margin']


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--round',  type=int, default=7)
    args = parser.parse_args()

    games = FIXTURE.get(args.round)
    if not games:
        print(f'No fixture for R{args.round}. Add to FIXTURE dict.')
        return

    print(f'\nLoading data...')
    features_df = pd.read_csv(FEATURES)
    features_df = features_df[features_df['season'] <= args.season].copy()
    elo = get_current_elo(features_df[features_df['season'] == args.season])

    style_rows = load_style_snapshot(args.season, args.round)
    norms      = compute_league_norms(style_rows) if style_rows else {}
    snap_label = f'R{args.round} snapshot' if style_rows else 'no style data'
    print(f'Style data: {snap_label}  ({len(style_rows)} teams)')

    cal = compute_season_calibration(features_df, args.season)
    print(f'Rules T1 calibration ({args.season}, n={cal["n"]}):  '
          f'margin {cal["margin_correction"]:+.1f} pts,  total {cal["total_correction"]:+.1f} pts')

    # Load ML models for shadow section only
    try:
        ml_margin_model, ml_total_model, ml_h2h_model = load_models()
        ml_available = True
        ml_bias = compute_ml_bias(ml_total_model, features_df)
        print(f'ML total bias (2022–2025, n={ml_bias["n"]}):  {ml_bias["bias"]:+.1f} pts  '
              f'(MAE {ml_bias["mae"]:.1f} pts)  — correction applied to shadow totals')
    except Exception as e:
        ml_available = False
        ml_bias = {'bias': 0.0, 'n': 0, 'mae': 0.0}
        print(f'  (ML models not available — shadow section will be skipped)')

    results = []
    for home, away, venue, date in games:
        feat = build_feature_row(home, away, venue, date, elo, features_df)
        X    = pd.DataFrame([feat])[FEATURE_COLS]

        # ── T1: Rules-based baseline ──────────────────────────────────────────
        home_elo = elo.get(home, 1500.0)
        away_elo = elo.get(away, 1500.0)
        t1 = compute_t1_rules(home, away, home_elo, away_elo, features_df, date, cal)
        t1_margin = t1['t1_margin']
        t1_total  = t1['t1_total']

        # ── ML shadow predictions (stored, not used in pricing) ───────────────
        if ml_available:
            ml_margin_raw = float(ml_margin_model.predict(X)[0])
            ml_total_raw  = float(ml_total_model.predict(X)[0])
            ml_total_cal  = ml_total_raw + ml_bias['bias']   # bias-corrected total
            ml_h2h_prob   = float(ml_h2h_model.predict_proba(X)[0][1])
        else:
            ml_margin_raw = ml_total_raw = ml_total_cal = ml_h2h_prob = None

        home_style = style_rows.get(home)
        away_style = style_rows.get(away)
        t2 = compute_t2(home_style, away_style, norms)

        # T3 — situational
        t3 = compute_t3(
            home=home, away=away, venue=venue, game_date=date,
            home_rest=rest_days(features_df, home, date),
            away_rest=rest_days(features_df, away, date),
            home_last_margin=last_margin(features_df, home, date),
            away_last_margin=last_margin(features_df, away, date),
        )

        t4 = compute_t4(home=home, away=away, venue=venue)

        round_injuries = INJURIES.get(args.round, {})
        t5 = compute_t5(
            home_outs=round_injuries.get(home, []),
            away_outs=round_injuries.get(away, []),
        )

        # T6 — emotional flags
        round_emotional = EMOTIONAL_FLAGS.get(args.round, {})
        t6 = compute_t6(
            home_flags=round_emotional.get(home, []),
            away_flags=round_emotional.get(away, []),
        )

        # T7 — weather (game-day only; leave WEATHER entry empty mid-week)
        round_weather = WEATHER.get(args.round, {})
        wx_data = round_weather.get((home, away), {})
        kickoff_str = date + ' 15:00'   # fallback if no kickoff time in weather dict
        if wx_data.get('kickoff'):
            kickoff_str = date + ' ' + wx_data['kickoff']
        # MCG wind swirl: apply 1.1x multiplier on wind-dominant conditions
        wind_venue_factor = 1.1 if venue == 'MCG' else 1.0
        t7 = compute_t7(weather=wx_data, kickoff=kickoff_str,
                        wind_venue_factor=wind_venue_factor)

        final_margin = (t1_margin
                        + t2['t2_handicap'] + t3['t3_handicap']
                        + t4['t4_handicap'] + t5['t5_handicap']
                        + t6['t6_handicap'])
        final_total  = (t1_total
                        + t2['t2_totals']   + t3['t3_totals']
                        + t4['t4_totals']   + t5['t5_totals']
                        + t6['t6_totals']   + t7['t7_totals'])

        home_prob, away_prob = margin_to_h2h(final_margin)

        # Totals — fair line is our model total; price over/under at that line
        fair_line = round(final_total * 2) / 2   # round to nearest 0.5
        p_over, p_under, odds_over, odds_under = total_to_ou_odds(final_total, fair_line)

        results.append({
            'home': home, 'away': away, 'venue': venue,
            'home_elo': round(elo.get(home, 1500), 1),
            'away_elo': round(elo.get(away, 1500), 1),
            't1_margin': round(t1_margin, 1),
            't1_total':  round(t1_total,  1),
            'ml_margin_raw': round(ml_margin_raw, 1) if ml_margin_raw is not None else None,
            'ml_total_raw':  round(ml_total_raw, 1)  if ml_total_raw  is not None else None,
            'ml_total_cal':  round(ml_total_cal, 1)  if ml_total_cal  is not None else None,
            'ml_h2h_raw':    round(ml_h2h_prob, 4)   if ml_h2h_prob   is not None else None,
            # ML adjusted: ML (bias-corrected) + T2 + T5 + T6 + T7
            'ml_margin': round(ml_margin_raw + t2['t2_handicap'] + t5['t5_handicap'] + t6['t6_handicap'], 1) if ml_margin_raw is not None else None,
            'ml_total':  round(ml_total_cal  + t2['t2_totals']   + t5['t5_totals']   + t6['t6_totals']   + t7['t7_totals'],  1) if ml_total_cal  is not None else None,
            'ml_h2h':    round(ml_h2h_prob, 4)   if ml_h2h_prob   is not None else None,
            't2_hcp':    t2['t2_handicap'],
            't2_tot':    t2['t2_totals'],
            't3_hcp':    t3['t3_handicap'],
            't3_tot':    t3['t3_totals'],
            't3_signals':t3['signals'],
            't4_hcp':    t4['t4_handicap'],
            't4_tot':    t4['t4_totals'],
            't4_signals':t4['signals'],
            't5_hcp':    t5['t5_handicap'],
            't5_tot':    t5['t5_totals'],
            't5_home':   t5['home_impact'],
            't5_away':   t5['away_impact'],
            't6_hcp':    t6['t6_handicap'],
            't6_tot':    t6['t6_totals'],
            't6_signals':t6['signals'],
            't7_tot':    t7['t7_totals'],
            't7_cond':   t7['condition_type'],
            't7_dew':    t7['dew_risk'],
            'final_margin': round(final_margin, 1),
            'final_total':  round(final_total,  1),
            'home_prob':    home_prob,
            'away_prob':    away_prob,
            'home_odds':    prob_to_odds(home_prob),
            'away_odds':    prob_to_odds(away_prob),
            'fair_line':    fair_line,
            'p_over':       p_over,
            'p_under':      p_under,
            'odds_over':    odds_over,
            'odds_under':   odds_under,
            'families':     t2['families'],
        })

    # ── Print ──────────────────────────────────────────────────────────────────
    print()
    print('=' * 152)
    print(f'  AFL R{args.round} {args.season} — Rules Engine (T1–T7)  |  Fair Prices')
    print(f'  T1: ELO margin + team scoring rates  |  T2–T7: style / situational / venue / injury / emotional / weather')
    print('=' * 152)
    print()
    print(f"  {'Matchup':<46} {'ELO':>8}  {'T1 Mrg':>7} {'T2':>6} {'T3':>6} {'T4':>6} {'T5':>6} {'T6':>6} {'T7':>6} {'FinalMrg':>9} {'FinalTot':>9}  {'HomeOdds':>9} {'AwayOdds':>9}")
    print('  ' + '─' * 138)

    for r in results:
        home_s = r['home'].split()[-1]
        away_s = r['away'].split()[-1]
        matchup = f"{home_s} vs {away_s}"
        elo_diff = r['home_elo'] - r['away_elo']
        t5_flag = ' ⚑' if r['t5_hcp'] != 0.0 else ''
        t6_flag = ' ◆' if r['t6_hcp'] != 0.0 else ''
        wx_flag = f" [{r['t7_cond']}]" if r['t7_cond'] != 'clear' else ''
        print(f"  {matchup:<46} {elo_diff:>+8.0f}  "
              f"{r['t1_margin']:>+7.1f} {r['t2_hcp']:>+6.1f} {r['t3_hcp']:>+6.1f} "
              f"{r['t4_hcp']:>+6.1f} {r['t5_hcp']:>+6.1f} "
              f"{r['t6_hcp']:>+6.1f} {r['t7_tot']:>+6.1f} "
              f"{r['final_margin']:>+9.1f} {r['final_total']:>9.1f}  "
              f"{r['home_odds']:>9.2f} {r['away_odds']:>9.2f}{t5_flag}{t6_flag}{wx_flag}")

    SEP = '  ' + '─' * 138

    # ── T2 family breakdown ───────────────────────────────────────────────────
    print()
    print(SEP)
    print(f"  {'Matchup':<46} {'A:Cont':>8} {'B:Terr':>8} {'C:Fwd':>8} {'D:Def':>8} {'E:Press':>8}  {'T2 Hcp':>7}  {'T2 Tot':>7}")
    print(SEP)
    for r in results:
        home_s = r['home'].split()[-1]; away_s = r['away'].split()[-1]
        fams = r['families']
        parts = [f"{fams.get(k, {}).get('pts', 0):>+8.2f}" for k in 'ABCDE']
        print(f"  {home_s+' vs '+away_s:<46} {'  '.join(parts)}  {r['t2_hcp']:>+7.2f}  {r['t2_tot']:>+7.2f}")

    # ── T3 signal breakdown ───────────────────────────────────────────────────
    print()
    print(SEP)
    print(f"  {'Matchup':<46} {'3A Rest':>8} {'3B Trvl':>8} {'3C Comp':>8} {'3D Form':>8} {'3E Occ':>8}  {'T3 Hcp':>7}  {'T3 Tot':>7}")
    print(SEP)
    SIG_ORDER_T3 = ['3A_rest', '3B_travel', '3C_compound', '3D_momentum', '3E_occasion']
    for r in results:
        home_s = r['home'].split()[-1]; away_s = r['away'].split()[-1]
        sig_map = {s['signal']: s['pts'] for s in r['t3_signals']}
        parts = [f"{sig_map.get(k, 0.0):>+8.2f}" for k in SIG_ORDER_T3]
        notes = [s['note'] for s in r['t3_signals'] if s.get('applied') and s.get('note')]
        note_str = '  ' + ' | '.join(notes) if notes else ''
        print(f"  {home_s+' vs '+away_s:<46} {'  '.join(parts)}  {r['t3_hcp']:>+7.2f}  {r['t3_tot']:>+7.2f}{note_str}")

    # ── T4 venue breakdown ────────────────────────────────────────────────────
    print()
    print(SEP)
    print(f"  {'Matchup':<46} {'4A Fortress':>12} {'4B VenScore':>12}  {'T4 Hcp':>7}  {'T4 Tot':>7}  Notes")
    print(SEP)
    for r in results:
        home_s = r['home'].split()[-1]; away_s = r['away'].split()[-1]
        sig_map = {s['signal']: s for s in r['t4_signals']}
        s4a = sig_map.get('4A_fortress', {}); s4b = sig_map.get('4B_venue_scoring', {})
        notes = [s4a.get('note', '')] if s4a.get('applied') else []
        note_str = '  ' + ' | '.join(n for n in notes if n) if notes else ''
        print(f"  {home_s+' vs '+away_s:<46} {s4a.get('pts', 0.0):>+12.2f} {s4b.get('pts', 0.0):>+12.2f}  "
              f"{r['t4_hcp']:>+7.2f}  {r['t4_tot']:>+7.2f}{note_str}")

    # ── T5 injury breakdown ───────────────────────────────────────────────────
    print()
    print(SEP)
    print(f"  {'Matchup':<46} {'Home Outs':<28} {'Away Outs':<28}  {'T5 Hcp':>7}  {'T5 Tot':>7}")
    print(SEP)
    for r in results:
        home_s = r['home'].split()[-1]; away_s = r['away'].split()[-1]
        hi = r['t5_home']; ai = r['t5_away']
        h_str = ', '.join(f"{p['player']} ({p['quality'][0].upper()} {p['position'][:4]})"
                          for p in hi['players']) if hi['players'] else 'none'
        a_str = ', '.join(f"{p['player']} ({p['quality'][0].upper()} {p['position'][:4]})"
                          for p in ai['players']) if ai['players'] else 'none'
        compound = ' ⚡' if hi['compound'] or ai['compound'] else ''
        print(f"  {home_s+' vs '+away_s:<46} {h_str:<28} {a_str:<28}  "
              f"{r['t5_hcp']:>+7.2f}  {r['t5_tot']:>+7.2f}{compound}")

    print()
    print('  ⚑ = injury adjustment active.  ⚡ = compound penalty (2+ key players out).')
    print('  Update INJURIES dict in prepare_afl_round.py before each round.')
    print('=' * 138)

    # ── Totals table ──────────────────────────────────────────────────────────
    print()
    print('=' * 90)
    print(f'  AFL R{args.round} {args.season} — TOTALS (Over/Under)  |  std={TOTAL_STD} pts')
    print('=' * 90)
    print()
    print(f"  {'Matchup':<46} {'Fair Line':>10}  {'P(Over)':>8} {'P(Under)':>9}  {'Odds Over':>10} {'Odds Under':>11}")
    print('  ' + '─' * 88)
    for r in results:
        home_s = r['home'].split()[-1]
        away_s = r['away'].split()[-1]
        matchup = f"{home_s} vs {away_s}"
        print(f"  {matchup:<46} {r['fair_line']:>10.1f}  "
              f"{r['p_over']:>8.3f} {r['p_under']:>9.3f}  "
              f"{r['odds_over']:>10.2f} {r['odds_under']:>11.2f}")
    print()
    print(f'  Fair line = model total (T1+T2+T3) rounded to nearest 0.5.')
    print(f'  At fair line, P(Over) ≈ P(Under) ≈ 0.500 — both sides ~2.00.')
    print(f'  Compare market line vs fair line to find value. Each 5pt gap ≈ 59% edge.')
    print('=' * 90)

    # ── PRICING SHEET ─────────────────────────────────────────────────────────
    print()
    print('=' * 110)
    print(f'  AFL R{args.round} {args.season} — PRICING SHEET  (T1+T2+T3+T4 fair prices)')
    print('=' * 110)
    print()
    print(f"  {'Matchup':<38}  {'H2H Home':>9} {'H2H Away':>9}  {'Hdcp Line':<18}  {'Total':>7}  {'O Odds':>8} {'U Odds':>8}")
    print('  ' + '─' * 108)

    for r in results:
        home_s = r['home'].split()[-1]
        away_s = r['away'].split()[-1]
        matchup = f"{home_s} vs {away_s}"

        m = r['final_margin']
        fav = home_s if m > 0 else away_s
        hdcp = f"{fav} -{abs(m):.1f}"

        print(f"  {matchup:<38}  {r['home_odds']:>9.2f} {r['away_odds']:>9.2f}  {hdcp:<18}  {r['fair_line']:>7.1f}  {r['odds_over']:>8.2f} {r['odds_under']:>8.2f}")

    print()
    print(f'  Hdcp = fair handicap line.  H2H = fair win odds.  Total = fair O/U line.')
    print(f'  O/U odds at model line are ~2.00 by definition — compare vs market line for EV.')
    print('=' * 110)

    # ── ML SHADOW MODE ────────────────────────────────────────────────────────
    if ml_available:
        DIVERG_MARGIN = 6.0   # flag if ML vs rules margin gap >= this
        DIVERG_H2H    = 0.08  # flag if ML vs rules H2H probability gap >= this
        DIVERG_TOTAL  = 8.0   # flag if ML vs rules total gap >= this

        print()
        print('=' * 120)
        print(f'  AFL R{args.round} {args.season} — ML Shadow Mode  (XGBoost trained 2009–2023)')
        print(f'  Rules = T1–T7 full stack above.  ML = XGBoost (bias-corrected +{ml_bias["bias"]:.1f} pts, n={ml_bias["n"]}) + T2 + T5 + T6 + T7.')
        print(f'  Divergence flags: margin ≥{DIVERG_MARGIN:.0f}pt  |  H2H ≥{DIVERG_H2H:.0%}  |  total ≥{DIVERG_TOTAL:.0f}pt')
        print('=' * 120)
        print()
        print(f"  {'Matchup':<46} {'Rules Mrg':>10} {'ML Mrg':>8} {'MrgΔ':>7}  "
              f"{'Rules Tot':>10} {'ML Tot':>8} {'TotΔ':>7}  "
              f"{'Rules H%':>9} {'ML H%':>8} {'H%Δ':>7}")
        print('  ' + '─' * 118)

        divergences = []
        for r in results:
            home_s   = r['home'].split()[-1]
            away_s   = r['away'].split()[-1]
            matchup  = f"{home_s} vs {away_s}"
            rules_mrg = r['final_margin']
            ml_mrg    = r['ml_margin']
            mrg_delta = ml_mrg - rules_mrg

            rules_tot = r['final_total']
            ml_tot    = r['ml_total']
            tot_delta = ml_tot - rules_tot

            rules_h   = r['home_prob']
            ml_h      = r['ml_h2h']
            h_delta   = ml_h - rules_h

            flags = []
            if abs(mrg_delta) >= DIVERG_MARGIN: flags.append('margin')
            if abs(h_delta)   >= DIVERG_H2H:    flags.append('H2H')
            if abs(tot_delta) >= DIVERG_TOTAL:   flags.append('total')
            flag_str = ' ◆' + '+'.join(flags) if flags else ''
            if flags:
                divergences.append((matchup, mrg_delta, tot_delta, h_delta, flags))

            print(f"  {matchup:<46} {rules_mrg:>+10.1f} {ml_mrg:>+8.1f} {mrg_delta:>+7.1f}  "
                  f"{rules_tot:>10.1f} {ml_tot:>8.1f} {tot_delta:>+7.1f}  "
                  f"{rules_h:>9.1%} {ml_h:>8.1%} {h_delta:>+7.1%}{flag_str}")

        if divergences:
            print()
            print(f'  DIVERGENCE SUMMARY  (rules vs ML gap beyond thresholds)')
            print('  ' + '─' * 80)
            for matchup, md, td, hd, flags in divergences:
                parts = []
                for f in flags:
                    val = abs(md) if f == 'margin' else abs(td) if f == 'total' else abs(hd)
                    parts.append(f'{f}: {val:.1f}')
                note = '  '.join(parts)
                direction = 'ML more bullish home' if md > 0 else 'ML more bearish home'
                print(f'  {matchup:<46}  {direction}  |  {note}')
        print()
        print('  ◆ = divergence flag.  ML is independent cross-check only — not used in pricing.')
        print('=' * 120)


if __name__ == '__main__':
    main()
