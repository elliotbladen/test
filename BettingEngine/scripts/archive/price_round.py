#!/usr/bin/env python3
"""
scripts/price_round.py

Run Tier 1 + Tier 2 + Tier 3 pricing for a given season and round, then record
a tier2_performance row for every game.

Tier 2 results are updated with actuals if results are already in the DB.

USAGE
-----
    python scripts/price_round.py --season 2026 --round 5
    python scripts/price_round.py --season 2026 --round 5 --dry-run
    python scripts/price_round.py --season 2026 --round 5 6 7
"""

import argparse
import sqlite3
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pricing.tier1_baseline import compute_baseline
from pricing.tier2_matchup import (
    compute_family_a, compute_family_b, compute_family_c, compute_family_d,
)
from pricing.tier3_situational import compute_situational_adjustments
from pricing.tier4_venue import compute_venue_adjustments
from pricing.tier5_injury import compute_injury_adjustments
from pricing.tier6_referee import get_ref_context, compute_referee_adjustments
from pricing.tier7_environment import compute_weather_adjustments
from pricing.engine import derive_final_prices
from db.queries import (
    get_team_stats,
    get_prior_season_stats,
    get_team_style_stats,
    get_style_league_norms,
    get_situational_context,
    get_team_venue_edge,
    get_venue_total_edge,
    get_venue_name,
    get_team_injury_pts,
    get_weather_conditions,
    insert_tier2_performance,
    update_tier2_results,
)

MODEL_VERSION = '1.0.0-abc'

TOTALS_FLOOR   = 30.0
TOTALS_CEILING = 70.0



def _get_family_label(result: dict, direction: str) -> str:
    """Extract the attack label for one direction from a family result dict."""
    d = result.get('debug', {})
    key = 'h_attacks_a_label' if direction == 'h' else 'a_attacks_h_label'
    return d.get(key, 'none')


