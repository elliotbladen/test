#!/usr/bin/env python3
"""
ml/afl/backtest_2025.py

Backtest AFL ML models against 2025 market odds.
Uses pre-trained models from ml/afl/results/models/.
Reads features from ml/afl/results/features_afl.csv.
Reads OddsPortal xlsx for actual H2H / handicap / totals prices.

Outputs:
    ml/afl/results/backtest_2025.txt   — summary report
    ml/afl/results/backtest_2025.csv   — row-level detail

USAGE
-----
    python3 ml/afl/backtest_2025.py
    python3 ml/afl/backtest_2025.py --xlsx /path/to/afl.xlsx
"""

import argparse
import csv
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import openpyxl

ROOT        = Path(__file__).resolve().parent.parent.parent
FEATURES    = ROOT / 'ml' / 'afl' / 'results' / 'features_afl.csv'
MODELS_DIR  = ROOT / 'ml' / 'afl' / 'results' / 'models'
REPORT_TXT  = ROOT / 'ml' / 'afl' / 'results' / 'backtest_2025.txt'
REPORT_CSV  = ROOT / 'ml' / 'afl' / 'results' / 'backtest_2025.csv'
XLSX        = Path.home() / 'Downloads' / 'afl (2) (1).xlsx'

FEATURE_COLS = [
    'elo_diff', 'elo_win_prob',
    'home_rest_days', 'away_rest_days', 'rest_diff',
    'home_travel_km', 'away_travel_km', 'travel_diff_km',
    'home_win_pct', 'home_avg_margin', 'home_last_margin',
    'home_off_big_win', 'home_off_big_loss', 'home_win_streak', 'home_loss_streak',
    'away_win_pct', 'away_avg_margin', 'away_last_margin',
    'away_off_big_win', 'away_off_big_loss', 'away_win_streak', 'away_loss_streak',
    'form_win_pct_diff', 'form_margin_diff',
    'venue_games', 'venue_avg_total', 'venue_home_win_pct',
    'is_final',
]


def load_model(name: str):
    path = MODELS_DIR / f'{name}.pkl'
    with open(path, 'rb') as f:
        return pickle.load(f)


def load_odds_2025(xlsx_path: Path) -> dict:
    """Return dict keyed by (date_str, home_team_op, away_team_op) → odds row."""
    wb   = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws   = wb.active
    rows = list(ws.iter_rows(values_only=True))
    odds = {}
    for r in rows[2:]:
        if not r[0] or not hasattr(r[0], 'year'):
            continue
        if r[0].year != 2025:
            continue
        date_str = r[0].strftime('%Y-%m-%d')
        key = (date_str, r[2], r[3])   # date, home_op, away_op
        odds[key] = {
            'h2h_home_open':   r[15],
            'h2h_away_open':   r[19],
            'h2h_home_close':  r[18],
            'h2h_away_close':  r[22],
            'home_line_open':  r[23],
            'home_line_close': r[26],
            'total_open':      r[39],
            'total_close':     r[42],
            'home_score':      r[5],
            'away_score':      r[6],
        }
    print(f'Loaded {len(odds)} 2025 games from odds xlsx')
    return odds


TEAM_MAP_REVERSE = {
    'Adelaide Crows':               'Adelaide',
    'Brisbane Lions':               'Brisbane',
    'Carlton Blues':                'Carlton',
    'Collingwood Magpies':          'Collingwood',
    'Essendon Bombers':             'Essendon',
    'Fremantle Dockers':            'Fremantle',
    'Greater Western Sydney Giants':'GWS Giants',
    'Geelong Cats':                 'Geelong',
    'Gold Coast Suns':              'Gold Coast',
    'Hawthorn Hawks':               'Hawthorn',
    'Melbourne Demons':             'Melbourne',
    'North Melbourne Kangaroos':    'North Melbourne',
    'Port Adelaide Power':          'Port Adelaide',
    'Richmond Tigers':              'Richmond',
    'St Kilda Saints':              'St Kilda',
    'Sydney Swans':                 'Sydney',
    'West Coast Eagles':            'West Coast',
    'Western Bulldogs':             'Western Bulldogs',
}


