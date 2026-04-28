#!/usr/bin/env python3
"""
scripts/build_afl_t2_matchups.py

AFL Tier 2 matchup engine — stat-based, regression-validated.

Computes style-matchup adjustments using:
  - Real season-average team stats from data/footywire_team_stats.csv
  - Regression-validated multipliers (see scripts/derive_t2_multipliers.py)

Significant predictors (p < 0.05) after controlling for ELO:
  1. Inside 50s/game   (2.04 pts per unit diff)  — forward entry volume
  2. Marks inside 50   (2.58 pts per unit diff)  — quality forward entry
  3. CP/game           (0.50 pts per unit diff)  — midfield dominance
  4. Goal conversion % (141 pts per 1.0 unit)   — scoring efficiency

NOT significant and excluded: clearances/game (p=0.57), rebound 50s (p=0.88)

NOTE: Key Position matchup (Family 4) deferred to next year.

USAGE
-----
    python3 scripts/build_afl_t2_matchups.py --season 2026 --round 9
    python3 scripts/build_afl_t2_matchups.py --demo   (use hardcoded R9 2026)
"""

import argparse
import csv
import sqlite3
from pathlib import Path

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'data' / 'model.db'
FW_CSV  = ROOT / 'data' / 'footywire_team_stats.csv'

# ---------------------------------------------------------------------------
# Regression-validated multipliers
# Source: scripts/derive_t2_multipliers.py, 2013-2023 regular season
#
# We use the ELO-RESIDUAL coefficients (style-only regression after
# partialling out ELO), not the full regression coefficients.
# Reason: ELO already captures team quality. T2 should only add the
# incremental style effect that is NOT already priced by ELO.
#
# Full model R² = 0.383; ELO alone R² = 0.247; style vars add +0.136
#
# ELO-residual significant predictors (p < 0.10):
#   inside_50s_pg:  1.49 pts/unit  (p<0.001 ***)
#   goal_conv_pct:  47.0 pts/1.0   (p=0.031 *)
#   clearances_pg:  0.60 pts/unit  (p=0.039 *)
#   rebound_50s_pg: 0.46 pts/unit  (p=0.099, marginal — included conservatively)
#
# Dropped from T2 (not significant in residual model):
#   marks_i50_pg:  p=0.159 (quality captured by ELO)
#   cp_pg:         p=0.110 (quality captured by ELO)
# ---------------------------------------------------------------------------
T2_MULTIPLIERS = {
    'inside_50s_pg':  1.49,    # *** pts per I50/game advantage  (ELO-residual)
    'goal_conv_pct':  47.0,    # *   pts per 1.0 (100%) goal-conv (ELO-residual)
    'clearances_pg':  0.60,    # *   pts per clearance/game adv   (ELO-residual)
    'rebound_50s_pg': 0.46,    # ~   pts per R50/game advantage   (marginal p=0.099)
}

T2_CONFIG = {
    'max_t2_delta':  7.0,    # absolute cap on total T2 handicap adjustment
    'max_tot_delta': 3.0,    # absolute cap on total T2 totals adjustment
    'totals_scale':  0.30,   # totals = |handicap_delta| × this, directional
}


# ---------------------------------------------------------------------------
# Load Footywire stats
# ---------------------------------------------------------------------------
def load_footywire(path: Path = FW_CSV) -> dict:
    """
    Returns lookup: (season, canonical_team_name) → {stat: value, ...}
    """
    lookup: dict = {}
    if not path.exists():
        print(f"WARNING: {path} not found — T2 will use neutral stats")
        return lookup
    with open(path) as f:
        for row in csv.DictReader(f):
            key = (int(row['season']), row['team_name'])
            lookup[key] = {k: float(v) if v else None
                           for k, v in row.items()
                           if k not in ('season', 'team_name')}
    return lookup


