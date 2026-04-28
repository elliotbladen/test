#!/usr/bin/env python3
"""
ml/run_r9_shadow.py

Shadow-mode ML inference for a single round.

Loads the trained XGBoost models, builds R9 features from the DB + historical
data, runs predictions, then layers T5 (injuries) and T7 (emotional) adjustments
on top.

Prints a side-by-side comparison:
    Rules model (T1–T8) vs ML baseline vs ML + T5/T7

USAGE
-----
    python ml/run_r9_shadow.py --season 2026 --round 9
    python ml/run_r9_shadow.py --season 2026 --round 9 --output results/r9_ml_shadow.txt
"""

import argparse
import csv
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np

ROOT       = Path(__file__).resolve().parent.parent
DB_PATH    = ROOT / 'data' / 'model.db'
MODELS_DIR = ROOT / 'ml' / 'models'
REF_LOG    = ROOT / 'ml' / 'results' / 'game_log_referee.csv'

# ── Rest classification (matches game_log.py) ────────────────────────────────
SHORT_MAX  = 6
NORMAL_MAX = 9
LONG_MAX   = 13

def rest_class(days):
    if days is None: return None
    if days <= SHORT_MAX:  return 'short'
    if days <= NORMAL_MAX: return 'normal'
    if days <= LONG_MAX:   return 'long'
    return 'bye'


# ── Venue name mapping: DB name → features.csv name ─────────────────────────
VENUE_NAME_MAP = {
    'Leichhardt Oval':                    'Leichhardt Oval',
    'Queensland Country Bank Stadium':    'QCB Stadium',
    'Suncorp Stadium':                    'Suncorp Stadium',
    'Allianz Stadium':                    'Allianz Stadium',
    'Sky Stadium':                        'Sky Stadium',
    'AAMI Park':                          'AAMI Park',
    'McDonald Jones Stadium':             'McDonald Jones Stadium',
    '4 Pines Park':                       '4 Pines Park (Brookvale Oval)',
}

# Pre-computed venue stats from full training set (2009-2025, excl. Sky/NQ with small n)
VENUE_STATS = {
    'Leichhardt Oval':                 {'avg_total': 52.4, 'hw_pct': 0.500},
    'QCB Stadium':                     {'avg_total': 48.1, 'hw_pct': 0.576},
    'Suncorp Stadium':                 {'avg_total': 47.4, 'hw_pct': 0.497},
    'Allianz Stadium':                 {'avg_total': 47.2, 'hw_pct': 0.575},
    'Sky Stadium':                     {'avg_total': 32.0, 'hw_pct': 1.000},  # tiny n=1
    'AAMI Park':                       {'avg_total': 45.9, 'hw_pct': 0.810},
    'McDonald Jones Stadium':          {'avg_total': 43.5, 'hw_pct': 0.452},
    '4 Pines Park (Brookvale Oval)':   {'avg_total': 48.1, 'hw_pct': 0.600},
}