def price_match(conn, match_row, tier2_cfg, tiers_cfg, dry_run: bool) -> dict:
    """Run Tier 1 + Tier 2 + Tier 3 for one match. Return the performance record dict."""
    match_id   = match_row['match_id']
    home_tid   = match_row['home_team_id']
    away_tid   = match_row['away_team_id']
    venue_id   = match_row['venue_id']
    match_date = match_row['match_date']
    season     = match_row['season']
    home_name  = match_row['home_team']
    away_name  = match_row['away_team']

    # --- Tier 1 ---
    home_stats = get_team_stats(conn, home_tid, season, match_date) or {}
    away_stats = get_team_stats(conn, away_tid, season, match_date) or {}
    home_prior = get_prior_season_stats(conn, home_tid, season)
    away_prior = get_prior_season_stats(conn, away_tid, season)

    t1_cfg  = tiers_cfg.get('tier1_baseline', {})
    t1      = compute_baseline(
        home_stats, away_stats, {}, t1_cfg,
        home_prior_stats=home_prior, away_prior_stats=away_prior,
    )
    t1_home    = t1['baseline_home_points']
    t1_away    = t1['baseline_away_points']
    t1_mrg     = t1['baseline_margin']
    totals_T1  = t1.get('totals_T1', t1['baseline_total'])

    # --- Tier 2 families ---
    home_style = get_team_style_stats(conn, home_tid, season, match_date) or {}
    away_style = get_team_style_stats(conn, away_tid, season, match_date) or {}
    as_of      = home_style.get('as_of_date') or away_style.get('as_of_date') or match_date
    norms      = get_style_league_norms(conn, season, as_of)

    fa = compute_family_a(home_style, away_style, norms, tier2_cfg)
    fc = compute_family_c(home_style, away_style, norms, tier2_cfg)
    # Pass 2A deltas for overlap monitoring only — no effect on 2D math.
    fd = compute_family_d(
        home_style, away_style, norms, tier2_cfg,
        home_2a_delta=fa['home_delta'], away_2a_delta=fa['away_delta'],
    )
    fb = compute_family_b(home_style, away_style, norms, tier2_cfg)

    t2a_h = fa['home_delta']
    t2b_h = fb['home_delta']
    t2c_h = fc['home_delta']
    t2d_h = fd['home_delta']

    raw_home_t2 = t2a_h + t2b_h + t2c_h + t2d_h
    raw_away_t2 = fa['away_delta'] + fb['away_delta'] + fc['away_delta'] + fd['away_delta']

    # T2 totals: sum family totals deltas, cap at ±3.0
    raw_totals_T2 = (fa.get('totals_delta', 0.0) + fb.get('totals_delta', 0.0)
                     + fc.get('totals_delta', 0.0) + fd.get('totals_delta', 0.0))
    totals_T2 = round(max(-3.0, min(3.0, raw_totals_T2)), 3)

    cap_t2 = float(tier2_cfg.get('max_home_points_delta', 4.0))
    scale_t2 = 1.0
    if abs(raw_home_t2) > cap_t2 and raw_home_t2 != 0.0:
        scale_t2 = min(scale_t2, cap_t2 / abs(raw_home_t2))
    if abs(raw_away_t2) > cap_t2 and raw_away_t2 != 0.0:
        scale_t2 = min(scale_t2, cap_t2 / abs(raw_away_t2))

    t2_capped_home = round(raw_home_t2 * scale_t2, 3)
    t2_capped_away = round(raw_away_t2 * scale_t2, 3)

    # fired families
    fired = []
    if t2a_h != 0.0 or fa['away_delta'] != 0.0: fired.append('A')
    if t2b_h != 0.0 or fb['away_delta'] != 0.0: fired.append('B')
    if t2c_h != 0.0 or fc['away_delta'] != 0.0: fired.append('C')
    if t2d_h != 0.0 or fd['away_delta'] != 0.0: fired.append('D')
    fired_str = ','.join(fired)

    # --- Tier 3 ---
    sit_ctx = get_situational_context(
        conn, match_id, home_tid, away_tid, venue_id, match_date, season
    )
    t3 = compute_situational_adjustments(sit_ctx, tiers_cfg)
    t3_home = t3['home_delta_capped']
    t3_away = t3['away_delta_capped']
    totals_T3 = t3.get('totals_delta', 0.0)

    # --- Tier 5 injury ---
    t5_cfg = tiers_cfg.get('tier5_injury', {})
    h_injury_pts = get_team_injury_pts(conn, match_id, home_tid)
    a_injury_pts = get_team_injury_pts(conn, match_id, away_tid)
    t5 = compute_injury_adjustments(h_injury_pts, a_injury_pts, t5_cfg)
    t5_handicap_delta = t5['handicap_delta']
    totals_T5         = t5['totals_delta']
    t5_debug          = t5['_debug']

    # --- Tier 4 venue ---
    t4_cfg         = tiers_cfg.get('tier4_venue', {})
    home_v_edge    = get_team_venue_edge(conn, home_tid, venue_id)
    away_v_edge    = get_team_venue_edge(conn, away_tid, venue_id)
    venue_tot_edge = get_venue_total_edge(conn, venue_id)
    venue_name_str = get_venue_name(conn, venue_id)
    if t4_cfg.get('enabled', True):
        t4 = compute_venue_adjustments(
            home_tid, away_tid, venue_id,
            home_v_edge, away_v_edge, venue_tot_edge,
            t4_cfg,
        )
        t4_handicap_delta = t4['handicap_delta']
        totals_T4         = t4['totals_delta']
    else:
        t4_handicap_delta = 0.0
        totals_T4         = 0.0

    # --- Tier 6 referee ---
    t6_cfg = tiers_cfg.get('tier6_referee', {})
    t6_ctx = get_ref_context(conn, match_id, home_tid, away_tid, season)
    if t6_ctx and t6_cfg.get('enabled', True):
        t6 = compute_referee_adjustments(
            t6_ctx['home_bucket_edge'],
            t6_ctx['away_bucket_edge'],
            t6_ctx['bucket'],
            t6_cfg,
        )
        t6_handicap_delta = t6['handicap_delta']
        totals_T6         = t6['totals_delta']
        t6_bucket         = t6_ctx['bucket']
        t6_referee_name   = t6_ctx['referee_name']
    else:
        t6_handicap_delta = 0.0
        totals_T6         = 0.0
        t6_bucket         = None
        t6_referee_name   = None

    # --- Tier 7 weather ---
    t7_cfg     = tiers_cfg.get('tier7_environment', {})
    kickoff_dt = match_row.get('kickoff_datetime') or ''
    weather_row = get_weather_conditions(conn, match_id)
    t7 = compute_weather_adjustments(weather_row, kickoff_dt, t7_cfg)
    totals_T7          = t7['totals_delta']
    t7_condition_type  = t7['condition_type']
    t7_dew_risk        = int(t7['dew_risk'])

    # --- Final margin combination ---
    final_home = round(t1_home + t2_capped_home + t3_home, 3)
    final_away = round(t1_away + t2_capped_away + t3_away, 3)
    final_mrg  = round(final_home - final_away + t4_handicap_delta + t5_handicap_delta + t6_handicap_delta, 3)

    # --- Final totals combination ---
    raw_final_total = totals_T1 + totals_T2 + totals_T3 + totals_T5 + totals_T4 + totals_T6 + totals_T7
    final_total = round(max(TOTALS_FLOOR, min(TOTALS_CEILING, raw_final_total)), 2)
    pred_home_score = round((final_total + final_mrg) / 2.0, 1)
    pred_away_score = round((final_total - final_mrg) / 2.0, 1)

    # --- Derive final market prices ---
    prices = derive_final_prices(pred_home_score, pred_away_score, t1_cfg)

    record = {
        'match_id':      match_id,
        'model_version': MODEL_VERSION,
        'season':        season,
        'round_number':  match_row['round_number'],
        'match_date':    match_date,
        'home_team_id':  home_tid,
        'away_team_id':  away_tid,

        't1_home_pts': round(t1_home, 3),
        't1_away_pts': round(t1_away, 3),
        't1_margin':   round(t1_mrg, 3),

        't2a_home_delta': t2a_h,
        't2b_home_delta': t2b_h,
        't2c_home_delta': t2c_h,
        't2_raw_total':   round(raw_home_t2, 3),
        't2_capped_total': t2_capped_home,
        't2_scale_applied': round(scale_t2, 4) if scale_t2 < 1.0 else None,

        't2a_label_h': _get_family_label(fa, 'h'),
        't2a_label_a': _get_family_label(fa, 'a'),
        't2b_label_h': _get_family_label(fb, 'h'),
        't2b_label_a': _get_family_label(fb, 'a'),
        't2c_label_h': _get_family_label(fc, 'h'),
        't2c_label_a': _get_family_label(fc, 'a'),

        'fired_families': fired_str,

        # Net handicap contribution per tier (home perspective)
        't2_net_hcap': round(t2_capped_home - t2_capped_away, 3),
        't3_net_hcap': round(t3_home - t3_away, 3),

        'final_margin':    final_mrg,
        'final_home_pts':  final_home,
        'final_away_pts':  final_away,

        # Totals
        'totals_T1':         round(totals_T1, 2),
        'totals_T2':         totals_T2,
        'totals_T3':         round(totals_T3, 3),
        'totals_T5':         totals_T5,
        'totals_T6':         totals_T6,
        'totals_T7':         totals_T7,
        'raw_final_total':   round(raw_final_total, 2),
        'final_total':       final_total,
        'pred_home_score':   pred_home_score,
        'pred_away_score':   pred_away_score,
        '_t5_debug':         t5_debug,

        # Tier 5 injury
        't5_handicap_delta': t5_handicap_delta,
        't5_home_injury_pts': h_injury_pts,
        't5_away_injury_pts': a_injury_pts,

        # Fair market prices (from derive_final_prices)
        'fair_home_odds':       prices['fair_home_odds'],
        'fair_away_odds':       prices['fair_away_odds'],
        'home_win_probability': prices['home_win_probability'],
        'away_win_probability': prices['away_win_probability'],
        'fair_handicap_line':   prices['fair_handicap_line'],
        'fair_total_line':      prices['fair_total_line'],

        # 105% book odds (standard 5% bookmaker overround applied proportionally)
        'h2h_home_105':  round(prices['fair_home_odds'] / 1.05, 3),
        'h2h_away_105':  round(prices['fair_away_odds'] / 1.05, 3),

        # Tier 4 venue
        't4_handicap_delta': t4_handicap_delta,
        'totals_T4':         totals_T4,
        't4_venue_name':     venue_name_str,
        't4_home_edge':      home_v_edge,
        't4_away_edge':      away_v_edge,

        # Tier 6
        't6_referee_name':    t6_referee_name,
        't6_bucket':          t6_bucket,
        't6_handicap_delta':  t6_handicap_delta,

        # Tier 7
        't7_condition_type': t7_condition_type,
        't7_dew_risk':       t7_dew_risk,

        # 2D tracked separately — not in tier2_performance schema yet.
        '_t2d_home_delta':  t2d_h,
        '_t2d_away_delta':  fd['away_delta'],
        '_t2d_label_h':     _get_family_label(fd, 'h'),
        '_t2d_label_a':     _get_family_label(fd, 'a'),
        '_t2d_2a_agree':    fd['debug'].get('_2a_same_direction'),

        # Tier 3 — logged to stdout; separate performance table not yet written.
        '_t3_home_delta':   t3_home,
        '_t3_away_delta':   t3_away,
        '_t3_3a':           t3.get('3a_home_delta', 0.0),
        '_t3_3b':           t3.get('3b_home_delta', 0.0),
        '_t3_3c_home':      t3.get('3c_home_delta', 0.0),
        '_t3_3c_away':      t3.get('3c_away_delta', 0.0),
        '_t3_home_rest':    sit_ctx.get('home_rest_days'),
        '_t3_away_rest':    sit_ctx.get('away_rest_days'),
        '_t3_home_km':      sit_ctx.get('home_travel_km'),
        '_t3_away_km':      sit_ctx.get('away_travel_km'),
        '_t3_debug':        t3.get('debug', {}),
    }

    mode      = 'DRY-RUN' if dry_run else 'written'
    scale_str = f' T2scale={scale_t2:.3f}' if scale_t2 < 1.0 else ''

    d_str  = f' 2D={t2d_h:+.0f}' if (t2d_h != 0.0 or fd['away_delta'] != 0.0) else ' 2D= 0'

    # Tier 3 summary string
    t3_str = ''
    if t3_home != 0.0 or t3_away != 0.0:
        t3_str = f' T3={t3_home:+.1f}'
        if t3['scale_applied']:
            t3_str += f'(cap)'
    else:
        t3_str = ' T3=  0'

    # Rest/travel annotation
    h_rest = sit_ctx.get('home_rest_days')
    a_rest = sit_ctx.get('away_rest_days')
    rest_ann = ''
    if h_rest is not None and a_rest is not None:
        rest_ann = f' [{h_rest}d/{a_rest}d]'

    t4_str = f'  T4={t4_handicap_delta:+.1f}' if t4_handicap_delta != 0.0 else '  T4= 0'
    t5h_str = f'  T5h={t5_handicap_delta:+.1f}' if t5_handicap_delta != 0.0 else ''

    t6_str = ''
    if t6_referee_name:
        t6_str = f'  T6={t6_handicap_delta:+.1f}({t6_bucket[0].upper() if t6_bucket else "?"})'
    else:
        t6_str = '  T6= 0'

    ref_str = f'  ref={t6_referee_name}' if t6_referee_name else ''

    print(f"  R{match_row['round_number']} {home_name:<36} vs {away_name:<36}  "
          f"T1={t1_mrg:+.1f}  2A={t2a_h:+.0f} 2B={t2b_h:+.0f} 2C={t2c_h:+.0f}{d_str}{t3_str}{t4_str}{t5h_str}{t6_str}  "
          f"margin={final_mrg:+.1f}  total={final_total:.1f}  "
          f"({pred_home_score:.1f}-{pred_away_score:.1f})  "
          f"[{fired_str or '—'}]{scale_str}{rest_ann}{ref_str}  {mode}")

    return record