# ---------------------------------------------------------------------------
# T2 calculation using raw stats
# ---------------------------------------------------------------------------
def compute_t2_from_stats(home_stats: dict | None,
                          away_stats: dict | None) -> dict:
    """
    Compute T2 adjustment from raw season-average stats.
    Returns dict with per-family points and totals.
    home_stats / away_stats: dict of {field: float} from footywire CSV.
    """

    def diff(stat: str) -> float | None:
        h = (home_stats or {}).get(stat)
        a = (away_stats or {}).get(stat)
        if h is None or a is None:
            return None
        return h - a

    components = {}

    # Forward Entry (I50) ─────────────────────────────────────────────────────
    d_i50   = diff('inside_50s_pg')
    fwd_pts = 0.0
    if d_i50 is not None:
        fwd_pts = T2_MULTIPLIERS['inside_50s_pg'] * d_i50
    components['fwd_entry_pts'] = round(fwd_pts, 2)

    # Goal Conversion Efficiency ──────────────────────────────────────────────
    d_gc   = diff('goal_conv_pct')
    gc_pts = 0.0
    if d_gc is not None:
        gc_pts = T2_MULTIPLIERS['goal_conv_pct'] * d_gc
    components['gc_pts'] = round(gc_pts, 2)

    # Clearances ──────────────────────────────────────────────────────────────
    d_cl   = diff('clearances_pg')
    cl_pts = 0.0
    if d_cl is not None:
        cl_pts = T2_MULTIPLIERS['clearances_pg'] * d_cl
    components['cl_pts'] = round(cl_pts, 2)

    # Rebound 50s (marginal) ──────────────────────────────────────────────────
    d_r50   = diff('rebound_50s_pg')
    r50_pts = 0.0
    if d_r50 is not None:
        r50_pts = T2_MULTIPLIERS['rebound_50s_pg'] * d_r50
    components['r50_pts'] = round(r50_pts, 2)

    # Combined handicap delta (home perspective)
    raw_handicap = fwd_pts + gc_pts + cl_pts + r50_pts
    t2_handicap  = max(-T2_CONFIG['max_t2_delta'],
                       min(T2_CONFIG['max_t2_delta'], raw_handicap))

    # Totals: high I50 + goal efficiency games tend to be higher scoring
    t2_totals = max(-T2_CONFIG['max_tot_delta'],
                    min(T2_CONFIG['max_tot_delta'],
                        (fwd_pts + gc_pts) * T2_CONFIG['totals_scale']))

    components['raw_handicap'] = round(raw_handicap, 2)
    components['t2_handicap']  = round(t2_handicap, 2)
    components['t2_totals']    = round(t2_totals, 2)
    components['capped']       = abs(raw_handicap) > T2_CONFIG['max_t2_delta']

    # Raw stat differentials for display
    components['d_i50']   = round(d_i50,  2) if d_i50  is not None else None
    components['d_gc']    = round(d_gc * 100, 2) if d_gc is not None else None  # as pct
    components['d_cl']    = round(d_cl,   2) if d_cl   is not None else None
    components['d_r50']   = round(d_r50,  2) if d_r50  is not None else None

    return components


def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