# ── Build referee lookup from historical game log ────────────────────────────
def build_ref_lookup(ref_log_path: Path) -> dict:
    """
    Build rolling pre-game referee stats from game_log_referee.csv.
    Returns dict: ref_name → {ref_total_diff, ref_penalty_rate, ref_home_bias, ref_home_win_pct}
    Uses the most recent 50 games for each referee as the snapshot.
    """
    MIN_SAMPLE = 10
    ref_rows = defaultdict(list)

    with open(ref_log_path) as f:
        for row in csv.DictReader(f):
            ref = (row.get('referee') or '').strip()
            if not ref:
                continue
            try:
                ref_rows[ref].append({
                    'ref_total_diff':  float(row['ref_total_diff'])  if row.get('ref_total_diff')  not in ('', 'None') else None,
                    'ref_penalty_rate':float(row['ref_penalty_rate']) if row.get('ref_penalty_rate') not in ('', 'None') else None,
                    'ref_home_bias':   float(row['ref_home_bias'])    if row.get('ref_home_bias')    not in ('', 'None') else None,
                    'ref_home_win_pct':float(row['ref_home_win_pct']) if row.get('ref_home_win_pct') not in ('', 'None') else None,
                })
            except (ValueError, KeyError):
                continue

    lookup = {}
    for ref, games in ref_rows.items():
        valid = [g for g in games if g['ref_total_diff'] is not None]
        if len(valid) < MIN_SAMPLE:
            lookup[ref] = {k: None for k in ['ref_total_diff','ref_penalty_rate','ref_home_bias','ref_home_win_pct']}
        else:
            # Use last 50 valid games as representative snapshot
            recent = valid[-50:]
            lookup[ref] = {
                'ref_total_diff':   round(sum(g['ref_total_diff']   for g in recent) / len(recent), 3),
                'ref_penalty_rate': round(sum(g['ref_penalty_rate'] for g in recent if g['ref_penalty_rate']) / len(recent), 3),
                'ref_home_bias':    round(sum(g['ref_home_bias']    for g in recent if g['ref_home_bias'])    / len(recent), 3),
                'ref_home_win_pct': round(sum(g['ref_home_win_pct'] for g in recent if g['ref_home_win_pct']) / len(recent), 3),
            }
    return lookup


# ── Team form from results DB ─────────────────────────────────────────────────
def build_team_form(conn, season: int, round_before: int) -> dict:
    """
    For each team, compute form stats entering this round.
    Returns dict: team_id → {prev_margin, off_big_win, off_big_loss,
                              win_streak, loss_streak}
    """
    # Get all results up to the round before, ordered by date
    rows = conn.execute("""
        SELECT r.match_id, m.match_date, m.home_team_id, m.away_team_id,
               r.margin, r.home_score, r.away_score
        FROM results r
        JOIN matches m ON m.match_id = r.match_id
        WHERE m.season = ? AND m.round_number < ?
        ORDER BY m.match_date, r.match_id
    """, (season, round_before)).fetchall()

    # Track per-team history (ordered by date)
    team_games = defaultdict(list)  # team_id → [(date, margin_from_perspective)]
    for r in rows:
        htid = r['home_team_id']
        atid = r['away_team_id']
        home_margin = r['margin']       # home - away
        away_margin = -home_margin
        team_games[htid].append({'date': r['match_date'], 'margin': home_margin})
        team_games[atid].append({'date': r['match_date'], 'margin': away_margin})

    form = {}
    for tid, games in team_games.items():
        if not games:
            form[tid] = {'prev_margin': None, 'off_big_win': 0, 'off_big_loss': 0,
                         'win_streak': 0, 'loss_streak': 0}
            continue

        last = games[-1]
        pm = last['margin']
        form[tid] = {
            'prev_margin':  pm,
            'off_big_win':  1 if pm >= 20 else 0,
            'off_big_loss': 1 if pm <= -20 else 0,
            'win_streak':   0,
            'loss_streak':  0,
        }
        # Compute streaks from most recent backward
        ws = ls = 0
        for g in reversed(games):
            if g['margin'] > 0:
                if ls == 0: ws += 1
                else: break
            elif g['margin'] < 0:
                if ws == 0: ls += 1
                else: break
            else:  # draw
                break
        form[tid]['win_streak']  = ws
        form[tid]['loss_streak'] = ls

    return form