def _safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def implied_prob(odds: float) -> float:
    return 1.0 / odds if odds else 0.0


def devig_2way(odds_a: float, odds_b: float) -> tuple:
    """Return (prob_a, prob_b) after removing bookmaker margin."""
    if not odds_a or not odds_b:
        return None, None
    p_a = implied_prob(odds_a)
    p_b = implied_prob(odds_b)
    total = p_a + p_b
    return p_a / total, p_b / total


def ev(ml_prob: float, market_odds: float) -> float:
    """EV = (ml_prob * market_odds) - 1."""
    return (ml_prob * market_odds) - 1.0


def kelly_fraction(ml_prob: float, market_odds: float) -> float:
    """Full Kelly fraction."""
    b = market_odds - 1.0
    return (ml_prob * b - (1 - ml_prob)) / b if b > 0 else 0.0


# ---------------------------------------------------------------------------
# Main backtest
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--features', default=str(FEATURES))
    parser.add_argument('--xlsx',     default=str(XLSX))
    args = parser.parse_args()

    # Load features
    df = pd.read_csv(args.features, low_memory=False)
    df.replace('', np.nan, inplace=True)
    test_df = df[df['split'] == 'test'].copy()
    print(f'Test games (2025): {len(test_df)}')

    # Load models
    margin_model = load_model('margin_model')
    total_model  = load_model('total_model')
    h2h_model    = load_model('h2h_model')

    # Prepare features
    X = test_df[FEATURE_COLS].fillna(0)
    test_df = test_df.copy()
    test_df['ml_margin']    = margin_model.predict(X)
    test_df['ml_total']     = total_model.predict(X)
    test_df['ml_home_prob'] = h2h_model.predict_proba(X)[:, 1]
    test_df['ml_away_prob'] = 1.0 - test_df['ml_home_prob']
    # confidence = distance from 50/50
    test_df['ml_confidence'] = test_df['ml_home_prob'].apply(
        lambda p: abs(p - 0.5) + 0.5)

    # Load market odds
    odds_dict = load_odds_2025(Path(args.xlsx))

    records = []

    for _, row in test_df.iterrows():
        date_str  = row['date']
        home      = row['home_team']
        away      = row['away_team']
        home_op   = TEAM_MAP_REVERSE.get(home, home)
        away_op   = TEAM_MAP_REVERSE.get(away, away)

        key = (date_str, home_op, away_op)
        odds = odds_dict.get(key, {})

        h2h_home = _safe_float(odds.get('h2h_home_open'))
        h2h_away = _safe_float(odds.get('h2h_away_open'))
        home_line = _safe_float(odds.get('home_line_open'))
        total_line = _safe_float(odds.get('total_open'))
        actual_home = _safe_float(odds.get('home_score'))
        actual_away = _safe_float(odds.get('away_score'))

        # actual result
        if actual_home is not None and actual_away is not None:
            actual_margin = actual_home - actual_away
            actual_total  = actual_home + actual_away
            actual_win    = 1 if actual_margin > 0 else 0
        else:
            actual_margin = _safe_float(row.get('home_margin'))
            actual_total  = _safe_float(row.get('total_score'))
            actual_win    = _safe_float(row.get('home_win'))

        ml_home_prob = row['ml_home_prob']
        ml_margin    = row['ml_margin']
        ml_total     = row['ml_total']
        confidence   = row['ml_confidence']

        # Fair odds (no margin)
        ml_home_odds = round(1.0 / ml_home_prob, 3) if ml_home_prob > 0.01 else None
        ml_away_odds = round(1.0 / (1 - ml_home_prob), 3) if ml_home_prob < 0.99 else None

        # Devig market
        mkt_home_prob, mkt_away_prob = devig_2way(h2h_home, h2h_away)

        # EV on H2H
        ev_home = ev(ml_home_prob, h2h_home) if h2h_home else None
        ev_away = ev(1 - ml_home_prob, h2h_away) if h2h_away else None

        # Handicap edge: ML margin vs market line
        # market line is home_line_open (e.g. -6.5 means home gives 6.5)
        # positive edge = ML thinks home margin > line (bet home)
        # negative edge = ML thinks away covers
        if home_line is not None:
            handicap_edge = ml_margin - (-home_line)   # home_line is negative for favourite
            # Actually OddsPortal: home_line_open is the number of points for home
            # e.g. +6.5 means home starts with +6.5 point handicap
            # So home covers if: actual_margin + home_line > 0
            # ML edge: ml_margin + home_line (> 0 = bet home; < 0 = bet away)
            handicap_edge = ml_margin + home_line
        else:
            handicap_edge = None

        # Total edge
        if total_line is not None:
            total_edge = ml_total - total_line
        else:
            total_edge = None

        # Handicap result
        if home_line is not None and actual_margin is not None:
            home_covers = 1 if (actual_margin + home_line) > 0 else 0
        else:
            home_covers = None

        # Total result
        if total_line is not None and actual_total is not None:
            over_hit = 1 if actual_total > total_line else 0
        else:
            over_hit = None

        rec = {
            'date':          date_str,
            'home':          home,
            'away':          away,
            'venue':         row['venue'],
            'is_final':      int(row.get('is_final', 0) or 0),

            # ML outputs
            'ml_home_prob':  round(ml_home_prob, 4),
            'ml_margin':     round(ml_margin, 1),
            'ml_total':      round(ml_total, 1),
            'ml_confidence': round(confidence, 4),
            'ml_home_odds':  ml_home_odds,
            'ml_away_odds':  ml_away_odds,

            # Market
            'mkt_home_open': h2h_home,
            'mkt_away_open': h2h_away,
            'mkt_home_prob': round(mkt_home_prob, 4) if mkt_home_prob else '',
            'home_line_open':  home_line,
            'total_line_open': total_line,

            # Edges
            'ev_home':       round(ev_home, 4) if ev_home is not None else '',
            'ev_away':       round(ev_away, 4) if ev_away is not None else '',
            'handicap_edge': round(handicap_edge, 1) if handicap_edge is not None else '',
            'total_edge':    round(total_edge, 1) if total_edge is not None else '',

            # Actuals
            'actual_home_score': actual_home if actual_home else '',
            'actual_away_score': actual_away if actual_away else '',
            'actual_margin':     actual_margin if actual_margin is not None else '',
            'actual_total':      actual_total  if actual_total  is not None else '',
            'actual_home_win':   actual_win    if actual_win    is not None else '',
            'home_covers':       home_covers   if home_covers   is not None else '',
            'over_hit':          over_hit      if over_hit      is not None else '',
        }
        records.append(rec)

    # ── Save CSV ─────────────────────────────────────────────────────────────
    REPORT_CSV.parent.mkdir(parents=True, exist_ok=True)
    if records:
        with open(REPORT_CSV, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)
        print(f'Detail saved → {REPORT_CSV}')

    # ── Analytics ────────────────────────────────────────────────────────────
    recs = pd.DataFrame(records)
    recs = recs.replace('', np.nan)

    # Add ML-favored side columns (always bet the side the model prefers)
    def ml_side_ev(r):
        """EV of betting the side the ML model favors."""
        hp = _safe_float(r['ml_home_prob'])
        ho = _safe_float(r['mkt_home_open'])
        ao = _safe_float(r['mkt_away_open'])
        if hp is None or ho is None or ao is None:
            return np.nan
        if hp >= 0.5:
            return ev(hp, ho)
        else:
            return ev(1 - hp, ao)

    def ml_side_odds(r):
        hp = _safe_float(r['ml_home_prob'])
        ho = _safe_float(r['mkt_home_open'])
        ao = _safe_float(r['mkt_away_open'])
        if hp is None:
            return np.nan
        return ho if hp >= 0.5 else ao

    def ml_side_won(r):
        hp = _safe_float(r['ml_home_prob'])
        aw = _safe_float(r['actual_home_win'])
        if hp is None or aw is None:
            return np.nan
        if hp >= 0.5:
            return 1.0 if aw == 1.0 else 0.0
        else:
            return 1.0 if aw == 0.0 else 0.0

    recs['ml_side_ev']   = recs.apply(ml_side_ev,   axis=1)
    recs['ml_side_odds'] = recs.apply(ml_side_odds, axis=1)
    recs['ml_side_won']  = recs.apply(ml_side_won,  axis=1)

    lines = []

    def section(title: str):
        lines.append('\n' + '=' * 60 + '\n')
        lines.append(title + '\n')
        lines.append('=' * 60 + '\n')

    def bullet(text: str):
        lines.append(f'  {text}\n')

    lines.append('AFL ML Backtest — 2025 Season\n')
    lines.append(f'Total games: {len(recs)}\n')
    with_odds = recs[recs['mkt_home_open'].notna()]
    bullet(f'Games with market odds: {len(with_odds)}')

    # ── H2H accuracy at various confidence thresholds ─────────────────────
    section('H2H Model — Strike Rate by Confidence Threshold (ML-favored side)')
    for thresh in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        sub = recs[(recs['ml_confidence'] >= thresh) & recs['ml_side_won'].notna()].copy()
        if len(sub) < 5:
            continue
        strike = sub['ml_side_won'].mean()
        bullet(f'≥{thresh:.0%} confidence: {len(sub):3d} games  {strike:.1%} strike')

    # ── H2H ROI — ML-favored side, full universe ─────────────────────────
    section('H2H ROI — Betting ML-Favored Side (full 2025 season)')
    sub_full = recs[recs['ml_side_won'].notna() & recs['ml_side_odds'].notna()].copy()
    if len(sub_full):
        total_staked = len(sub_full)
        total_return = sub_full.apply(
            lambda r: r['ml_side_odds'] if r['ml_side_won'] == 1 else 0, axis=1).sum()
        roi_full = (total_return / total_staked) - 1
        wins_full = sub_full['ml_side_won'].sum()
        bullet(f'All games: {total_staked} bets  {wins_full:.0f}W  ROI {roi_full:+.1%}')

    # ── H2H ROI by confidence filter ─────────────────────────────────────
    section('H2H ROI — ML-Favored Side by Confidence Threshold')
    for thresh in [0.55, 0.60, 0.65, 0.70, 0.75]:
        sub = recs[
            (recs['ml_confidence'] >= thresh) &
            recs['ml_side_won'].notna() &
            recs['ml_side_odds'].notna()
        ].copy()
        if len(sub) < 5:
            continue
        returns = sub.apply(
            lambda r: r['ml_side_odds'] if r['ml_side_won'] == 1 else 0, axis=1)
        roi = (returns.sum() / len(sub)) - 1
        strike = sub['ml_side_won'].mean()
        bullet(f'Conf ≥{thresh:.0%}: {len(sub):3d} bets  {strike:.1%} strike  ROI {roi:+.1%}')

    # ── H2H ROI by minimum odds (price filter) ────────────────────────────
    section('H2H ROI — ML-Favored Side by Min Price (Conf ≥ 65%)')
    sub_conf = recs[
        (recs['ml_confidence'] >= 0.65) &
        recs['ml_side_won'].notna() &
        recs['ml_side_odds'].notna()
    ].copy()
    for min_odds in [1.40, 1.50, 1.60, 1.70, 1.80, 2.00]:
        sub = sub_conf[sub_conf['ml_side_odds'] >= min_odds]
        if len(sub) < 3:
            continue
        returns = sub.apply(
            lambda r: r['ml_side_odds'] if r['ml_side_won'] == 1 else 0, axis=1)
        roi = (returns.sum() / len(sub)) - 1
        strike = sub['ml_side_won'].mean()
        bullet(f'Odds ≥ {min_odds:.2f}: {len(sub):3d} bets  {strike:.1%} strike  ROI {roi:+.1%}')

    # ── H2H ROI — positive EV filter ─────────────────────────────────────
    section('H2H ROI — ML-Favored Side, Positive EV Filter')
    sub_ev = recs[
        recs['ml_side_ev'].notna() &
        recs['ml_side_won'].notna() &
        recs['ml_side_odds'].notna()
    ].copy()
    for ev_thresh in [0.0, 0.05, 0.10, 0.15, 0.20]:
        sub = sub_ev[sub_ev['ml_side_ev'] >= ev_thresh]
        if len(sub) < 3:
            continue
        returns = sub.apply(
            lambda r: r['ml_side_odds'] if r['ml_side_won'] == 1 else 0, axis=1)
        roi = (returns.sum() / len(sub)) - 1
        strike = sub['ml_side_won'].mean()
        bullet(f'EV ≥ {ev_thresh:+.0%}: {len(sub):3d} bets  {strike:.1%} strike  ROI {roi:+.1%}')

    # ── Combined filters ──────────────────────────────────────────────────
    section('H2H ROI — Combined Filters (ML-favored side)')
    for conf, ev_t, odds_t in [
        (0.65, 0.00, 1.50),
        (0.65, 0.05, 1.50),
        (0.65, 0.10, 1.50),
        (0.70, 0.00, 1.50),
        (0.70, 0.05, 1.50),
        (0.75, 0.00, 1.50),
    ]:
        sub = recs[
            (recs['ml_confidence'] >= conf) &
            (recs['ml_side_ev'] >= ev_t) &
            (recs['ml_side_odds'] >= odds_t) &
            recs['ml_side_won'].notna()
        ]
        if len(sub) < 3:
            bullet(f'Conf≥{conf:.0%} EV≥{ev_t:+.0%} Odds≥{odds_t:.2f}: < 3 bets')
            continue
        returns = sub.apply(
            lambda r: r['ml_side_odds'] if r['ml_side_won'] == 1 else 0, axis=1)
        roi = (returns.sum() / len(sub)) - 1
        strike = sub['ml_side_won'].mean()
        bullet(f'Conf≥{conf:.0%} EV≥{ev_t:+.0%} Odds≥{odds_t:.2f}: {len(sub):3d} bets  {strike:.1%} strike  ROI {roi:+.1%}')

    # ── Handicap analysis ────────────────────────────────────────────────
    section('Handicap — ML Edge vs Market Line')
    recs['handicap_edge'] = pd.to_numeric(recs['handicap_edge'], errors='coerce')
    recs['home_covers']   = pd.to_numeric(recs['home_covers'],   errors='coerce')
    sub_hc = recs[recs['handicap_edge'].notna() & recs['home_covers'].notna()]

    for edge_thresh in [0, 3, 5, 8, 10, 12, 15]:
        sub_pos = sub_hc[sub_hc['handicap_edge'] >= edge_thresh]   # bet home covers
        sub_neg = sub_hc[sub_hc['handicap_edge'] <= -edge_thresh]  # bet away covers
        total = len(sub_pos) + len(sub_neg)
        if total < 5:
            continue
        pos_covers = sub_pos['home_covers'].sum()
        neg_covers = (1 - sub_neg['home_covers']).sum()
        combined_win = pos_covers + neg_covers
        strike = combined_win / total
        bullet(f'Edge ≥ ±{edge_thresh:2d}pts: {total:3d} bets  {combined_win:.0f}W  {strike:.1%} strike')

    # ── Totals ────────────────────────────────────────────────────────────
    section('Totals — ML vs Market Line')
    recs['total_edge'] = pd.to_numeric(recs['total_edge'], errors='coerce')
    recs['over_hit']   = pd.to_numeric(recs['over_hit'],   errors='coerce')
    sub_tot = recs[recs['total_edge'].notna() & recs['over_hit'].notna()]

    for edge in [0, 5, 10, 15]:
        sub_over  = sub_tot[sub_tot['total_edge'] >= edge]
        sub_under = sub_tot[sub_tot['total_edge'] <= -edge]
        total = len(sub_over) + len(sub_under)
        if total < 5:
            continue
        over_hits  = sub_over['over_hit'].sum()
        under_hits = (1 - sub_under['over_hit']).sum()
        strike = (over_hits + under_hits) / total
        bullet(f'Total edge ≥ ±{edge:2d}pts: {total:3d} bets  {strike:.1%} strike')

    # ── print + save ─────────────────────────────────────────────────────
    report = ''.join(lines)
    print('\n' + report)
    REPORT_TXT.write_text(report)
    print(f'Report saved → {REPORT_TXT}')


if __name__ == '__main__':
    main()