def main():
    parser = argparse.ArgumentParser(description='Price a round and record Tier 2 performance')
    parser.add_argument('--season',      type=int, default=2026)
    parser.add_argument('--round',       type=int, nargs='+', required=True)
    parser.add_argument('--dry-run',     action='store_true')
    parser.add_argument('--settings',    default='config/settings.yaml')
    args = parser.parse_args()

    settings  = yaml.safe_load(open(args.settings))
    tiers_cfg = yaml.safe_load(open('config/tiers.yaml'))
    tier2_cfg = tiers_cfg.get('tier2_matchup', {})

    conn = sqlite3.connect(settings['database']['path'])
    conn.row_factory = sqlite3.Row

    rounds_str = ', '.join(str(r) for r in args.round)
    placeholders = ', '.join('?' for _ in args.round)
    matches = conn.execute(f"""
        SELECT m.match_id, m.match_date, m.round_number, m.season,
               m.home_team_id, m.away_team_id, m.venue_id,
               h.team_name as home_team, a.team_name as away_team
        FROM matches m
        JOIN teams h ON m.home_team_id = h.team_id
        JOIN teams a ON m.away_team_id = a.team_id
        WHERE m.season = ? AND m.round_number IN ({placeholders})
        ORDER BY m.match_date, m.match_id
    """, [args.season] + args.round).fetchall()

    print(f"\nPricing season={args.season} rounds={rounds_str}  "
          f"({len(matches)} games)  mode={'DRY RUN' if args.dry_run else 'WRITE'}")
    print(f"model_version={MODEL_VERSION}\n")

    records = []
    for m in matches:
        rec = price_match(conn, m, tier2_cfg, tiers_cfg, args.dry_run)
        records.append(rec)

    team_names = {
        row['team_id']: row['team_name']
        for row in conn.execute("SELECT team_id, team_name FROM teams").fetchall()
    }

    def short(name: str, n: int = 28) -> str:
        return name if len(name) <= n else name[:n-1] + '…'

    # ── Handicap build-up ────────────────────────────────────────────────────
    W1 = 178
    print(f"\n{'═'*W1}")
    print(f"  HANDICAP BUILD-UP  (home perspective — positive = home favoured)   |   H2H at 105% book")
    print(f"{'─'*W1}")
    print(f"  {'Matchup':<46}  "
          f"{'T1mrg':>6}  {'T2h':>6}  {'T3h':>6}  {'T4h':>6}  {'T5h':>6}  {'T6h':>6}  "
          f"{'Margin':>7}  {'Hcap':>6}  "
          f"{'H%':>5}  {'H(fair)':>8}  {'A(fair)':>8}  {'H@105':>7}  {'A@105':>7}  {'Score':>11}")
    print(f"{'─'*W1}")
    for rec in records:
        h  = short(team_names.get(rec['home_team_id'], '?'))
        a  = short(team_names.get(rec['away_team_id'], '?'))
        matchup = f"{h} vs {a}"
        hpct    = rec['home_win_probability'] * 100
        score   = f"({rec['pred_home_score']:.1f}-{rec['pred_away_score']:.1f})"
        print(f"  {matchup:<46}  "
              f"{rec['t1_margin']:>+6.1f}  "
              f"{rec['t2_net_hcap']:>+6.1f}  "
              f"{rec['t3_net_hcap']:>+6.1f}  "
              f"{rec['t4_handicap_delta']:>+6.1f}  "
              f"{rec['t5_handicap_delta']:>+6.1f}  "
              f"{rec['t6_handicap_delta']:>+6.1f}  "
              f"{rec['final_margin']:>+7.1f}  "
              f"{rec['fair_handicap_line']:>+6.1f}  "
              f"{hpct:>4.1f}%  "
              f"{rec['fair_home_odds']:>8.3f}  "
              f"{rec['fair_away_odds']:>8.3f}  "
              f"{rec['h2h_home_105']:>7.3f}  "
              f"{rec['h2h_away_105']:>7.3f}  "
              f"{score:>11}")
    print(f"{'═'*W1}")

    # ── Totals build-up ──────────────────────────────────────────────────────
    # Shows how each tier contributes to the final total points line
    W2 = 180
    print(f"\n{'═'*W2}")
    print(f"  TOTALS BUILD-UP")
    print(f"{'─'*W2}")
    print(f"  {'Matchup':<46}  "
          f"{'T1tot':>6}  {'T2t':>6}  {'T3t':>6}  {'T4t':>6}  {'T5t':>6}  {'T6t':>6}  {'T7t':>6}  "
          f"{'Total':>6}  {'Score':>11}  {'Referee':<26}  {'Bucket':<14}  {'Weather'}")
    print(f"{'─'*W2}")
    for rec in records:
        h  = short(team_names.get(rec['home_team_id'], '?'))
        a  = short(team_names.get(rec['away_team_id'], '?'))
        matchup  = f"{h} vs {a}"
        ref_col  = rec.get('t6_referee_name') or '—'
        bkt_col  = rec.get('t6_bucket') or '—'
        score    = f"({rec['pred_home_score']:.1f}-{rec['pred_away_score']:.1f})"
        dew_flag = ' [dew]' if rec.get('t7_dew_risk') else ''
        wx_col   = f"{rec.get('t7_condition_type', 'clear')}{dew_flag}"
        print(f"  {matchup:<46}  "
              f"{rec['totals_T1']:>6.1f}  "
              f"{rec['totals_T2']:>+6.2f}  "
              f"{rec['totals_T3']:>+6.2f}  "
              f"{rec['totals_T4']:>+6.2f}  "
              f"{rec['totals_T5']:>+6.2f}  "
              f"{rec['totals_T6']:>+6.2f}  "
              f"{rec['totals_T7']:>+6.2f}  "
              f"{rec['final_total']:>6.1f}  "
              f"{score:>11}  "
              f"{ref_col:<26}  {bkt_col:<14}  {wx_col}")
    print(f"{'═'*W2}")

    if not args.dry_run:
        for rec in records:
            insert_tier2_performance(conn, rec)
        print(f"\n  {len(records)} rows written to tier2_performance.")

        for season_val in set(r['season'] for r in records):
            n = update_tier2_results(conn, season_val, MODEL_VERSION)
            if n:
                print(f"  {n} rows updated with actual results (season={season_val}).")

    conn.close()


if __name__ == '__main__':
    main()