# ── Convert to float array matching feature_columns.json order ───────────────
FEATURE_COLS = [
    'elo_diff', 'home_elo_win_prob', 'elo_predicted_margin',
    'home_rest_days', 'away_rest_days', 'rest_diff',
    'home_rest_class', 'away_rest_class',           # → NaN (string, XGB handles)
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


def to_float(v):
    if v is None: return float('nan')
    try:    return float(v)
    except: return float('nan')


def build_feature_row(feat_dict: dict) -> np.ndarray:
    row = [to_float(feat_dict.get(col)) for col in FEATURE_COLS]
    return np.array([row], dtype=np.float32)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--round',  type=int, default=9, dest='round_number')
    parser.add_argument('--output', default=None)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ── Load models ───────────────────────────────────────────────────────────
    margin_model = joblib.load(MODELS_DIR / 'margin_model_v20260419.joblib')
    total_model  = joblib.load(MODELS_DIR / 'total_model_v20260419.joblib')
    h2h_model    = joblib.load(MODELS_DIR / 'h2h_model_v20260419.joblib')

    # ── Build ref lookup ──────────────────────────────────────────────────────
    ref_lookup = build_ref_lookup(REF_LOG)

    # ── Team form ─────────────────────────────────────────────────────────────
    team_form = build_team_form(conn, args.season, args.round_number)

    # ── Pull R9 matches with all needed data ──────────────────────────────────
    matches = conn.execute("""
        SELECT m.match_id, m.home_team_id, m.away_team_id,
               m.match_date, m.kickoff_datetime, m.venue_id,
               ht.team_name AS home_name, at.team_name AS away_name,
               v.venue_name,
               hts.elo_rating AS home_elo, ats.elo_rating AS away_elo,
               tp.t3_home_rest_days  AS home_rest_days,
               tp.t3_away_rest_days  AS away_rest_days,
               tp.t3_home_travel_km  AS home_travel_km,
               tp.t3_away_travel_km  AS away_travel_km,
               tp.t5_handicap_delta  AS t5_hcap,
               tp.totals_T5          AS t5_tot,
               tp.totals_T7          AS t7_tot,
               tp.final_margin       AS rules_margin,
               tp.final_total        AS rules_total,
               tp.home_win_probability AS rules_h2h_prob,
               tp.t1_margin, tp.t2a_home_delta, tp.t2b_home_delta, tp.t2c_home_delta,
               tp.totals_T2,
               tp.t3_home_delta, tp.t3_away_delta,
               tp.t4_handicap_delta, tp.t6_handicap_delta,
               tp.totals_T6, tp.t7_condition_type, tp.t7_dew_risk,
               wra.referee_id,
               ref.referee_name,
               wc.precipitation_mm AS rain_mm, wc.wind_kmh AS wind_kmh,
               wc.temp_c AS temp_c
        FROM matches m
        JOIN teams ht  ON ht.team_id = m.home_team_id
        JOIN teams at  ON at.team_id = m.away_team_id
        JOIN venues v  ON v.venue_id = m.venue_id
        JOIN team_stats hts ON hts.team_id = m.home_team_id
                           AND hts.season = m.season
                           AND hts.as_of_date = '2026-04-22'
        JOIN team_stats ats ON ats.team_id = m.away_team_id
                           AND ats.season = m.season
                           AND ats.as_of_date = '2026-04-22'
        JOIN tier2_performance tp ON tp.match_id = m.match_id
        LEFT JOIN weekly_ref_assignments wra ON wra.match_id = m.match_id
        LEFT JOIN referees ref ON ref.referee_id = wra.referee_id
        LEFT JOIN weather_conditions wc ON wc.match_id = m.match_id
        WHERE m.season = ? AND m.round_number = ?
        ORDER BY m.match_date, m.match_id
    """, (args.season, args.round_number)).fetchall()

    if not matches:
        print(f"No matches found for S{args.season} R{args.round_number}", file=sys.stderr)
        sys.exit(1)

    # ── T7 emotional handicap delta (recomputed from emotional_flags) ─────────
    MARGIN_PTS = {
        'milestone': 0.8, 'new_coach': 1.2, 'star_return': 1.5,
        'shame_blowout': 1.0, 'origin_boost': 0.6, 'farewell': 0.5,
        'personal_tragedy': 1.5, 'rivalry_derby': 0.3, 'must_win': 0.8,
    }
    STRENGTH_MULT = {'minor': 0.5, 'normal': 1.0, 'major': 1.5}
    MAX_TEAM = 2.5

    def get_t7_hcap(mid, home_tid, away_tid):
        flags = conn.execute(
            "SELECT team_id, flag_type, flag_strength FROM emotional_flags WHERE match_id=?",
            (mid,)
        ).fetchall()
        home_raw = sum(MARGIN_PTS.get(f['flag_type'], 0) * STRENGTH_MULT.get(f['flag_strength'], 1.0)
                       for f in flags if f['team_id'] == home_tid)
        away_raw = sum(MARGIN_PTS.get(f['flag_type'], 0) * STRENGTH_MULT.get(f['flag_strength'], 1.0)
                       for f in flags if f['team_id'] == away_tid)
        return round(min(MAX_TEAM, home_raw) - min(MAX_TEAM, away_raw), 3)

    # ── Weather T8 delta ──────────────────────────────────────────────────────
    def get_t8_wx(m):
        # Derive from final_total - (T1+T2+T3+T4+T5+T6+T7)
        tp = m
        t1 = tp['totals_T1'] if hasattr(tp, '__getitem__') else 0  # not available here
        # Use weather_conditions table directly via wc join above
        return None  # will use rules_total - ML as delta reference instead

    # ── Process each match ────────────────────────────────────────────────────
    results = []

    for m in matches:
        home_elo = float(m['home_elo'] or 1500)
        away_elo = float(m['away_elo'] or 1500)
        elo_diff = home_elo - away_elo

        # ELO features
        home_elo_win_prob  = 1.0 / (1.0 + 10 ** (-elo_diff / 400.0))
        elo_pred_margin    = elo_diff * 0.04 + 3.5

        # Rest/form
        hrd = m['home_rest_days']
        ard = m['away_rest_days']
        hrc = rest_class(hrd)
        arc = rest_class(ard)
        hform = team_form.get(m['home_team_id'], {})
        aform = team_form.get(m['away_team_id'], {})

        # Venue
        vname_db  = m['venue_name'] or ''
        vname_csv = VENUE_NAME_MAP.get(vname_db, vname_db)
        vstats    = VENUE_STATS.get(vname_csv, {})

        # Travel
        htk = m['home_travel_km'] or 0.0
        atk = m['away_travel_km'] or 0.0
        travel_diff = atk - htk  # positive = away team travelled more

        # Referee
        ref_name  = m['referee_name'] or ''
        ref_stats = ref_lookup.get(ref_name, {k: None for k in
                      ['ref_total_diff','ref_penalty_rate','ref_home_bias','ref_home_win_pct']})

        # Weather
        rain_mm       = float(m['rain_mm']  or 0.0)
        wind_kmh      = float(m['wind_kmh'] or 0.0)
        wind_gusts    = None   # not stored in DB
        temp_c        = float(m['temp_c']   or 20.0)

        feat = {
            'elo_diff':             elo_diff,
            'home_elo_win_prob':    home_elo_win_prob,
            'elo_predicted_margin': elo_pred_margin,
            'home_rest_days':       hrd,
            'away_rest_days':       ard,
            'rest_diff':            (hrd - ard) if (hrd and ard) else None,
            'home_rest_class':      None,   # string → NaN (matches training behaviour)
            'away_rest_class':      None,
            'home_had_bye':         1 if hrc == 'bye' else 0,
            'away_had_bye':         1 if arc == 'bye' else 0,
            'home_prev_margin':     hform.get('prev_margin'),
            'away_prev_margin':     aform.get('prev_margin'),
            'home_off_big_win':     hform.get('off_big_win', 0),
            'home_off_big_loss':    hform.get('off_big_loss', 0),
            'away_off_big_win':     aform.get('off_big_win', 0),
            'away_off_big_loss':    aform.get('off_big_loss', 0),
            'home_win_streak':      hform.get('win_streak', 0),
            'away_win_streak':      aform.get('win_streak', 0),
            'home_loss_streak':     hform.get('loss_streak', 0),
            'away_loss_streak':     aform.get('loss_streak', 0),
            'home_travel_km':       htk,
            'away_travel_km':       atk,
            'travel_diff':          travel_diff,
            'is_neutral_venue':     0,
            'venue_avg_total':      vstats.get('avg_total'),
            'venue_home_win_pct':   vstats.get('hw_pct'),
            'ref_total_diff':       ref_stats.get('ref_total_diff'),
            'ref_penalty_rate':     ref_stats.get('ref_penalty_rate'),
            'ref_home_bias':        ref_stats.get('ref_home_bias'),
            'ref_home_win_pct':     ref_stats.get('ref_home_win_pct'),
            'rain_mm':              rain_mm,
            'wind_kmh':             wind_kmh,
            'wind_gusts_kmh':       wind_gusts,
            'temp_c':               temp_c,
        }

        X = build_feature_row(feat)

        ml_margin   = float(margin_model.predict(X)[0])
        ml_total    = float(total_model.predict(X)[0])
        ml_h2h_prob = float(h2h_model.predict_proba(X)[0][1])

        # Adjust ML with T2 + T5 + T7 situational tiers
        t2_hcap   = (float(m['t2a_home_delta'] or 0.0)
                     + float(m['t2b_home_delta'] or 0.0)
                     + float(m['t2c_home_delta'] or 0.0))
        t2_tot    = float(m['totals_T2'] or 0.0)
        t5_hcap   = float(m['t5_hcap']  or 0.0)
        t5_tot    = float(m['t5_tot']   or 0.0)
        t7_hcap   = get_t7_hcap(m['match_id'], m['home_team_id'], m['away_team_id'])
        t7_tot    = float(m['t7_tot']   or 0.0)

        ml_adj_margin = ml_margin + t2_hcap + t5_hcap + t7_hcap
        ml_adj_total  = ml_total  + t2_tot  + t5_tot  + t7_tot

        # Convert adjusted margin → win probability (normal distribution approx)
        # std dev ~13 pts is a reasonable NRL approximation
        STD = 13.0
        ml_adj_h2h_prob = 0.5 * (1 + math.erf(ml_adj_margin / (STD * math.sqrt(2))))

        # Rules model T7 handicap (for fair comparison)
        rules_t7_hcap = t7_hcap

        results.append({
            'match_id':        m['match_id'],
            'home_name':       m['home_name'],
            'away_name':       m['away_name'],
            'venue':           vname_db,
            'ref_name':        ref_name,
            # Feature completeness (non-NaN count)
            'feat_complete':   round(sum(1 for v in feat.values() if v is not None) / len(feat), 2),
            # ML raw (T1-T4 equivalent + T6 + T8 via historical patterns)
            'ml_margin':       round(ml_margin, 1),
            'ml_total':        round(ml_total, 1),
            'ml_h2h_prob':     round(ml_h2h_prob, 3),
            # ML adjusted (+ T5 injuries + T7 emotional)
            'ml_adj_margin':   round(ml_adj_margin, 1),
            'ml_adj_total':    round(ml_adj_total, 1),
            'ml_adj_h2h_prob': round(ml_adj_h2h_prob, 3),
            # Rules-based 8-tier model
            'rules_margin':    round(float(m['rules_margin'] or 0), 1),
            'rules_total':     round(float(m['rules_total']  or 0), 1),
            'rules_h2h_prob':  round(float(m['rules_h2h_prob'] or 0.5), 3),
            # Adjustments applied
            't2_hcap':         t2_hcap,
            't2_tot':          t2_tot,
            't5_hcap':         t5_hcap,
            't7_hcap':         t7_hcap,
            't5_tot':          t5_tot,
            't7_tot':          t7_tot,
            # Feature values for debug
            '_elo_diff':       round(elo_diff, 1),
            '_rest_h':         hrd,
            '_rest_a':         ard,
            '_had_bye_h':      feat['home_had_bye'],
            '_had_bye_a':      feat['away_had_bye'],
            '_prev_mrg_h':     hform.get('prev_margin'),
            '_prev_mrg_a':     aform.get('prev_margin'),
            '_win_streak_h':   hform.get('win_streak', 0),
            '_win_streak_a':   aform.get('win_streak', 0),
            '_loss_streak_h':  hform.get('loss_streak', 0),
            '_loss_streak_a':  aform.get('loss_streak', 0),
            '_venue':          vname_csv,
            '_venue_avg_tot':  vstats.get('avg_total'),
            '_ref_name':       ref_name,
            '_ref_td':         ref_stats.get('ref_total_diff'),
        })

    # ── Print tables ──────────────────────────────────────────────────────────
    SEP = '─' * 145
    W   = 145

    lines = []
    def p(s=''): lines.append(s); print(s)

    p()
    p('=' * W)
    p(f'  NRL 2026 — Round 9  |  ML Shadow Mode vs Rules Model')
    p(f'  Models: XGBoost trained on 2009–2023  |  T2+T5+T7 layered on top')
    p('=' * W)

    # ── MARGIN COMPARISON ─────────────────────────────────────────────────────
    p()
    p('  MARGIN  (home perspective, +ve = home wins)')
    p(f"  {'Game':<44} {'ELO Δ':>7} {'ML Raw':>8} {'T2Δ':>6} {'T5Δ':>6} {'T7Δ':>6} {'ML+T2+T5+T7':>12} {'Rules':>8} {'Diff':>7}")
    p(f'  {SEP[:105]}')
    for r in results:
        game  = f"{r['home_name'].split()[-1]} vs {r['away_name'].split()[-1]}"[:44]
        diff  = round(r['ml_adj_margin'] - r['rules_margin'], 1)
        arrow = '▲' if diff > 0 else ('▼' if diff < 0 else ' ')
        p(f"  {game:<44} {r['_elo_diff']:>+7.1f} {r['ml_margin']:>+8.1f} "
          f"{r['t2_hcap']:>+6.1f} {r['t5_hcap']:>+6.1f} {r['t7_hcap']:>+6.1f} "
          f"{r['ml_adj_margin']:>+12.1f} {r['rules_margin']:>+8.1f} "
          f"{diff:>+6.1f}{arrow}")

    # ── TOTAL COMPARISON ──────────────────────────────────────────────────────
    p()
    p('  TOTAL  (expected combined score)')
    p(f"  {'Game':<44} {'ML Raw':>8} {'T5Δ':>6} {'T7Δ':>6} {'ML+T5+T7':>10} {'Rules':>8} {'Diff':>7}")
    p(f'  {SEP[:95]}')
    for r in results:
        game = f"{r['home_name'].split()[-1]} vs {r['away_name'].split()[-1]}"[:44]
        diff = round(r['ml_adj_total'] - r['rules_total'], 1)
        arrow = '▲' if diff > 1 else ('▼' if diff < -1 else ' ')
        p(f"  {game:<44} {r['ml_total']:>8.1f} "
          f"{r['t5_tot']:>+6.1f} {r['t7_tot']:>+6.1f} "
          f"{r['ml_adj_total']:>10.1f} {r['rules_total']:>8.1f} "
          f"{diff:>+6.1f}{arrow}")

    # ── H2H WIN PROBABILITY ───────────────────────────────────────────────────
    p()
    p('  H2H WIN PROBABILITY  (home team %)')
    p(f"  {'Game':<44} {'ML Raw':>8} {'ML+T5+T7':>10} {'Rules':>8} {'Diff':>8}  {'ML H(fair)':>11}  {'Rules H(fair)':>14}")
    p(f'  {SEP[:112]}')
    for r in results:
        game  = f"{r['home_name'].split()[-1]} vs {r['away_name'].split()[-1]}"[:44]
        diff  = round((r['ml_adj_h2h_prob'] - r['rules_h2h_prob']) * 100, 1)
        ml_odds   = round(1/r['ml_adj_h2h_prob'], 3) if r['ml_adj_h2h_prob'] > 0 else 99
        rules_odds= round(1/r['rules_h2h_prob'], 3)  if r['rules_h2h_prob'] > 0 else 99
        arrow = '▲' if diff > 2 else ('▼' if diff < -2 else ' ')
        p(f"  {game:<44} {r['ml_h2h_prob']*100:>7.1f}% "
          f"{r['ml_adj_h2h_prob']*100:>9.1f}% "
          f"{r['rules_h2h_prob']*100:>7.1f}% "
          f"{diff:>+7.1f}%{arrow}  {ml_odds:>11.3f}  {rules_odds:>14.3f}")

    # ── FEATURE AUDIT ─────────────────────────────────────────────────────────
    p()
    p('  FEATURE AUDIT')
    p(f"  {'Game':<44} {'ELO Δ':>7} {'H Rest':>7} {'A Rest':>7} {'H Bye':>6} {'H Prev':>7} {'A Prev':>7} {'H Streak':>9} {'A Streak':>9} {'Venue Avg':>10} {'Ref TD':>8} {'Completeness':>13}")
    p(f'  {SEP[:142]}')
    for r in results:
        game = f"{r['home_name'].split()[-1]} vs {r['away_name'].split()[-1]}"[:44]
        hst  = f"+{r['_win_streak_h']}W" if r['_win_streak_h'] else f"-{r['_loss_streak_h']}L"
        ast  = f"+{r['_win_streak_a']}W" if r['_win_streak_a'] else f"-{r['_loss_streak_a']}L"
        va   = f"{r['_venue_avg_tot']:.1f}" if r['_venue_avg_tot'] else '—'
        rtd  = f"{r['_ref_td']:+.1f}" if r['_ref_td'] else '—'
        hprev= f"{r['_prev_mrg_h']:+.0f}" if r['_prev_mrg_h'] is not None else '—'
        aprev= f"{r['_prev_mrg_a']:+.0f}" if r['_prev_mrg_a'] is not None else '—'
        p(f"  {game:<44} {r['_elo_diff']:>+7.1f} {str(r['_rest_h'] or '—'):>7} {str(r['_rest_a'] or '—'):>7} "
          f"{'Y' if r['_had_bye_h'] else 'N':>6} {hprev:>7} {aprev:>7} "
          f"{hst:>9} {ast:>9} {va:>10} {rtd:>8} "
          f"{r['feat_complete']*100:>12.0f}%")

    # ── SUMMARY — WHERE THEY DIVERGE ─────────────────────────────────────────
    p()
    p('  DIVERGENCE SUMMARY  (ML+T5+T7 vs Rules, margin ≥ 3 pts OR H2H ≥ 5%)')
    p(f"  {'Game':<44} {'Margin Δ':>10} {'Total Δ':>9} {'H2H Δ':>8}  Notes")
    p(f'  {SEP[:100]}')
    any_diverge = False
    for r in results:
        m_diff   = round(r['ml_adj_margin'] - r['rules_margin'], 1)
        t_diff   = round(r['ml_adj_total']  - r['rules_total'],  1)
        h2h_diff = round((r['ml_adj_h2h_prob'] - r['rules_h2h_prob']) * 100, 1)
        if abs(m_diff) >= 3 or abs(h2h_diff) >= 5:
            game = f"{r['home_name'].split()[-1]} vs {r['away_name'].split()[-1]}"[:44]
            notes = []
            if abs(m_diff) >= 5:  notes.append(f'big margin gap')
            if abs(h2h_diff) >= 10: notes.append(f'big H2H gap')
            if abs(t_diff) >= 5:  notes.append(f'total gap')
            p(f"  {game:<44} {m_diff:>+10.1f} {t_diff:>+9.1f} {h2h_diff:>+7.1f}%  {', '.join(notes)}")
            any_diverge = True
    if not any_diverge:
        p('  — Models broadly agree on all games this round')

    p()
    p('=' * W)
    p(f'  Legend: ML Raw = XGBoost prediction (ELO + rest/form + venue + ref + weather from history)')
    p(f'          T2Δ = style matchup  |  T5Δ = injury  |  T7Δ = emotional  |  Rules = full 8-tier model')
    p('=' * W)

    # ── Save to file ──────────────────────────────────────────────────────────
    out_path = args.output or str(ROOT / 'results' / f'r{args.round_number}_ml_shadow_{args.season}.txt')
    with open(out_path, 'w') as f:
        f.write('\n'.join(lines))
    print(f'\nSaved → {out_path}')

    conn.close()


if __name__ == '__main__':
    main()
