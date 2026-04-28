#!/usr/bin/env python3
"""
scripts/export_round_csv.py

Export a full pricing summary CSV for a given round.
Columns:
  - game info (date, kickoff, venue, teams)
  - predicted scores and totals
  - fair (100%) and 105% overround prices for H2H, handicap, totals
  - per-tier handicap adjustment: T1–T7 hcap, final_margin
  - per-tier totals adjustment: T1–T8 totals, final_total
  - injury detail: home/away pts, who is out
  - referee detail: name, bucket
  - weather detail: condition, temp, wind
  - per-tier explanation notes (t1_note … t8_note)
  - combined explanation (all tiers in one sentence)
  - results columns (blank until game is played)

Usage:
    python scripts/export_round_csv.py --season 2026 --round 9
    python scripts/export_round_csv.py --season 2026 --round 9 --out results/r9_pricing.csv
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'data' / 'model.db'

OVERROUND = 1.05          # 105% book
HCAP_SYM_PRICE = round(1 / (0.5 * OVERROUND), 3)   # 1.905 — both sides of spread/total


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _t2_net_hcap(row: dict) -> float:
    """Derive T2 net handicap delta: final_margin minus all other tier contributions."""
    t1  = row.get('t1_margin', 0) or 0
    t3  = (row.get('t3_home_delta', 0) or 0) - (row.get('t3_away_delta', 0) or 0)
    t4  = row.get('t4_handicap_delta', 0) or 0
    t5  = row.get('t5_handicap_delta', 0) or 0
    t6  = row.get('t6_handicap_delta', 0) or 0
    t7e = 0.0   # emotional — no flags loaded this round
    fm  = row.get('final_margin', 0) or 0
    return round(fm - t1 - t3 - t4 - t5 - t6 - t7e, 3)


def _t8_wx_delta(row: dict) -> float:
    """Derive T8 weather totals delta: final_total minus T1–T7 totals sum."""
    sub = (
        (row.get('totals_T1') or 0)
        + (row.get('totals_T2') or 0)
        + (row.get('totals_T3') or 0)
        + (row.get('totals_T4') or 0)
        + (row.get('totals_T5') or 0)
        + (row.get('totals_T6') or 0)
        + (row.get('totals_T7') or 0)   # emotional totals
    )
    return round((row.get('final_total') or 0) - sub, 2)


# ---------------------------------------------------------------------------
# Per-tier note builders
# ---------------------------------------------------------------------------

def _note_t1(row: dict) -> str:
    home, away = row['home_name'], row['away_name']
    t1 = row.get('t1_margin', 0) or 0
    h_elo = row.get('t1_home_pts', 0) or 0
    a_elo = row.get('t1_away_pts', 0) or 0
    if abs(t1) < 1.5:
        return f"ELO near-equal — baseline margin {t1:+.1f}pt (H:{h_elo:.1f} A:{a_elo:.1f})"
    leader = home if t1 > 0 else away
    return f"{leader} ELO edge — baseline margin {t1:+.1f}pt (H:{h_elo:.1f} A:{a_elo:.1f})"


def _note_t2(row: dict) -> str:
    home, away = row['home_name'], row['away_name']
    t2 = _t2_net_hcap(row)
    families = row.get('fired_families') or 'none'
    t2_tot = row.get('totals_T2') or 0
    if abs(t2) < 0.5 and abs(t2_tot) < 0.5:
        return f"No style edge fired (families checked: {families})"
    direction = home if t2 > 0 else away
    return (f"Style matchup fires family [{families}] — "
            f"{direction} hcap {t2:+.1f}pt / totals {t2_tot:+.1f}pt")


def _note_t3(row: dict) -> str:
    home, away = row['home_name'], row['away_name']
    t3h = row.get('t3_home_delta', 0) or 0
    t3a = row.get('t3_away_delta', 0) or 0
    net = t3h - t3a
    t3_tot = row.get('totals_T3') or 0
    h_rest = row.get('t3_home_rest_days') or 0
    a_rest = row.get('t3_away_rest_days') or 0
    h_km   = row.get('t3_home_travel_km') or 0
    a_km   = row.get('t3_away_travel_km') or 0
    notes = []
    if h_rest and h_rest <= 6:
        notes.append(f"{home} short turnaround ({h_rest}d rest)")
    elif h_rest and h_rest >= 10:
        notes.append(f"{home} extra rest ({h_rest}d)")
    if a_rest and a_rest <= 6:
        notes.append(f"{away} short turnaround ({a_rest}d rest)")
    elif a_rest and a_rest >= 10:
        notes.append(f"{away} extra rest ({a_rest}d)")
    if h_km and h_km > 500:
        notes.append(f"{home} travelled {h_km:.0f}km")
    if a_km and a_km > 500:
        notes.append(f"{away} travelled {a_km:.0f}km")
    detail = "; ".join(notes) if notes else "no significant rest/travel factors"
    return f"Situational: {detail} — hcap net {net:+.2f}pt / totals {t3_tot:+.2f}pt"


def _note_t4(row: dict) -> str:
    home, away = row['home_name'], row['away_name']
    t4h = row.get('t4_handicap_delta', 0) or 0
    t4t = row.get('totals_T4') or 0
    venue = row.get('t4_venue_name') or row.get('match_venue') or 'venue'
    if abs(t4h) < 0.5 and abs(t4t) < 0.5:
        return f"No venue edge at {venue}"
    direction = home if t4h > 0 else away
    return f"Venue edge: {direction} at {venue} — hcap {t4h:+.1f}pt / totals {t4t:+.1f}pt"


def _note_t5(row: dict, injuries: dict) -> str:
    home, away = row['home_name'], row['away_name']
    h_pts = row.get('t5_home_injury_pts', 0) or 0
    a_pts = row.get('t5_away_injury_pts', 0) or 0
    t5h   = row.get('t5_handicap_delta', 0) or 0
    h_inj = injuries.get((row['home_team_id'], row['match_id']), [])
    a_inj = injuries.get((row['away_team_id'], row['match_id']), [])
    parts = []
    if h_inj:
        names = ", ".join(f"{p['player_name']} ({p['importance_tier']})" for p in h_inj)
        parts.append(f"{home} outs [{names}] = {h_pts:.1f}pts")
    else:
        parts.append(f"{home} no outs")
    if a_inj:
        names = ", ".join(f"{p['player_name']} ({p['importance_tier']})" for p in a_inj)
        parts.append(f"{away} outs [{names}] = {a_pts:.1f}pts")
    else:
        parts.append(f"{away} no outs")
    return "; ".join(parts) + f" — net hcap shift {t5h:+.1f}pt"


def _note_t6(row: dict) -> str:
    ref    = row.get('t6_referee_name') or 'TBC'
    bucket = row.get('t6_bucket') or 'neutral'
    t6h    = row.get('t6_handicap_delta', 0) or 0
    t6t    = row.get('totals_T6') or 0
    desc = {
        'flow_heavy':    'flow ref — more set restarts, higher totals',
        'whistle_heavy': 'whistle ref — more penalties, lower scoring',
        'neutral':       'neutral ref — no totals or hcap adjustment',
    }.get(bucket, 'neutral')
    return f"{ref} ({bucket}): {desc} — hcap {t6h:+.1f}pt / totals {t6t:+.1f}pt"


def _note_t7(row: dict) -> str:
    t7h = 0.0   # emotional — no flags loaded this round
    t7t = row.get('totals_T7') or 0
    if abs(t7h) < 0.1 and abs(t7t) < 0.1:
        return "No emotional flags loaded for this game"
    return f"Emotional flags — hcap {t7h:+.1f}pt / totals {t7t:+.1f}pt"


def _note_t8(row: dict) -> str:
    wx    = row.get('wx_condition') or row.get('t7_condition_type') or 'clear'
    dew   = row.get('wx_dew_risk') or row.get('t7_dew_risk') or 0
    temp  = row.get('temp_c')
    wind  = row.get('wind_kmh')
    delta = row.get('_t8_wx_delta', 0.0) or 0.0
    wx_str = wx.replace('_', ' ')
    detail = []
    if temp is not None:
        detail.append(f"{temp:.1f}°C")
    if wind is not None:
        detail.append(f"wind {wind:.0f}km/h")
    if dew:
        detail.append("dew risk")
    conds = ", ".join(detail) if detail else "no data"
    return f"Weather: {wx_str} ({conds}) — totals {delta:+.1f}pt"


def _combined_explanation(row: dict, injuries: dict) -> str:
    """One paragraph covering every tier concisely."""
    notes = [
        _note_t1(row),
        _note_t2(row),
        _note_t3(row),
        _note_t4(row),
        _note_t5(row, injuries),
        _note_t6(row),
        _note_t7(row),
        _note_t8(row),
    ]
    return " | ".join(f"T{i+1}: {n}" for i, n in enumerate(notes))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Export round pricing CSV')
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--round',  type=int, required=True, dest='round_number')
    parser.add_argument('--out',    default=None)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT
            tp.*,
            t1.team_name  AS home_name,
            t2.team_name  AS away_name,
            m.kickoff_datetime,
            v.venue_name  AS match_venue,
            r.home_score  AS actual_home,
            r.away_score  AS actual_away,
            wc.condition_type AS wx_condition,
            wc.temp_c, wc.wind_kmh, wc.precipitation_mm, wc.dew_risk AS wx_dew_risk
        FROM tier2_performance tp
        JOIN matches m  ON m.match_id  = tp.match_id
        JOIN teams t1   ON t1.team_id  = tp.home_team_id
        JOIN teams t2   ON t2.team_id  = tp.away_team_id
        LEFT JOIN venues v ON v.venue_id = m.venue_id
        LEFT JOIN results r ON r.match_id = tp.match_id
        LEFT JOIN weather_conditions wc ON wc.match_id = tp.match_id
        WHERE tp.season = ? AND tp.round_number = ?
        ORDER BY m.match_date, tp.match_id
    """, (args.season, args.round_number)).fetchall()

    if not rows:
        print(f"No pricing data found for S{args.season} R{args.round_number}", file=sys.stderr)
        sys.exit(1)

    # Load injury reports keyed by (team_id, match_id)
    injuries = {}
    inj_rows = conn.execute("""
        SELECT ir.match_id, ir.team_id, ir.player_name, ir.importance_tier, ir.status
        FROM injury_reports ir
        JOIN matches m ON m.match_id = ir.match_id
        WHERE m.season = ? AND m.round_number = ? AND ir.status IN ('out','doubtful')
    """, (args.season, args.round_number)).fetchall()
    for ir in inj_rows:
        k = (ir['team_id'], ir['match_id'])
        injuries.setdefault(k, []).append(dict(ir))

    # Output path
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = ROOT / 'results' / f'r{args.round_number}_pricing_{args.season}.csv'
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        # ── Game info ──────────────────────────────────────────────────────
        'season', 'round', 'date', 'kickoff', 'venue',
        'home_team', 'away_team',

        # ── Predicted scores ───────────────────────────────────────────────
        'pred_home_score', 'pred_away_score', 'pred_total',

        # ── Fair (100%) prices ─────────────────────────────────────────────
        'fair_home_odds', 'fair_away_odds',
        'fair_hcap_line',     # negative = home is favourite (gives away points)
        'fair_total_line',

        # ── 105% overround prices ──────────────────────────────────────────
        'h2h_home_105', 'h2h_away_105',
        'hcap_line_105', 'hcap_price_105',     # both sides at 1.905
        'total_line_105', 'total_price_105',   # both sides at 1.905

        # ── Tier handicap adjustments (home perspective, pts) ──────────────
        't1_hcap',    # ELO/baseline margin
        't2_hcap',    # style matchup
        't3_hcap',    # situational (rest/travel/form)
        't4_hcap',    # venue
        't5_hcap',    # injuries/suspensions
        't6_hcap',    # referee
        't7_hcap',    # emotional flags
        'final_margin',

        # ── Tier totals adjustments (pts added/removed from total) ─────────
        't1_totals',
        't2_totals',
        't3_totals',
        't4_totals',
        't5_totals',
        't6_totals',
        't7_totals',  # emotional
        't8_totals',  # weather
        'final_total',

        # ── Injury detail ──────────────────────────────────────────────────
        't5_home_inj_pts', 't5_away_inj_pts',
        'home_outs', 'away_outs',

        # ── Referee detail ─────────────────────────────────────────────────
        'referee', 'ref_bucket',

        # ── Weather detail ─────────────────────────────────────────────────
        'weather_condition', 'temp_c', 'wind_kmh',

        # ── Per-tier explanation notes ─────────────────────────────────────
        't1_note', 't2_note', 't3_note', 't4_note',
        't5_note', 't6_note', 't7_note', 't8_note',

        # ── Combined explanation ────────────────────────────────────────────
        'explanation',

        # ── Actual result (blank pre-match) ────────────────────────────────
        'actual_home', 'actual_away', 'actual_total',
        'margin_error', 'total_error',

        # ── Model meta ─────────────────────────────────────────────────────
        'model_version',
    ]

    out_rows = []
    for r in rows:
        r = dict(r)

        # Inject derived values
        r['_t2_hcap']    = _t2_net_hcap(r)
        r['_t8_wx_delta'] = _t8_wx_delta(r)

        # Injury strings
        h_inj = injuries.get((r['home_team_id'], r['match_id']), [])
        a_inj = injuries.get((r['away_team_id'], r['match_id']), [])
        home_outs = "; ".join(
            f"{p['player_name']} ({p['importance_tier']}, {p['status']})" for p in h_inj
        ) or "none"
        away_outs = "; ".join(
            f"{p['player_name']} ({p['importance_tier']}, {p['status']})" for p in a_inj
        ) or "none"

        # Weather label
        wx_condition = r.get('wx_condition') or r.get('t7_condition_type') or 'clear'
        wx_label     = wx_condition.replace('_', ' ')
        if r.get('wx_dew_risk') or r.get('t7_dew_risk'):
            wx_label += ' + dew'

        # Actual results
        a_home = r.get('actual_home')
        a_away = r.get('actual_away')
        a_total    = (a_home + a_away) if (a_home is not None and a_away is not None) else ''
        margin_err = round(r['final_margin'] - (a_home - a_away), 2) if a_home is not None else ''
        total_err  = round((r.get('final_total') or 0) - a_total, 2) if a_total != '' else ''

        # Kickoff
        ko         = r.get('kickoff_datetime') or ''
        date_str   = ko[:10] if ko else (r.get('match_date') or '')
        time_str   = ko[11:16] if len(ko) > 10 else ''

        # Per-tier notes
        t1_note = _note_t1(r)
        t2_note = _note_t2(r)
        t3_note = _note_t3(r)
        t4_note = _note_t4(r)
        t5_note = _note_t5(r, injuries)
        t6_note = _note_t6(r)
        t7_note = _note_t7(r)
        t8_note = _note_t8(r)

        explanation = (
            f"T1: {t1_note} | "
            f"T2: {t2_note} | "
            f"T3: {t3_note} | "
            f"T4: {t4_note} | "
            f"T5: {t5_note} | "
            f"T6: {t6_note} | "
            f"T7: {t7_note} | "
            f"T8: {t8_note}"
        )

        out_rows.append({
            # ── Game info ────────────────────────────────────────────────
            'season':            args.season,
            'round':             args.round_number,
            'date':              date_str,
            'kickoff':           time_str,
            'venue':             r.get('match_venue') or r.get('t4_venue_name') or '',
            'home_team':         r['home_name'],
            'away_team':         r['away_name'],

            # ── Predicted scores ─────────────────────────────────────────
            'pred_home_score':   r['pred_home_score'],
            'pred_away_score':   r['pred_away_score'],
            'pred_total':        round((r['pred_home_score'] or 0) + (r['pred_away_score'] or 0), 1),

            # ── Fair prices ──────────────────────────────────────────────
            'fair_home_odds':    r['fair_home_odds'],
            'fair_away_odds':    r['fair_away_odds'],
            'fair_hcap_line':    r['fair_handicap_line'],
            'fair_total_line':   r['fair_total_line'],

            # ── 105% prices ──────────────────────────────────────────────
            'h2h_home_105':      round((r['fair_home_odds'] or 0) / OVERROUND, 2),
            'h2h_away_105':      round((r['fair_away_odds'] or 0) / OVERROUND, 2),
            'hcap_line_105':     r['fair_handicap_line'],
            'hcap_price_105':    HCAP_SYM_PRICE,
            'total_line_105':    r['fair_total_line'],
            'total_price_105':   HCAP_SYM_PRICE,

            # ── Tier handicap (home perspective) ─────────────────────────
            't1_hcap':           round(r.get('t1_margin') or 0, 2),
            't2_hcap':           round(r['_t2_hcap'], 2),
            't3_hcap':           round((r.get('t3_home_delta') or 0) - (r.get('t3_away_delta') or 0), 2),
            't4_hcap':           round(r.get('t4_handicap_delta') or 0, 2),
            't5_hcap':           round(r.get('t5_handicap_delta') or 0, 2),
            't6_hcap':           round(r.get('t6_handicap_delta') or 0, 2),
            't7_hcap':           0.0,   # emotional — no flags this round
            'final_margin':      round(r.get('final_margin') or 0, 2),

            # ── Tier totals ──────────────────────────────────────────────
            't1_totals':         round(r.get('totals_T1') or 0, 2),
            't2_totals':         round(r.get('totals_T2') or 0, 2),
            't3_totals':         round(r.get('totals_T3') or 0, 2),
            't4_totals':         round(r.get('totals_T4') or 0, 2),
            't5_totals':         round(r.get('totals_T5') or 0, 2),
            't6_totals':         round(r.get('totals_T6') or 0, 2),
            't7_totals':         round(r.get('totals_T7') or 0, 2),
            't8_totals':         r['_t8_wx_delta'],
            'final_total':       round(r.get('final_total') or 0, 2),

            # ── Injury detail ────────────────────────────────────────────
            't5_home_inj_pts':   round(r.get('t5_home_injury_pts') or 0, 1),
            't5_away_inj_pts':   round(r.get('t5_away_injury_pts') or 0, 1),
            'home_outs':         home_outs,
            'away_outs':         away_outs,

            # ── Referee ──────────────────────────────────────────────────
            'referee':           r.get('t6_referee_name') or '',
            'ref_bucket':        r.get('t6_bucket') or 'neutral',

            # ── Weather ──────────────────────────────────────────────────
            'weather_condition': wx_label,
            'temp_c':            r.get('temp_c') or '',
            'wind_kmh':          r.get('wind_kmh') or '',

            # ── Per-tier notes ───────────────────────────────────────────
            't1_note':           t1_note,
            't2_note':           t2_note,
            't3_note':           t3_note,
            't4_note':           t4_note,
            't5_note':           t5_note,
            't6_note':           t6_note,
            't7_note':           t7_note,
            't8_note':           t8_note,

            # ── Combined explanation ─────────────────────────────────────
            'explanation':       explanation,

            # ── Actual results ───────────────────────────────────────────
            'actual_home':       a_home if a_home is not None else '',
            'actual_away':       a_away if a_away is not None else '',
            'actual_total':      a_total,
            'margin_error':      margin_err,
            'total_error':       total_err,

            # ── Model meta ───────────────────────────────────────────────
            'model_version':     r.get('model_version') or '',
        })

    with open(out_path, 'w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Written {len(out_rows)} rows → {out_path}")
    conn.close()


if __name__ == '__main__':
    main()