# ---------------------------------------------------------------------------
# Demo matchups (R9 2026 — until AFL fixture is in DB)
# ---------------------------------------------------------------------------
DEMO_ROUND = [
    ('Adelaide Crows',          'Port Adelaide Power',          'Adelaide Oval'),
    ('Collingwood Magpies',     'Carlton Blues',                'MCG'),
    ('Geelong Cats',            'Brisbane Lions',               'GMHBA Stadium'),
    ('Greater Western Sydney Giants', 'North Melbourne Kangaroos', 'Giants Stadium'),
    ('Hawthorn Hawks',          'Fremantle Dockers',            'UTAS Stadium'),
    ('Melbourne Demons',        'Essendon Bombers',             'MCG'),
    ('Richmond Tigers',         'Gold Coast Suns',              'Punt Road'),
    ('St Kilda Saints',         'Sydney Swans',                 'Marvel Stadium'),
    ('West Coast Eagles',       'Western Bulldogs',             'Optus Stadium'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--round',  type=int, default=9)
    parser.add_argument('--db',     default=str(DB_PATH))
    parser.add_argument('--demo',   action='store_true',
                        help='Use hardcoded R9 2026 matchups (no DB needed)')
    args = parser.parse_args()

    # Load Footywire stats
    fw = load_footywire(FW_CSV)
    season_fw = args.season

    # Use prior season stats if current season is too early
    # (less than 6 rounds played — season averages not yet stable)
    # For 2026 before R9, use 2025 season averages as proxy
    if season_fw == 2026:
        # Check if 2026 data exists in CSV
        has_2026 = any(k[0] == 2026 for k in fw)
        if not has_2026:
            print(f"No 2026 Footywire data — using 2025 season averages as proxy")
            season_fw = 2025

    # ── Get matchups ──────────────────────────────────────────────────────────
    if args.demo:
        matchups = [{'home': h, 'away': a, 'venue': v, 'match_id': None}
                    for h, a, v in DEMO_ROUND]
        print(f"\n[DEMO MODE — using hardcoded R{args.round} matchups]")
    else:
        conn = sqlite3.connect(args.db)
        conn.row_factory = sqlite3.Row
        cur  = conn.cursor()
        rows = cur.execute("""
            SELECT m.match_id,
                   ht.team_name AS home_name, at.team_name AS away_name,
                   v.venue_name
            FROM matches m
            JOIN teams  ht ON ht.team_id = m.home_team_id
            JOIN teams  at ON at.team_id = m.away_team_id
            JOIN venues v  ON v.venue_id  = m.venue_id
            WHERE m.season = ? AND m.round_number = ?
              AND ht.league = 'AFL'
            ORDER BY m.match_id
        """, (args.season, args.round)).fetchall()

        if not rows:
            print(f'No AFL matches found for {args.season} R{args.round}')
            print('  (Tip: run with --demo to use hardcoded R9 matchups)')
            conn.close()
            return
        matchups = [{'home': r['home_name'], 'away': r['away_name'],
                     'venue': r['venue_name'], 'match_id': r['match_id']}
                    for r in rows]

    # ── Compute T2 for each match ─────────────────────────────────────────────
    results = []
    for m in matchups:
        home_stats = fw.get((season_fw, m['home']))
        away_stats = fw.get((season_fw, m['away']))
        t2 = compute_t2_from_stats(home_stats, away_stats)
        results.append({**m, **t2})

    # ── Print table ───────────────────────────────────────────────────────────
    stat_yr_label = f'{season_fw} stats'
    print()
    print('=' * 118)
    print(f'  AFL Tier 2 — Style Matchup  |  {args.season} Round {args.round}'
          f'  (using {stat_yr_label})')
    print(f'  Multipliers from ELO-residual regression 2013-2023 (style R²=+0.136 over ELO):')
    print(f'  I50: {T2_MULTIPLIERS["inside_50s_pg"]:.2f}pts/unit  '
          f'GConv: {T2_MULTIPLIERS["goal_conv_pct"]:.0f}pts/100%  '
          f'CL: {T2_MULTIPLIERS["clearances_pg"]:.2f}pts/unit  '
          f'R50: {T2_MULTIPLIERS["rebound_50s_pg"]:.2f}pts/unit')
    print('=' * 118)
    print()

    HDR = (f"  {'Matchup':<42} {'I50 Δ':>7} {'GC% Δ':>7} {'CL Δ':>7} {'R50 Δ':>7}"
           f"  {'I50 Pts':>8} {'GC Pts':>7} {'CL Pts':>7} {'R50 Pts':>8}"
           f"  {'T2 Hdcp':>9} {'T2 Tot':>8}")
    print(HDR)
    print('  ' + '-' * 120)

    for r in results:
        home_s = r['home'].split()[-1]
        away_s = r['away'].split()[-1]
        matchup = f"{home_s} vs {away_s}"

        i50_d  = f"{r['d_i50']:+.1f}"   if r['d_i50']  is not None else '  n/a'
        gc_d   = f"{r['d_gc']:+.1f}%"   if r['d_gc']   is not None else '  n/a'
        cl_d   = f"{r['d_cl']:+.1f}"    if r['d_cl']   is not None else '  n/a'
        r50_d  = f"{r['d_r50']:+.1f}"   if r['d_r50']  is not None else '  n/a'

        fwd_s  = f"{r['fwd_entry_pts']:+.1f}"
        gc_s   = f"{r['gc_pts']:+.1f}"
        cl_s   = f"{r['cl_pts']:+.1f}"
        r50_s  = f"{r['r50_pts']:+.1f}"
        hdcp_s = f"{r['t2_handicap']:+.1f}"
        tot_s  = f"{r['t2_totals']:+.1f}"

        flag = ' ◀' if abs(r['t2_handicap']) >= 3.0 else ''
        if r.get('capped'):
            flag += '⚠'

        print(f"  {matchup:<42} {i50_d:>7} {gc_d:>7} {cl_d:>7} {r50_d:>7}"
              f"  {fwd_s:>8} {gc_s:>7} {cl_s:>7} {r50_s:>8}"
              f"  {hdcp_s:>9} {tot_s:>8}  {flag}")

    print()
    print('  Positive T2 Hdcp = home team has style advantage')
    print('  Δ columns are season-average differentials (home − away)')

    # ── Summary ───────────────────────────────────────────────────────────────
    meaningful = [r for r in results if abs(r['t2_handicap']) >= 2.0]
    if meaningful:
        print()
        print('  MEANINGFUL T2 ADJUSTMENTS (≥ 2 pts):')
        for r in meaningful:
            home_s = r['home'].split()[-1]
            away_s = r['away'].split()[-1]
            if r['t2_handicap'] > 0:
                favoured, margin = home_s, r['t2_handicap']
            else:
                favoured, margin = away_s, -r['t2_handicap']
            print(f'    {home_s} vs {away_s}:  '
                  f'T2 = {r["t2_handicap"]:+.1f}  '
                  f'style favours {favoured} by ~{margin:.1f} pts')

    print('=' * 118)

    # ── Write to DB if not demo ───────────────────────────────────────────────
    if not args.demo and matchups[0]['match_id'] is not None:
        for r in results:
            if r['match_id'] is None:
                continue
            cur.execute("""
                INSERT OR REPLACE INTO afl_t2_matchup_log (
                    match_id, season, round_number,
                    f2_home_fp_rating, f2_away_fp_rating, f2_differential, f2_pts_delta,
                    t2_handicap_delta, t2_totals_delta,
                    f1_applied, f2_applied, f3_applied, f4_applied
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                r['match_id'], args.season, args.round,
                r.get('d_i50', 0), 0, r.get('d_i50', 0), r['fwd_entry_pts'],
                r['t2_handicap'], r['t2_totals'],
                0, 1, 0, 0,
            ))
        conn.commit()
        conn.close()
        print(f"\n  Written {len(results)} rows to afl_t2_matchup_log")


if __name__ == '__main__':
    main()
