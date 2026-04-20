# pricing/tier2_matchup.py
# =============================================================================
# Tier 2 — Matchup layer
# =============================================================================
#
# OVERVIEW
# --------
# Tier 2 refines the Tier 1 baseline by asking:
#   "How do these two specific teams interact?"
#
# Tier 1 establishes the base number from class, form, and home advantage.
# Tier 2 overlays stylistic and matchup effects that sit above that number.
#
# CURRENTLY ACTIVE BUCKET
# -----------------------
# Bucket 1: Yardage / territory / ruck-momentum
#   Answers: which team is more likely to win the field-position and
#   momentum battle in this specific matchup?
#   Signals: run metres, completion/discipline, kick metres, ruck speed.
#
# STUBS — NOT YET IMPLEMENTED
# ----------------------------
# Bucket 2: Defensive system / discipline
# Bucket 3: Attacking shape / scoring-actions
# Overlay:  Coach H2H
# Overlay:  Team-vs-team history overlay
#
# OUTPUT FORMAT
# -------------
# compute_matchup_adjustments() returns a list of adjustment dicts.
# Each dict conforms to the model_adjustments schema and is logged separately
# so the contribution of each bucket is always auditable.
#
# Schema:
#   tier_number            int
#   tier_name              str
#   adjustment_code        str
#   adjustment_description str
#   home_points_delta      float
#   away_points_delta      float
#   margin_delta           float   (home_delta - away_delta)
#   total_delta            float   (home_delta + away_delta)
#   _debug                 dict    full per-signal audit breakdown
#
# =============================================================================

import logging
import math

logger = logging.getLogger(__name__)

_TIER      = 2
_TIER_NAME = 'tier2_matchup'


# =============================================================================
# Family A — Territory & Control
# completion_rate + kick_metres_pg style  vs  errors_pg + penalties_pg vulnerability
# =============================================================================

def compute_family_a(
    home_style: dict,
    away_style: dict,
    norms: dict,
    config: dict,
) -> dict:
    """
    Compute Family A (Territory & Control) for both directions.

    Style side — the team that controls territory:
        completion_rate  (higher = better control)
        kick_metres_pg   (higher = better territorial kicking)
        errors_pg        (inverted — lower errors = better)
        penalties_pg     (inverted — lower penalties = better)

    Vulnerability side — the team that bleeds territory:
        errors_pg        (higher = more vulnerable)
        penalties_pg     (higher = more vulnerable)

    Weights (auto-normalised by their sum so they need not add to 1.0):
        Style:       cr=0.35  km=0.25  err(inv)=0.20  pen(inv)=0.15
        Vulnerability: err=0.60  pen=0.40

    Gate, ladder, and caps mirror Family B exactly:
        gate_threshold = 0.25  (both style > gate AND vuln > gate must pass)
        strong (≥0.40) → 3 pts | average (≥0.20) → 2 pts | weak (≥0.0625) → 1 pt
        inner_cap = 3.0 | outer_cap = 4.0

    Returns a dict with home_delta, away_delta, and a full debug breakdown.
    """
    fa_cfg   = config.get('family_a', {})
    enabled  = fa_cfg.get('enabled', True)
    if not enabled:
        return _family_a_neutral()

    # --- style weights (auto-normalised) ---
    cr_w      = float(fa_cfg.get('completion_rate_weight', 0.35))
    km_w      = float(fa_cfg.get('kick_metres_weight',     0.25))
    err_st_w  = float(fa_cfg.get('errors_style_weight',    0.20))
    pen_st_w  = float(fa_cfg.get('penalties_style_weight', 0.15))
    total_style_w = cr_w + km_w + err_st_w + pen_st_w

    # --- vulnerability weights ---
    err_vl_w  = float(fa_cfg.get('errors_vuln_weight',    0.60))
    pen_vl_w  = float(fa_cfg.get('penalties_vuln_weight', 0.40))
    total_vuln_w = err_vl_w + pen_vl_w

    # --- gate threshold ---
    gate = float(fa_cfg.get('gate_threshold', 0.25))

    # --- point values per classification ---
    pts = {
        'strong':  float(fa_cfg.get('strong_pts',  3.0)),
        'average': float(fa_cfg.get('average_pts', 2.0)),
        'weak':    float(fa_cfg.get('weak_pts',    1.0)),
        'none':    0.0,
    }

    # --- inner / outer caps ---
    inner_cap = float(fa_cfg.get('inner_cap', 3.0))
    outer_cap = float(fa_cfg.get('outer_cap', 4.0))

    # --- pull norms ---
    cr_avg,  cr_std  = norms.get('completion_rate',  (0.0, 1.0))
    km_avg,  km_std  = norms.get('kick_metres_pg',   (0.0, 1.0))
    err_avg, err_std = norms.get('errors_pg',        (0.0, 1.0))
    pen_avg, pen_std = norms.get('penalties_pg',     (0.0, 1.0))

    # --- per-team composite scores ---
    def _scores(sd):
        cr_n  = _normalize_stat(sd.get('completion_rate'), cr_avg,  cr_std)
        km_n  = _normalize_stat(sd.get('kick_metres_pg'),  km_avg,  km_std)
        err_n = _normalize_stat(sd.get('errors_pg'),       err_avg, err_std)
        pen_n = _normalize_stat(sd.get('penalties_pg'),    pen_avg, pen_std)
        # style: good completion/kicking + LOW errors/penalties
        if total_style_w > 0:
            style = (cr_w * cr_n + km_w * km_n
                     + err_st_w * (-err_n) + pen_st_w * (-pen_n)) / total_style_w
        else:
            style = 0.0
        style = max(-1.0, min(1.0, style))
        # vulnerability: HIGH errors/penalties
        if total_vuln_w > 0:
            vuln = (err_vl_w * err_n + pen_vl_w * pen_n) / total_vuln_w
        else:
            vuln = 0.0
        vuln = max(-1.0, min(1.0, vuln))
        return cr_n, km_n, err_n, pen_n, style, vuln

    h_cr_n, h_km_n, h_err_n, h_pen_n, h_style, h_vuln = _scores(home_style or {})
    a_cr_n, a_km_n, a_err_n, a_pen_n, a_style, a_vuln = _scores(away_style or {})

    # --- home attacks away ---
    gate_h  = h_style > gate and a_vuln > gate
    h_att_a = h_style * a_vuln if gate_h else 0.0
    label_h = _classify_edge(h_att_a)

    # --- away attacks home ---
    gate_a  = a_style > gate and h_vuln > gate
    a_att_h = a_style * h_vuln if gate_a else 0.0
    label_a = _classify_edge(a_att_h)

    # Raw deltas: home benefit = home style fires, away style fires hurts home
    raw_home = pts[label_h] - pts[label_a]
    raw_away = pts[label_a] - pts[label_h]

    # Inner cap
    home_delta = max(-inner_cap, min(inner_cap, raw_home))
    away_delta = max(-inner_cap, min(inner_cap, raw_away))

    # Outer cap
    home_delta = max(-outer_cap, min(outer_cap, home_delta))
    away_delta = max(-outer_cap, min(outer_cap, away_delta))

    debug = {
        'home_cr_n':   round(h_cr_n,  4), 'home_km_n':   round(h_km_n,  4),
        'home_err_n':  round(h_err_n, 4), 'home_pen_n':  round(h_pen_n, 4),
        'away_cr_n':   round(a_cr_n,  4), 'away_km_n':   round(a_km_n,  4),
        'away_err_n':  round(a_err_n, 4), 'away_pen_n':  round(a_pen_n, 4),
        'home_style_score':  round(h_style, 4),
        'home_vuln_score':   round(h_vuln,  4),
        'away_style_score':  round(a_style, 4),
        'away_vuln_score':   round(a_vuln,  4),
        'gate':              gate,
        'gate_passed_h':     gate_h,
        'gate_passed_a':     gate_a,
        'h_attacks_a_score': round(h_att_a, 4),
        'a_attacks_h_score': round(a_att_h, 4),
        'h_attacks_a_label': label_h,
        'a_attacks_h_label': label_a,
        'pts_h':             pts[label_h],
        'pts_a':             pts[label_a],
        'raw_home_delta':    round(raw_home, 3),
        'raw_away_delta':    round(raw_away, 3),
        'inner_cap':         inner_cap,
        'outer_cap':         outer_cap,
    }

    fires_a = home_delta != 0.0 or away_delta != 0.0
    return {
        'home_delta':   round(home_delta, 3),
        'away_delta':   round(away_delta, 3),
        'totals_delta': -1.5 if fires_a else 0.0,
        'debug':        debug,
    }


def _family_a_neutral() -> dict:
    return {
        'home_delta':   0.0,
        'away_delta':   0.0,
        'totals_delta': 0.0,
        'debug': {
            'home_cr_n': 0.0, 'home_km_n': 0.0, 'home_err_n': 0.0, 'home_pen_n': 0.0,
            'away_cr_n': 0.0, 'away_km_n': 0.0, 'away_err_n': 0.0, 'away_pen_n': 0.0,
            'home_style_score': 0.0, 'home_vuln_score': 0.0,
            'away_style_score': 0.0, 'away_vuln_score': 0.0,
            'gate': 0.25, 'gate_passed_h': False, 'gate_passed_a': False,
            'h_attacks_a_score': 0.0, 'a_attacks_h_score': 0.0,
            'h_attacks_a_label': 'none', 'a_attacks_h_label': 'none',
            'pts_h': 0.0, 'pts_a': 0.0,
            'raw_home_delta': 0.0, 'raw_away_delta': 0.0,
            'inner_cap': 3.0, 'outer_cap': 4.0,
        },
    }


def _print_family_a_debug(
    home_name: str,
    away_name: str,
    home_style: dict,
    away_style: dict,
    result: dict,
) -> None:
    """Always print Family A debug — fired or not."""
    d = result['debug']
    print(f"\n  [Tier2 Family A] {home_name} (H) vs {away_name} (A)")
    print(f"    Raw stats  — Home: cr={home_style.get('completion_rate')}, "
          f"km={home_style.get('kick_metres_pg')}, "
          f"err={home_style.get('errors_pg')}, pen={home_style.get('penalties_pg')}")
    print(f"               — Away: cr={away_style.get('completion_rate')}, "
          f"km={away_style.get('kick_metres_pg')}, "
          f"err={away_style.get('errors_pg')}, pen={away_style.get('penalties_pg')}")
    print(f"    Normalized — Home: cr_n={d['home_cr_n']:+.3f}  km_n={d['home_km_n']:+.3f}  "
          f"err_n={d['home_err_n']:+.3f}  pen_n={d['home_pen_n']:+.3f}")
    print(f"               — Away: cr_n={d['away_cr_n']:+.3f}  km_n={d['away_km_n']:+.3f}  "
          f"err_n={d['away_err_n']:+.3f}  pen_n={d['away_pen_n']:+.3f}")
    print(f"    Style score — Home={d['home_style_score']:+.4f}  Away={d['away_style_score']:+.4f}  "
          f"(gate>{d['gate']})")
    print(f"    Vuln score  — Home={d['home_vuln_score']:+.4f}  Away={d['away_vuln_score']:+.4f}")
    print(f"    H attacks A — gate={'PASS' if d['gate_passed_h'] else 'FAIL'}  "
          f"score={d['h_attacks_a_score']:.4f}  label={d['h_attacks_a_label']}  "
          f"pts={d['pts_h']:.1f}")
    print(f"    A attacks H — gate={'PASS' if d['gate_passed_a'] else 'FAIL'}  "
          f"score={d['a_attacks_h_score']:.4f}  label={d['a_attacks_h_label']}  "
          f"pts={d['pts_a']:.1f}")
    print(f"    Deltas      — home={result['home_delta']:+.3f}  away={result['away_delta']:+.3f}")


# =============================================================================
# Family D — Kicking Pressure & Exit Stress  [SOFT LAUNCH — controlled trial]
# fdo_pg style  vs  krm_pg (inverted) vulnerability
# =============================================================================
#
# STATUS: experimental. Caps are deliberately smaller than frozen families
#         (inner=2.0, outer=2.5 vs mature 3.0/4.0).
#
# OVERLAP AUDIT (confirmed clean):
#   fdo_pg  — not used in 2A, 2B, or 2C
#   krm_pg  — not used in 2A, 2B, or 2C
#   KM / errors / penalties / mt_pg / completion_rate are explicitly excluded
#
# INVERSION NOTE:
#   KRM vulnerability is inverted in this function.
#   Low KRM (poor exit quality) → high vulnerability score.
#   High KRM (strong exit quality) → low vulnerability score.
#   The gate check (vuln > gate) therefore triggers on BELOW-AVERAGE exit teams.
#
# OVERLAP MONITORING:
#   _print_family_d_debug() emits a 2A-compare line so post-game review can
#   identify games where 2D and 2A both fired in the same direction.
# =============================================================================

def compute_family_d(
    home_style: dict,
    away_style: dict,
    norms: dict,
    config: dict,
    home_2a_delta: float = 0.0,
    away_2a_delta: float = 0.0,
) -> dict:
    """
    Compute Family D (Kicking Pressure & Exit Stress) for both directions.

    Style side — the team that pins opponents with accurate kicks:
        fdo_pg   (forced dropouts per game; weight 1.0)
        High FDO = kicks land in dangerous positions, defenders are pinned.

    Vulnerability side — the team that struggles to exit under kick pressure:
        krm_pg   (kick return metres per game; INVERTED — low = vulnerable)
        Low KRM = team cannot escape their own end when kicked to.

    Normalisation: clamp(z / 2, -1.0, +1.0) — same as all other families.

    Caps (conservative — 2D is in soft launch):
        inner_cap = 2.0  (mature families: 3.0)
        outer_cap = 2.5  (mature families: 4.0)

    home_2a_delta / away_2a_delta are passed in for overlap monitoring only.
    They do NOT affect the 2D calculation.

    Returns dict with home_delta, away_delta, and full debug breakdown.
    """
    fd_cfg  = config.get('family_d', {})
    enabled = fd_cfg.get('enabled', True)
    if not enabled:
        return _family_d_neutral()

    # --- weights (single stat per side in V1) ---
    fdo_w        = float(fd_cfg.get('fdo_weight', 1.00))
    krm_w        = float(fd_cfg.get('krm_weight', 1.00))

    # --- gate threshold ---
    gate         = float(fd_cfg.get('gate_threshold', 0.25))

    # --- point values per classification ---
    pts = {
        'strong':  float(fd_cfg.get('strong_pts',  3.0)),
        'average': float(fd_cfg.get('average_pts', 2.0)),
        'weak':    float(fd_cfg.get('weak_pts',    1.0)),
        'none':    0.0,
    }

    # --- conservative caps ---
    inner_cap = float(fd_cfg.get('inner_cap', 2.0))
    outer_cap = float(fd_cfg.get('outer_cap', 2.5))

    # --- pull norms ---
    fdo_avg, fdo_std = norms.get('fdo_pg', (0.0, 1.0))
    krm_avg, krm_std = norms.get('krm_pg', (0.0, 1.0))

    # --- per-team scores ---
    def _scores(sd):
        fdo_n = _normalize_stat(sd.get('fdo_pg'), fdo_avg, fdo_std)
        krm_n = _normalize_stat(sd.get('krm_pg'), krm_avg, krm_std)

        # Style: high FDO = kicking pressure aggressor
        style = fdo_n * fdo_w
        style = max(-1.0, min(1.0, style))

        # Vulnerability: INVERTED KRM — low KRM = high vulnerability
        # A team returning few metres struggles to exit under kick pressure.
        vuln  = -(krm_n * krm_w)
        vuln  = max(-1.0, min(1.0, vuln))

        return fdo_n, krm_n, style, vuln

    h_fdo_n, h_krm_n, h_style, h_vuln = _scores(home_style or {})
    a_fdo_n, a_krm_n, a_style, a_vuln = _scores(away_style or {})

    # --- home attacks away ---
    gate_h  = h_style > gate and a_vuln > gate
    h_att_a = h_style * a_vuln if gate_h else 0.0
    label_h = _classify_edge(h_att_a)

    # --- away attacks home ---
    gate_a  = a_style > gate and h_vuln > gate
    a_att_h = a_style * h_vuln if gate_a else 0.0
    label_a = _classify_edge(a_att_h)

    # Raw deltas
    raw_home = pts[label_h] - pts[label_a]
    raw_away = pts[label_a] - pts[label_h]

    # Inner cap
    home_delta = max(-inner_cap, min(inner_cap, raw_home))
    away_delta = max(-inner_cap, min(inner_cap, raw_away))

    # Outer cap
    home_delta = max(-outer_cap, min(outer_cap, home_delta))
    away_delta = max(-outer_cap, min(outer_cap, away_delta))

    debug = {
        # Raw stats
        'home_fdo_pg':   home_style.get('fdo_pg'),
        'away_fdo_pg':   away_style.get('fdo_pg'),
        'home_krm_pg':   home_style.get('krm_pg'),
        'away_krm_pg':   away_style.get('krm_pg'),
        # Normalised components
        'home_fdo_n':    round(h_fdo_n, 4),
        'away_fdo_n':    round(a_fdo_n, 4),
        'home_krm_n':    round(h_krm_n, 4),
        'away_krm_n':    round(a_krm_n, 4),
        # Composite scores
        'home_style_score': round(h_style, 4),
        'away_style_score': round(a_style, 4),
        'home_vuln_score':  round(h_vuln,  4),  # inverted KRM
        'away_vuln_score':  round(a_vuln,  4),  # inverted KRM
        # Gate and matchup
        'gate':              gate,
        'gate_passed_h':     gate_h,
        'gate_passed_a':     gate_a,
        'h_attacks_a_score': round(h_att_a, 4),
        'a_attacks_h_score': round(a_att_h, 4),
        'h_attacks_a_label': label_h,
        'a_attacks_h_label': label_a,
        'pts_h':             pts[label_h],
        'pts_a':             pts[label_a],
        'raw_home_delta':    round(raw_home, 3),
        'raw_away_delta':    round(raw_away, 3),
        'inner_cap':         inner_cap,
        'outer_cap':         outer_cap,
        # Overlap monitoring vs 2A
        '_2a_home_delta':    round(home_2a_delta, 3),
        '_2a_away_delta':    round(away_2a_delta, 3),
        '_2a_same_direction': (
            (home_delta > 0 and home_2a_delta > 0) or
            (home_delta < 0 and home_2a_delta < 0)
        ) if (home_delta != 0 and home_2a_delta != 0) else None,
    }

    fires_d = home_delta != 0.0 or away_delta != 0.0
    return {
        'home_delta':   round(home_delta, 3),
        'away_delta':   round(away_delta, 3),
        'totals_delta': -0.75 if fires_d else 0.0,
        'debug':        debug,
    }


def _family_d_neutral() -> dict:
    return {
        'home_delta':   0.0,
        'away_delta':   0.0,
        'totals_delta': 0.0,
        'debug': {
            'home_fdo_pg': None, 'away_fdo_pg': None,
            'home_krm_pg': None, 'away_krm_pg': None,
            'home_fdo_n': 0.0, 'away_fdo_n': 0.0,
            'home_krm_n': 0.0, 'away_krm_n': 0.0,
            'home_style_score': 0.0, 'away_style_score': 0.0,
            'home_vuln_score':  0.0, 'away_vuln_score':  0.0,
            'gate': 0.25, 'gate_passed_h': False, 'gate_passed_a': False,
            'h_attacks_a_score': 0.0, 'a_attacks_h_score': 0.0,
            'h_attacks_a_label': 'none', 'a_attacks_h_label': 'none',
            'pts_h': 0.0, 'pts_a': 0.0,
            'raw_home_delta': 0.0, 'raw_away_delta': 0.0,
            'inner_cap': 2.0, 'outer_cap': 2.5,
            '_2a_home_delta': 0.0, '_2a_away_delta': 0.0,
            '_2a_same_direction': None,
        },
    }


def _print_family_d_debug(
    home_name: str,
    away_name: str,
    home_style: dict,
    away_style: dict,
    result: dict,
) -> None:
    """Always print Family D debug — fired or not."""
    d = result['debug']
    fired = result['home_delta'] != 0.0 or result['away_delta'] != 0.0
    status = '*** FIRED ***' if fired else 'neutral'

    print(f"\n  [Tier2 Family D — Kicking Pressure] {home_name} (H) vs {away_name} (A)  [{status}]")
    print(f"    Raw stats  — Home: fdo={d['home_fdo_pg']}  krm={d['home_krm_pg']}")
    print(f"               — Away: fdo={d['away_fdo_pg']}  krm={d['away_krm_pg']}")
    print(f"    Normalized — Home: fdo_n={d['home_fdo_n']:+.3f}  krm_n={d['home_krm_n']:+.3f}")
    print(f"               — Away: fdo_n={d['away_fdo_n']:+.3f}  krm_n={d['away_krm_n']:+.3f}")
    print(f"    Style score (FDO)    — Home={d['home_style_score']:+.4f}  Away={d['away_style_score']:+.4f}  (gate>{d['gate']})")
    print(f"    Vuln score  (KRM inv) — Home={d['home_vuln_score']:+.4f}  Away={d['away_vuln_score']:+.4f}")
    print(f"    H attacks A — gate={'PASS' if d['gate_passed_h'] else 'FAIL'}  "
          f"score={d['h_attacks_a_score']:.4f}  label={d['h_attacks_a_label']}  pts={d['pts_h']:.1f}")
    print(f"    A attacks H — gate={'PASS' if d['gate_passed_a'] else 'FAIL'}  "
          f"score={d['a_attacks_h_score']:.4f}  label={d['a_attacks_h_label']}  pts={d['pts_a']:.1f}")
    print(f"    Deltas      — home={result['home_delta']:+.3f}  away={result['away_delta']:+.3f}  "
          f"(inner_cap={d['inner_cap']}  outer_cap={d['outer_cap']})")
    # Overlap monitoring line
    if d['_2a_home_delta'] != 0.0 or result['home_delta'] != 0.0:
        same = d.get('_2a_same_direction')
        agree_str = ('AGREE — same direction' if same is True
                     else 'DIVERGE — opposite direction' if same is False
                     else 'n/a')
        print(f"    2A vs 2D    — 2A_home={d['_2a_home_delta']:+.3f}  2D_home={result['home_delta']:+.3f}  [{agree_str}]")


# =============================================================================
# Family C — Physical Carry & Forward Dominance
# run_metres_pg + errors_pg(inv) style  vs  mt_pg vulnerability
# =============================================================================

def compute_family_c(
    home_style: dict,
    away_style: dict,
    norms: dict,
    config: dict,
) -> dict:
    """
    Compute Family C (Physical Carry & Forward Dominance) for both directions.

    Style side — sustained physical carry dominance:
        run_metres_pg   weight 0.70  (volume of metres carried; primary signal)
        errors_pg       weight 0.30  (inverted — low errors = sustained pressure
                                      without self-interruption)

    Weights sum to 1.0. Auto-normalised by sum for safety.

    The errors_pg component prevents high-volume but sloppy teams from
    appearing dominant: a team that carries for big metres but turns the ball
    over frequently does not sustain physical pressure.

    Vulnerability side — susceptible to being physically worn down:
        mt_pg           weight 1.00  (missed tackles = defenders physically
                                      beaten in the contact zone)

    Overlap notes (documented):
        mt_pg:       shared with Family B vulnerability; different attacker
                     profile (run metres vs line breaks); combined cap limits
                     compounding.
        run_metres_pg: shares conceptual territory with the yardage bucket
                     (Bucket 1); yardage bucket currently returns 0 for run
                     metres in 2026 (data not loaded into team_stats); if both
                     are populated in future, monitor for compounding.
        errors_pg:   shared with Family A style (inverted); same stat, same
                     direction, different family context; combined cap mitigates.

    Gate, ladder, and caps mirror Family A and B exactly.
    """
    fc_cfg   = config.get('family_c', {})
    enabled  = fc_cfg.get('enabled', True)
    if not enabled:
        return _family_c_neutral()

    # --- style weights (auto-normalised by sum) ---
    rm_w      = float(fc_cfg.get('run_metres_weight',  0.70))
    err_st_w  = float(fc_cfg.get('errors_style_weight', 0.30))
    total_style_w = rm_w + err_st_w

    # --- vulnerability weights ---
    mt_vl_w      = float(fc_cfg.get('mt_vuln_weight', 1.00))
    total_vuln_w = mt_vl_w

    # --- gate threshold ---
    gate = float(fc_cfg.get('gate_threshold', 0.25))

    # --- point values per classification ---
    pts = {
        'strong':  float(fc_cfg.get('strong_pts',  3.0)),
        'average': float(fc_cfg.get('average_pts', 2.0)),
        'weak':    float(fc_cfg.get('weak_pts',    1.0)),
        'none':    0.0,
    }

    # --- inner / outer caps ---
    inner_cap = float(fc_cfg.get('inner_cap', 3.0))
    outer_cap = float(fc_cfg.get('outer_cap', 4.0))

    # --- pull norms ---
    rm_avg,  rm_std  = norms.get('run_metres_pg', (0.0, 1.0))
    err_avg, err_std = norms.get('errors_pg',     (0.0, 1.0))
    mt_avg,  mt_std  = norms.get('mt_pg',         (0.0, 1.0))

    # --- per-team composite scores ---
    def _scores(sd):
        rm_n  = _normalize_stat(sd.get('run_metres_pg'), rm_avg,  rm_std)
        err_n = _normalize_stat(sd.get('errors_pg'),     err_avg, err_std)
        mt_n  = _normalize_stat(sd.get('mt_pg'),         mt_avg,  mt_std)

        # style: high run metres + low errors (inverted)
        if total_style_w > 0:
            style = (rm_w * rm_n + err_st_w * (-err_n)) / total_style_w
        else:
            style = 0.0
        style = max(-1.0, min(1.0, style))

        # vulnerability: high missed tackles
        vuln = mt_n   # single stat, weight=1.0, already normalised
        vuln = max(-1.0, min(1.0, vuln))

        return rm_n, err_n, mt_n, style, vuln

    h_rm_n, h_err_n, h_mt_n, h_style, h_vuln = _scores(home_style or {})
    a_rm_n, a_err_n, a_mt_n, a_style, a_vuln = _scores(away_style or {})

    # --- home attacks away ---
    gate_h  = h_style > gate and a_vuln > gate
    h_att_a = h_style * a_vuln if gate_h else 0.0
    label_h = _classify_edge(h_att_a)

    # --- away attacks home ---
    gate_a  = a_style > gate and h_vuln > gate
    a_att_h = a_style * h_vuln if gate_a else 0.0
    label_a = _classify_edge(a_att_h)

    # Raw deltas
    raw_home = pts[label_h] - pts[label_a]
    raw_away = pts[label_a] - pts[label_h]

    # Inner cap
    home_delta = max(-inner_cap, min(inner_cap, raw_home))
    away_delta = max(-inner_cap, min(inner_cap, raw_away))

    # Outer cap
    home_delta = max(-outer_cap, min(outer_cap, home_delta))
    away_delta = max(-outer_cap, min(outer_cap, away_delta))

    debug = {
        'home_rm_n':   round(h_rm_n,  4), 'home_err_n':  round(h_err_n, 4),
        'home_mt_n':   round(h_mt_n,  4),
        'away_rm_n':   round(a_rm_n,  4), 'away_err_n':  round(a_err_n, 4),
        'away_mt_n':   round(a_mt_n,  4),
        'home_style_score':  round(h_style, 4),
        'home_vuln_score':   round(h_vuln,  4),
        'away_style_score':  round(a_style, 4),
        'away_vuln_score':   round(a_vuln,  4),
        'gate':              gate,
        'gate_passed_h':     gate_h,
        'gate_passed_a':     gate_a,
        'h_attacks_a_score': round(h_att_a, 4),
        'a_attacks_h_score': round(a_att_h, 4),
        'h_attacks_a_label': label_h,
        'a_attacks_h_label': label_a,
        'pts_h':             pts[label_h],
        'pts_a':             pts[label_a],
        'raw_home_delta':    round(raw_home, 3),
        'raw_away_delta':    round(raw_away, 3),
        'inner_cap':         inner_cap,
        'outer_cap':         outer_cap,
    }

    fires_c = home_delta != 0.0 or away_delta != 0.0
    return {
        'home_delta':   round(home_delta, 3),
        'away_delta':   round(away_delta, 3),
        'totals_delta': -1.5 if fires_c else 0.0,
        'debug':        debug,
    }


def _family_c_neutral() -> dict:
    return {
        'home_delta':   0.0,
        'away_delta':   0.0,
        'totals_delta': 0.0,
        'debug': {
            'home_rm_n': 0.0, 'home_err_n': 0.0, 'home_mt_n': 0.0,
            'away_rm_n': 0.0, 'away_err_n': 0.0, 'away_mt_n': 0.0,
            'home_style_score': 0.0, 'home_vuln_score': 0.0,
            'away_style_score': 0.0, 'away_vuln_score': 0.0,
            'gate': 0.25, 'gate_passed_h': False, 'gate_passed_a': False,
            'h_attacks_a_score': 0.0, 'a_attacks_h_score': 0.0,
            'h_attacks_a_label': 'none', 'a_attacks_h_label': 'none',
            'pts_h': 0.0, 'pts_a': 0.0,
            'raw_home_delta': 0.0, 'raw_away_delta': 0.0,
            'inner_cap': 3.0, 'outer_cap': 4.0,
        },
    }


def _print_family_c_debug(
    home_name: str,
    away_name: str,
    home_style: dict,
    away_style: dict,
    result: dict,
) -> None:
    """Always print Family C debug — fired or not."""
    d = result['debug']
    print(f"\n  [Tier2 Family C] {home_name} (H) vs {away_name} (A)")
    print(f"    Raw stats  — Home: rm={home_style.get('run_metres_pg')}, "
          f"err={home_style.get('errors_pg')}, mt={home_style.get('mt_pg')}")
    print(f"               — Away: rm={away_style.get('run_metres_pg')}, "
          f"err={away_style.get('errors_pg')}, mt={away_style.get('mt_pg')}")
    print(f"    Normalized — Home: rm_n={d['home_rm_n']:+.3f}  "
          f"err_n={d['home_err_n']:+.3f}  mt_n={d['home_mt_n']:+.3f}")
    print(f"               — Away: rm_n={d['away_rm_n']:+.3f}  "
          f"err_n={d['away_err_n']:+.3f}  mt_n={d['away_mt_n']:+.3f}")
    print(f"    Style score — Home={d['home_style_score']:+.4f}  Away={d['away_style_score']:+.4f}  "
          f"(gate>{d['gate']})")
    print(f"    Vuln score  — Home={d['home_vuln_score']:+.4f}  Away={d['away_vuln_score']:+.4f}")
    print(f"    H attacks A — gate={'PASS' if d['gate_passed_h'] else 'FAIL'}  "
          f"score={d['h_attacks_a_score']:.4f}  label={d['h_attacks_a_label']}  "
          f"pts={d['pts_h']:.1f}")
    print(f"    A attacks H — gate={'PASS' if d['gate_passed_a'] else 'FAIL'}  "
          f"score={d['a_attacks_h_score']:.4f}  label={d['a_attacks_h_label']}  "
          f"pts={d['pts_a']:.1f}")
    print(f"    Deltas      — home={result['home_delta']:+.3f}  away={result['away_delta']:+.3f}")


# =============================================================================
# Family B — LB+TB style vs MT+LBC vulnerability
# =============================================================================

def _normalize_stat(val: float, avg: float, std: float) -> float:
    """
    Clamp(z / 2, -1.0, +1.0) where z = (val - avg) / std.
    Returns 0.0 if std <= 0 or val is None.
    """
    if val is None or std is None or std <= 0:
        return 0.0
    z = (val - avg) / std
    return max(-1.0, min(1.0, z / 2.0))


def _classify_edge(matchup_score: float) -> str:
    """
    Returns 'strong', 'average', 'weak', or 'none' based on matchup_score.
    Thresholds: strong >= 0.40, average >= 0.20, weak >= 0.0625.
    """
    if matchup_score >= 0.40:
        return 'strong'
    elif matchup_score >= 0.20:
        return 'average'
    elif matchup_score >= 0.0625:
        return 'weak'
    return 'none'


def compute_family_b(
    home_style: dict,
    away_style: dict,
    norms: dict,
    config: dict,
) -> dict:
    """
    Compute Family B (LB+TB style vs MT+LBC vulnerability) for both directions.

    Returns a dict with:
        home_style_score     float   home team's LB+TB combined style score
        home_vuln_score      float   home team's MT+LBC combined vulnerability score
        away_style_score     float
        away_vuln_score      float
        h_attacks_a_score    float   home style × away vuln (if gate passes)
        a_attacks_h_score    float   away style × home vuln (if gate passes)
        h_attacks_a_label    str     'strong'/'average'/'weak'/'none'
        a_attacks_h_label    str
        home_delta           float   net expected-points adjustment for home
        away_delta           float   net expected-points adjustment for away
        gate_passed_h        bool
        gate_passed_a        bool
        debug                dict    full audit data
    """
    fb_cfg   = config.get('family_b', {})
    enabled  = fb_cfg.get('enabled', True)
    if not enabled:
        return _family_b_neutral()

    # --- weights ---
    lb_w  = float(fb_cfg.get('lb_weight',  0.55))
    tb_w  = float(fb_cfg.get('tb_weight',  0.45))
    mt_w  = float(fb_cfg.get('mt_weight',  0.60))
    lbc_w = float(fb_cfg.get('lbc_weight', 0.40))

    # --- gate threshold ---
    gate  = float(fb_cfg.get('gate_threshold', 0.25))

    # --- point values per classification ---
    pts   = {
        'strong':  float(fb_cfg.get('strong_pts',  3.0)),
        'average': float(fb_cfg.get('average_pts', 2.0)),
        'weak':    float(fb_cfg.get('weak_pts',    1.0)),
        'none':    0.0,
    }

    # --- inner / outer caps ---
    inner_cap = float(fb_cfg.get('inner_cap', 3.0))
    outer_cap = float(fb_cfg.get('outer_cap', 4.0))

    # --- pull norms ---
    lb_avg,  lb_std  = norms.get('lb_pg',  (0.0, 1.0))
    tb_avg,  tb_std  = norms.get('tb_pg',  (0.0, 1.0))
    mt_avg,  mt_std  = norms.get('mt_pg',  (0.0, 1.0))
    lbc_avg, lbc_std = norms.get('lbc_pg', (0.0, 1.0))

    # --- helper to compute scores for one team ---
    def _scores(style_dict):
        lb_n  = _normalize_stat(style_dict.get('lb_pg'),  lb_avg,  lb_std)
        tb_n  = _normalize_stat(style_dict.get('tb_pg'),  tb_avg,  tb_std)
        mt_n  = _normalize_stat(style_dict.get('mt_pg'),  mt_avg,  mt_std)
        lbc_n = _normalize_stat(style_dict.get('lbc_pg'), lbc_avg, lbc_std)
        style = lb_w * lb_n + tb_w * tb_n
        vuln  = mt_w * mt_n + lbc_w * lbc_n
        return lb_n, tb_n, mt_n, lbc_n, style, vuln

    h_lb_n, h_tb_n, h_mt_n, h_lbc_n, h_style, h_vuln = _scores(home_style or {})
    a_lb_n, a_tb_n, a_mt_n, a_lbc_n, a_style, a_vuln = _scores(away_style or {})

    # --- home attacks away ---
    gate_h    = h_style > gate and a_vuln > gate
    h_att_a   = h_style * a_vuln if gate_h else 0.0
    label_h   = _classify_edge(h_att_a)

    # --- away attacks home ---
    gate_a    = a_style > gate and h_vuln > gate
    a_att_h   = a_style * h_vuln if gate_a else 0.0
    label_a   = _classify_edge(a_att_h)

    # Raw deltas: home benefit = home style fires, away style fires hurts home
    raw_home = pts[label_h] - pts[label_a]
    raw_away = pts[label_a] - pts[label_h]

    # Inner cap
    home_delta = max(-inner_cap, min(inner_cap, raw_home))
    away_delta = max(-inner_cap, min(inner_cap, raw_away))

    # Outer cap
    home_delta = max(-outer_cap, min(outer_cap, home_delta))
    away_delta = max(-outer_cap, min(outer_cap, away_delta))

    debug = {
        'home_lb_n': round(h_lb_n, 4), 'home_tb_n': round(h_tb_n, 4),
        'home_mt_n': round(h_mt_n, 4), 'home_lbc_n': round(h_lbc_n, 4),
        'away_lb_n': round(a_lb_n, 4), 'away_tb_n': round(a_tb_n, 4),
        'away_mt_n': round(a_mt_n, 4), 'away_lbc_n': round(a_lbc_n, 4),
        'home_style_score':  round(h_style, 4),
        'home_vuln_score':   round(h_vuln,  4),
        'away_style_score':  round(a_style, 4),
        'away_vuln_score':   round(a_vuln,  4),
        'gate':              gate,
        'gate_passed_h':     gate_h,
        'gate_passed_a':     gate_a,
        'h_attacks_a_score': round(h_att_a, 4),
        'a_attacks_h_score': round(a_att_h, 4),
        'h_attacks_a_label': label_h,
        'a_attacks_h_label': label_a,
        'pts_h':             pts[label_h],
        'pts_a':             pts[label_a],
        'raw_home_delta':    round(raw_home, 3),
        'raw_away_delta':    round(raw_away, 3),
        'inner_cap':         inner_cap,
        'outer_cap':         outer_cap,
    }

    fires_b = home_delta != 0.0 or away_delta != 0.0
    return {
        'home_delta':   round(home_delta, 3),
        'away_delta':   round(away_delta, 3),
        'totals_delta': +1.5 if fires_b else 0.0,
        'debug':        debug,
    }


def _family_b_neutral() -> dict:
    return {
        'home_delta':   0.0,
        'away_delta':   0.0,
        'totals_delta': 0.0,
        'debug': {
            'home_lb_n': 0.0, 'home_tb_n': 0.0, 'home_mt_n': 0.0, 'home_lbc_n': 0.0,
            'away_lb_n': 0.0, 'away_tb_n': 0.0, 'away_mt_n': 0.0, 'away_lbc_n': 0.0,
            'home_style_score': 0.0, 'home_vuln_score': 0.0,
            'away_style_score': 0.0, 'away_vuln_score': 0.0,
            'gate': 0.25, 'gate_passed_h': False, 'gate_passed_a': False,
            'h_attacks_a_score': 0.0, 'a_attacks_h_score': 0.0,
            'h_attacks_a_label': 'none', 'a_attacks_h_label': 'none',
            'pts_h': 0.0, 'pts_a': 0.0,
            'raw_home_delta': 0.0, 'raw_away_delta': 0.0,
            'inner_cap': 3.0, 'outer_cap': 4.0,
        },
    }


def _print_family_b_debug(
    home_name: str,
    away_name: str,
    home_style: dict,
    away_style: dict,
    result: dict,
) -> None:
    """Always print Family B debug — fired or not."""
    d = result['debug']
    print(f"\n  [Tier2 Family B] {home_name} (H) vs {away_name} (A)")
    print(f"    Raw stats  — Home: lb={home_style.get('lb_pg')}, tb={home_style.get('tb_pg')}, "
          f"mt={home_style.get('mt_pg')}, lbc={home_style.get('lbc_pg')}")
    print(f"               — Away: lb={away_style.get('lb_pg')}, tb={away_style.get('tb_pg')}, "
          f"mt={away_style.get('mt_pg')}, lbc={away_style.get('lbc_pg')}")
    print(f"    Normalized — Home: lb_n={d['home_lb_n']:+.3f}  tb_n={d['home_tb_n']:+.3f}  "
          f"mt_n={d['home_mt_n']:+.3f}  lbc_n={d['home_lbc_n']:+.3f}")
    print(f"               — Away: lb_n={d['away_lb_n']:+.3f}  tb_n={d['away_tb_n']:+.3f}  "
          f"mt_n={d['away_mt_n']:+.3f}  lbc_n={d['away_lbc_n']:+.3f}")
    print(f"    Style score — Home={d['home_style_score']:+.4f}  Away={d['away_style_score']:+.4f}  "
          f"(gate>{d['gate']})")
    print(f"    Vuln score  — Home={d['home_vuln_score']:+.4f}  Away={d['away_vuln_score']:+.4f}")
    print(f"    H attacks A — gate={'PASS' if d['gate_passed_h'] else 'FAIL'}  "
          f"score={d['h_attacks_a_score']:.4f}  label={d['h_attacks_a_label']}  "
          f"pts={d['pts_h']:.1f}")
    print(f"    A attacks H — gate={'PASS' if d['gate_passed_a'] else 'FAIL'}  "
          f"score={d['a_attacks_h_score']:.4f}  label={d['a_attacks_h_label']}  "
          f"pts={d['pts_a']:.1f}")
    print(f"    Deltas      — home={result['home_delta']:+.3f}  away={result['away_delta']:+.3f}")


# =============================================================================
# Internal utilities
# =============================================================================

def _normalise(differential: float, norm_divisor: float) -> float:
    """
    Clamp (differential / norm_divisor) to [-1.0, +1.0].

    Used by every signal to convert a raw per-team differential into a
    bounded [-1, +1] score before weighting.

    Convention throughout Tier 2:
      differential = home_stat - away_stat  (unless reversed by design)
      positive result = home team has the advantage
      0.0            = neutral / no edge
      negative result = away team has the advantage

    The norm_divisor is the differential at which the signal saturates.
    Values should be calibrated from the distribution of actual NRL
    team-level per-game differentials once historical data is available.

    Args:
        differential:  home_stat - away_stat (or reversed for bad-is-bad stats)
        norm_divisor:  saturation threshold; must be positive

    Returns:
        float in [-1.0, +1.0]
    """
    if norm_divisor <= 0:
        return 0.0
    return max(-1.0, min(1.0, differential / norm_divisor))


def _has_sample(home_stats: dict, away_stats: dict, min_games: int) -> bool:
    """
    Return True if both teams meet the minimum games-played threshold.

    Signals are noisy for very small samples (e.g. round 1 or 2).
    Below min_games, all signals for this bucket return 0.0 (neutral)
    to avoid early-season noise dominating.

    Args:
        home_stats: team stats dict for the home team
        away_stats: team stats dict for the away team
        min_games:  minimum games played required (inclusive)

    Returns:
        bool — True if both teams have played at least min_games
    """
    home_gp = int(home_stats.get('games_played') or 0)
    away_gp = int(away_stats.get('games_played') or 0)
    return home_gp >= min_games and away_gp >= min_games


# =============================================================================
# Signal 1 — Run metres / post-contact metres
# =============================================================================

def compute_run_metres_signal(
    home_stats: dict,
    away_stats: dict,
    config: dict,
) -> float:
    """
    Signal 1 of 4: Run metres / post-contact metres advantage.

    PURPOSE
    -------
    Measures which team dominates the basic carry battle.

    Strong run metres:
      - build field position set by set
      - bend and stress defensive lines over time
      - improve kick launch points deep in the opposition half
      - wear down defensive structures physically

    Post-contact metres (metres after first contact) are an even sharper
    proxy for forward dominance — they capture not just initial gains but
    the ability to drive through the tackle, which directly creates better
    field position and faster play-the-ball situations.

    This is the strongest signal in the yardage bucket because it is the
    most direct, measurable expression of territorial dominance in NRL.

    FORMULA
    -------
    Two sub-signals are blended:
      a) run_metres_pg:          average run metres per game this season
      b) post_contact_metres_pg: metres after first contact per game (optional)

      run_m_component = _normalise(home_run_m - away_run_m, run_metres_norm)
      pcm_component   = _normalise(home_pcm - away_pcm, post_contact_metres_norm)

      signal = run_metres_only_weight * run_m_component
             + post_contact_metres_weight * pcm_component
      clamped to [-1.0, +1.0]

    If post_contact_metres_pg is unavailable, the signal falls back to
    run_metres_pg only (full weight on that component).

    NORMALISATION
    -------------
    Defaults (placeholder — recalibrate from NRL historical distributions):
      run_metres_norm:          100.0  (±100 m/game differential saturates)
      post_contact_metres_norm:  40.0  (±40 m/game differential saturates)

    DATA FIELDS EXPECTED IN team_stats
    ------------------------------------
    run_metres_pg:          float  average run metres per game this season
    post_contact_metres_pg: float  average post-contact metres per game (optional)
    games_played:           int    used for sample size check

    Args:
        home_stats: team stats dict for the home team
        away_stats: team stats dict for the away team
        config:     yardage sub-config (tier2_matchup.yardage section)

    Returns:
        float in [-1.0, +1.0]
          positive = home team has the carry/yardage edge
          0.0      = neutral (no data or no edge)
          negative = away team has the carry/yardage edge
    """
    min_games = int(config.get('min_sample_games', 3))
    if not _has_sample(home_stats, away_stats, min_games):
        logger.debug("run_metres_signal: insufficient sample — returning neutral")
        return 0.0

    run_metres_norm   = float(config.get('run_metres_norm', 100.0))
    post_contact_norm = float(config.get('post_contact_metres_norm', 40.0))
    run_metres_w      = float(config.get('run_metres_only_weight', 0.60))
    post_contact_w    = float(config.get('post_contact_metres_weight', 0.40))

    # --- sub-signal a: run metres per game ---
    home_run_m = float(home_stats.get('run_metres_pg') or 0.0)
    away_run_m = float(away_stats.get('run_metres_pg') or 0.0)

    if home_run_m == 0.0 and away_run_m == 0.0:
        # Data field not yet populated — return neutral.
        logger.debug("run_metres_signal: run_metres_pg not available — returning neutral")
        return 0.0

    run_m_component = _normalise(home_run_m - away_run_m, run_metres_norm)

    # --- sub-signal b: post-contact metres per game (optional enhancement) ---
    home_pcm = home_stats.get('post_contact_metres_pg')
    away_pcm = away_stats.get('post_contact_metres_pg')

    if home_pcm is not None and away_pcm is not None:
        pcm_component = _normalise(float(home_pcm) - float(away_pcm), post_contact_norm)
        signal = run_metres_w * run_m_component + post_contact_w * pcm_component
    else:
        # Post-contact data not yet available — fall back to run metres only.
        signal = run_m_component

    return max(-1.0, min(1.0, signal))


# =============================================================================
# Signal 2 — Completion / errors / discipline
# =============================================================================

def compute_completion_signal(
    home_stats: dict,
    away_stats: dict,
    config: dict,
) -> float:
    """
    Signal 2 of 4: Completion / errors / discipline advantage.

    PURPOSE
    -------
    Measures how well each team preserves field position and avoids
    self-inflicted territorial losses.

    Why this matters for yardage/territory:
      - poor completion wastes sets and hands possession back in bad spots
      - errors give opponents a free attacking set from their own end
      - poor discipline (penalties) gifts easy field position and set repeats
      - good teams hold possession, compound pressure, and deny reset opportunities

    FORMULA
    -------
    Three sub-signals blended:

      a) completion_rate: set completion rate (higher is better for that team)
         component = _normalise(home_cr - away_cr, completion_rate_norm)
         Expressed as a decimal: 0.75 = 75% completion.
         Positive differential = home team completes more sets.

      b) errors_pg: errors per game (lower is better — sign is REVERSED)
         component = _normalise(away_errors - home_errors, errors_pg_norm)
         Positive result = home team makes fewer errors.

      c) penalties_pg: penalties per game (lower is better — sign is REVERSED)
         component = _normalise(away_penalties - home_penalties, penalties_pg_norm)
         Positive result = home team concedes fewer penalties.

      signal = completion_rate_weight * completion_component
             + errors_weight          * errors_component
             + penalties_weight       * penalties_component
      clamped to [-1.0, +1.0]

    If any sub-signal's data is missing, the remaining sub-signals are
    re-normalised to their combined weight (no silent signal loss).

    NORMALISATION
    -------------
    Defaults (placeholder — recalibrate from NRL historical distributions):
      completion_rate_norm: 0.08  (±8 percentage-point differential saturates)
      errors_pg_norm:       3.0   (±3 errors/game differential saturates)
      penalties_pg_norm:    3.0   (±3 penalties/game differential saturates)

    DATA FIELDS EXPECTED IN team_stats
    ------------------------------------
    completion_rate:  float  set completion rate (0.0–1.0) this season
    errors_pg:        float  unforced errors per game this season
    penalties_pg:     float  penalties conceded per game this season
    games_played:     int    used for sample size check

    Args:
        home_stats: team stats dict for the home team
        away_stats: team stats dict for the away team
        config:     yardage sub-config (tier2_matchup.yardage section)

    Returns:
        float in [-1.0, +1.0]
          positive = home team has the completion/discipline edge
          0.0      = neutral
          negative = away team has the completion/discipline edge
    """
    min_games = int(config.get('min_sample_games', 3))
    if not _has_sample(home_stats, away_stats, min_games):
        logger.debug("completion_signal: insufficient sample — returning neutral")
        return 0.0

    cr_norm        = float(config.get('completion_rate_norm', 0.08))
    errors_norm    = float(config.get('errors_pg_norm', 3.0))
    penalties_norm = float(config.get('penalties_pg_norm', 3.0))
    cr_w           = float(config.get('completion_rate_weight', 0.50))
    errors_w       = float(config.get('errors_weight', 0.30))
    penalties_w    = float(config.get('penalties_weight', 0.20))

    components = []
    weights    = []

    # --- sub-signal a: completion rate (higher is better) ---
    home_cr = home_stats.get('completion_rate')
    away_cr = away_stats.get('completion_rate')
    if home_cr is not None and away_cr is not None:
        components.append(_normalise(float(home_cr) - float(away_cr), cr_norm))
        weights.append(cr_w)

    # --- sub-signal b: errors per game (fewer is better; sign reversed) ---
    home_err = home_stats.get('errors_pg')
    away_err = away_stats.get('errors_pg')
    if home_err is not None and away_err is not None:
        components.append(_normalise(float(away_err) - float(home_err), errors_norm))
        weights.append(errors_w)

    # --- sub-signal c: penalties per game (fewer is better; sign reversed) ---
    home_pen = home_stats.get('penalties_pg')
    away_pen = away_stats.get('penalties_pg')
    if home_pen is not None and away_pen is not None:
        components.append(_normalise(float(away_pen) - float(home_pen), penalties_norm))
        weights.append(penalties_w)

    if not components:
        logger.debug("completion_signal: no sub-signal data available — returning neutral")
        return 0.0

    # Re-normalise weights to sum to 1.0 if some sub-signals were absent.
    total_w = sum(weights)
    signal  = sum(c * w for c, w in zip(components, weights)) / total_w

    return max(-1.0, min(1.0, signal))


# =============================================================================
# Signal 3 — Kick metres / kicking control
# =============================================================================

def compute_kicking_signal(
    home_stats: dict,
    away_stats: dict,
    config: dict,
) -> float:
    """
    Signal 3 of 4: Kick metres / kicking control advantage.

    PURPOSE
    -------
    Measures territorial control through the kicking game.

    Why this matters for yardage/territory:
      - effective long kicking flips field position from defence to attack
      - strong exit kicking prevents opponents from gaining an easy platform
      - weak or inaccurate kicking hands opponents clean field position starts
      - total kick metres over a season is a robust proxy for territorial kicking value

    This is the third-ranked signal because kick metres correlates with
    territory won via the boot rather than the carry — both matter, but the
    carry is the more direct dominance proxy in NRL.

    FORMULA
    -------
    Single primary signal (additional kick quality metrics can be blended later):

      kick_metres_component = _normalise(home_km - away_km, kick_metres_norm)
      signal = kick_metres_component
      clamped to [-1.0, +1.0]

    FUTURE ENHANCEMENT
    ------------------
    Later versions can blend additional kick quality metrics if data becomes
    available from Stats Perform / Opta or similar:
      - effective kicks percentage
      - repeat set rate from kicking
      - 40/20 kicking (if tracked)
      - bomb and grubber effectiveness (scoring set-up rate)

    NORMALISATION
    -------------
    Defaults (placeholder — recalibrate from NRL historical distributions):
      kick_metres_norm: 150.0  (±150 kick metres/game differential saturates)

    DATA FIELDS EXPECTED IN team_stats
    ------------------------------------
    kick_metres_pg:  float  average kick metres per game this season
    games_played:    int    used for sample size check

    Args:
        home_stats: team stats dict for the home team
        away_stats: team stats dict for the away team
        config:     yardage sub-config (tier2_matchup.yardage section)

    Returns:
        float in [-1.0, +1.0]
          positive = home team has the kicking territorial edge
          0.0      = neutral
          negative = away team has the kicking territorial edge
    """
    min_games = int(config.get('min_sample_games', 3))
    if not _has_sample(home_stats, away_stats, min_games):
        logger.debug("kicking_signal: insufficient sample — returning neutral")
        return 0.0

    kick_metres_norm = float(config.get('kick_metres_norm', 150.0))

    home_km = home_stats.get('kick_metres_pg')
    away_km = away_stats.get('kick_metres_pg')

    if home_km is None or away_km is None:
        logger.debug("kicking_signal: kick_metres_pg not available — returning neutral")
        return 0.0

    signal = _normalise(float(home_km) - float(away_km), kick_metres_norm)
    return max(-1.0, min(1.0, signal))


# =============================================================================
# Signal 4 — Ruck speed / play-the-ball momentum
# =============================================================================

def compute_ruck_speed_signal(
    home_stats: dict,
    away_stats: dict,
    config: dict,
) -> float:
    """
    Signal 4 of 4: Ruck speed / play-the-ball momentum proxy.

    PURPOSE
    -------
    Measures which team creates faster play-the-ball situations and
    better shape opportunities out of the ruck.

    Why this matters for yardage/territory:
      - faster PTB moments give the attacking team more shape time
      - generate better pressure on defensive reloads
      - create line-break and offload opportunities
      - slow PTB can neutralise a team's attacking structure entirely

    This is the fourth-ranked signal because granular ruck-speed data
    is not readily available from standard public NRL sources, making it
    the noisiest of the four signals in early V1.

    CURRENT STATUS: PLACEHOLDER — returns 0.0 (neutral) until data is sourced
    --------------------------------------------------------------------------
    This signal requires PTB timing or ruck speed data that is not yet
    available from standard public NRL statistics.

    Until that data is sourced, this function returns 0.0 so it does not
    pollute the bucket score with invented values.

    INTENDED FORMULA (for future implementation)
    --------------------------------------------
      ruck_score_component = _normalise(home_ruck - away_ruck, ruck_speed_norm)
      signal = ruck_score_component
      clamped to [-1.0, +1.0]

    Where home_ruck and away_ruck are composite ruck speed scores.
    Positive = home team wins the PTB battle.

    POSSIBLE FUTURE PROXIES (when better data is available)
    -------------------------------------------------------
      - average PTB speed in seconds (from Stats Perform / Opta)
      - dominant carry count (if available)
      - tackle break rate (partial proxy for ruck dominance)
      - offloads per game (momentum proxy in expansive ruck play)

    DATA FIELDS EXPECTED IN team_stats (not yet standardised)
    ----------------------------------------------------------
    ruck_speed_score: float  composite ruck speed score (definition TBD)

    Args:
        home_stats: team stats dict for the home team
        away_stats: team stats dict for the away team
        config:     yardage sub-config (tier2_matchup.yardage section)

    Returns:
        float in [-1.0, +1.0]
          Returns 0.0 (neutral) until ruck speed data is sourced and validated.
    """
    min_games = int(config.get('min_sample_games', 3))
    if not _has_sample(home_stats, away_stats, min_games):
        logger.debug("ruck_speed_signal: insufficient sample — returning neutral")
        return 0.0

    ruck_norm  = float(config.get('ruck_speed_norm', 1.0))

    home_ruck = home_stats.get('ruck_speed_score')
    away_ruck = away_stats.get('ruck_speed_score')

    if home_ruck is None or away_ruck is None:
        # TODO: Replace with real PTB/ruck speed data once sourced.
        logger.debug("ruck_speed_signal: ruck_speed_score not available — returning neutral")
        return 0.0

    signal = _normalise(float(home_ruck) - float(away_ruck), ruck_norm)
    return max(-1.0, min(1.0, signal))


# =============================================================================
# Yardage bucket — combine signals into a bucket score
# =============================================================================

def compute_yardage_bucket(
    home_stats: dict,
    away_stats: dict,
    config: dict,
) -> dict:
    """
    Combine the four yardage signals into a single bucket score.

    SIGNAL WEIGHTS (from config — default philosophy)
    --------------------------------------------------
    1. Run metres / post-contact metres  weight=0.40  (biggest; most direct)
    2. Completion / errors / discipline  weight=0.30
    3. Kick metres / kicking control     weight=0.20
    4. Ruck speed / PTB momentum proxy   weight=0.10  (smallest; data caveat)

    Weights are re-normalised to sum to 1.0 automatically.
    If a signal returns 0.0 due to missing data, its weight is still included
    (the signal is treated as neutral, not absent).

    BUCKET SCORE
    ------------
    yardage_bucket_score in [-1.0, +1.0]
      positive = home team has the net yardage/territory edge
      0.0      = neutral (no meaningful edge either way)
      negative = away team has the net yardage/territory edge

    Args:
        home_stats: team stats dict for the home team
        away_stats: team stats dict for the away team
        config:     tier2_matchup section of tiers config
                    (yardage sub-section is extracted internally)

    Returns:
        dict with keys:
            run_metres_component  float  [-1, +1]  Signal 1 score
            completion_component  float  [-1, +1]  Signal 2 score
            kicking_component     float  [-1, +1]  Signal 3 score
            ruck_component        float  [-1, +1]  Signal 4 score
            yardage_bucket_score  float  [-1, +1]  weighted combination
    """
    yardage_cfg = config.get('yardage', {})

    run_metres_w = float(yardage_cfg.get('run_metres_weight', 0.40))
    completion_w = float(yardage_cfg.get('completion_weight', 0.30))
    kick_w       = float(yardage_cfg.get('kick_weight', 0.20))
    ruck_w       = float(yardage_cfg.get('ruck_weight', 0.10))

    run_m_signal = compute_run_metres_signal(home_stats, away_stats, yardage_cfg)
    comp_signal  = compute_completion_signal(home_stats, away_stats, yardage_cfg)
    kick_signal  = compute_kicking_signal(home_stats, away_stats, yardage_cfg)
    ruck_signal  = compute_ruck_speed_signal(home_stats, away_stats, yardage_cfg)

    total_weight = run_metres_w + completion_w + kick_w + ruck_w
    if total_weight <= 0:
        bucket_score = 0.0
    else:
        bucket_score = (
            run_metres_w * run_m_signal
            + completion_w * comp_signal
            + kick_w       * kick_signal
            + ruck_w       * ruck_signal
        ) / total_weight

    bucket_score = max(-1.0, min(1.0, bucket_score))

    logger.debug(
        "yardage_bucket: run_m=%.3f comp=%.3f kick=%.3f ruck=%.3f -> score=%.3f",
        run_m_signal, comp_signal, kick_signal, ruck_signal, bucket_score,
    )

    return {
        'run_metres_component': round(run_m_signal,  4),
        'completion_component': round(comp_signal,   4),
        'kicking_component':    round(kick_signal,   4),
        'ruck_component':       round(ruck_signal,   4),
        'yardage_bucket_score': round(bucket_score,  4),
    }


# =============================================================================
# Yardage bucket — translate bucket score into expected-points adjustments
# =============================================================================

def compute_yardage_adjustments(
    home_stats: dict,
    away_stats: dict,
    config: dict,
) -> dict:
    """
    Translate the yardage bucket score into capped expected-points adjustments.

    LOGIC
    -----
    The team with the yardage/territory edge is expected to:
      a) score more themselves  (better field position, cleaner set starts)
      b) concede less           (opponent works from worse field position)

    The adjustment therefore affects BOTH sides of the expected score:

      raw_home_delta =  bucket_score * max_points_swing
      raw_away_delta = -bucket_score * max_points_swing

    When bucket_score > 0 (home has the edge):
      home expected points increase, away expected points decrease.
      The margin widens toward home. The total is approximately unchanged.

    When bucket_score < 0 (away has the edge):
      home expected points decrease, away expected points increase.
      The margin narrows or reverses toward away.

    The symmetric structure means the yardage bucket is primarily a
    H2H / handicap signal, with near-zero net effect on the total.
    This matches the spec's stated market priority: H2H > handicap > totals.

    CAPS
    ----
    Two layers of capping:

    Inner cap (yardage-specific):
      raw delta is clamped to [-max_points_swing, +max_points_swing]
      controlled by tier2_matchup.yardage.max_points_swing in config

    Outer cap (tier-level):
      the inner-capped delta is further clamped to:
        [-max_home_points_delta, +max_home_points_delta]  for home
        [-max_away_points_delta, +max_away_points_delta]  for away
      controlled by tier2_matchup.max_*_points_delta in config

    In V1, max_points_swing (default 2.5) is smaller than the outer cap
    (default 4.0), so the inner cap is the binding constraint.
    Both remain in place so tuning one does not silently break the other.

    Args:
        home_stats: team stats dict for the home team
        away_stats: team stats dict for the away team
        config:     tier2_matchup section of tiers config

    Returns:
        dict with keys:
            run_metres_component                    float   Signal 1 score
            completion_component                    float   Signal 2 score
            kicking_component                       float   Signal 3 score
            ruck_component                          float   Signal 4 score
            yardage_bucket_score                    float   combined bucket score
            raw_home_delta                          float   before caps
            raw_away_delta                          float   before caps
            capped_yardage_adjustment_home_points   float   after both caps
            capped_yardage_adjustment_away_points   float   after both caps
    """
    yardage_cfg = config.get('yardage', {})

    if not yardage_cfg.get('enabled', True):
        logger.debug("yardage bucket: disabled in config — returning neutral")
        return {
            'run_metres_component':  0.0,
            'completion_component':  0.0,
            'kicking_component':     0.0,
            'ruck_component':        0.0,
            'yardage_bucket_score':  0.0,
            'raw_home_delta':        0.0,
            'raw_away_delta':        0.0,
            'capped_yardage_adjustment_home_points': 0.0,
            'capped_yardage_adjustment_away_points': 0.0,
        }

    max_swing      = float(yardage_cfg.get('max_points_swing', 2.5))
    outer_home_cap = float(config.get('max_home_points_delta', 4.0))
    outer_away_cap = float(config.get('max_away_points_delta', 4.0))

    bucket = compute_yardage_bucket(home_stats, away_stats, config)
    score  = bucket['yardage_bucket_score']

    # Raw symmetric deltas: positive bucket_score = home benefits.
    raw_home_delta =  score * max_swing
    raw_away_delta = -score * max_swing

    # Inner cap: yardage-specific swing limit.
    home_delta = max(-max_swing, min(max_swing, raw_home_delta))
    away_delta = max(-max_swing, min(max_swing, raw_away_delta))

    # Outer cap: tier-level safety net.
    home_delta = max(-outer_home_cap, min(outer_home_cap, home_delta))
    away_delta = max(-outer_away_cap, min(outer_away_cap, away_delta))

    logger.debug(
        "yardage_adjustments: score=%.3f max_swing=%.1f "
        "raw=(%.2f, %.2f) capped=(%.2f, %.2f)",
        score, max_swing,
        raw_home_delta, raw_away_delta,
        home_delta, away_delta,
    )

    return {
        **bucket,
        'raw_home_delta':  round(raw_home_delta, 3),
        'raw_away_delta':  round(raw_away_delta, 3),
        'capped_yardage_adjustment_home_points': round(home_delta, 3),
        'capped_yardage_adjustment_away_points': round(away_delta, 3),
    }


# =============================================================================
# Main entry point
# =============================================================================

def compute_matchup_adjustments(match: dict, context: dict, config: dict, conn=None) -> list:
    """
    Compute Tier 2 matchup adjustments for a single match.

    Runs all active Tier 2 buckets in sequence and returns a list of
    adjustment dicts. Stubs for unimplemented buckets are included as
    comments so the sequence is clear and easy to activate later.

    CURRENTLY ACTIVE
    ----------------
    Bucket 1: Yardage / territory / ruck-momentum

    NOT YET IMPLEMENTED
    -------------------
    Bucket 2: Defensive system / discipline
    Bucket 3: Attacking shape / scoring-actions
    Overlay:  Coach H2H
    Overlay:  Team-vs-team history overlay

    ARGUMENT STRUCTURE
    ------------------
    match dict is expected to contain:
        home_stats      dict  team_stats row for the home team
        away_stats      dict  team_stats row for the away team
        home_team_id    int
        away_team_id    int
        match_id        int

    context dict is the match_context row.
    Not used by the yardage bucket; reserved for later buckets.

    config dict is the full tiers config.
    The tier2_matchup section is extracted internally.

    Args:
        match:   match dict with home_stats and away_stats embedded
        context: match_context dict
        config:  full tiers config dict

    Returns:
        list of adjustment dicts (may be empty if all buckets are disabled
        or return neutral adjustments)

        Each adjustment dict contains:
            tier_number              int
            tier_name                str
            adjustment_code          str
            adjustment_description   str
            home_points_delta        float   post-combined-cap value
            away_points_delta        float   post-combined-cap value
            margin_delta             float   home_delta - away_delta
            total_delta              float   home_delta + away_delta
            _debug                   dict    full signal-level audit breakdown
            _tier2_scale_applied     float   scaling factor (only present when < 1.0)

    COMBINED OUTER CAP
    ------------------
    After all families have contributed, the raw combined home/away totals
    are checked against tier2_matchup.max_home_points_delta and
    tier2_matchup.max_away_points_delta.  If either total exceeds its cap,
    a proportional scaling factor is applied to ALL adjustment entries so
    that relative family contributions are preserved and the combined total
    hits exactly the cap.  The factor is stamped as _tier2_scale_applied
    on every entry in the list when it fires.
    """
    tier2_cfg = config.get('tier2_matchup', {})

    if not tier2_cfg.get('enabled', True):
        logger.debug("tier2_matchup: disabled in config — returning no adjustments")
        return []

    home_stats = match.get('home_stats', {})
    away_stats = match.get('away_stats', {})

    adjustments = []

    # ------------------------------------------------------------------
    # Bucket 1: Yardage / territory / ruck-momentum
    # ------------------------------------------------------------------
    yardage_cfg = tier2_cfg.get('yardage', {})
    if yardage_cfg.get('enabled', True):
        yardage = compute_yardage_adjustments(home_stats, away_stats, tier2_cfg)

        home_delta = yardage['capped_yardage_adjustment_home_points']
        away_delta = yardage['capped_yardage_adjustment_away_points']

        adjustments.append({
            'tier_number':  _TIER,
            'tier_name':    _TIER_NAME,
            'adjustment_code': 'yardage_territory',
            'adjustment_description': (
                'Yardage / territory / ruck-momentum matchup bucket. '
                'Adjusts both expected scores based on which team is '
                'more likely to win the field-position and momentum '
                'battle. Signals: run metres, completion/discipline, '
                'kick metres, ruck speed.'
            ),
            'home_points_delta': round(home_delta, 3),
            'away_points_delta': round(away_delta, 3),
            'margin_delta':      round(home_delta - away_delta, 3),
            'total_delta':       round(home_delta + away_delta, 3),
            '_debug':            yardage,
        })

        logger.debug(
            "tier2 yardage_territory: home_delta=%.2f away_delta=%.2f "
            "margin_delta=%.2f total_delta=%.2f",
            home_delta, away_delta,
            home_delta - away_delta, home_delta + away_delta,
        )

    # ------------------------------------------------------------------
    # Family A: Territory & Control (completion/kick style vs errors/penalties vuln)
    # ------------------------------------------------------------------
    fa_cfg = tier2_cfg.get('family_a', {})
    if fa_cfg.get('enabled', True) and conn is not None:
        from db.queries import get_team_style_stats, get_style_league_norms

        match_date  = match.get('match_date') or match.get('match_date_str', '')
        season      = match.get('season') or (int(str(match_date)[:4]) if match_date else None)
        home_tid    = match.get('home_team_id')
        away_tid    = match.get('away_team_id')
        home_name   = match.get('home_team', str(home_tid))
        away_name   = match.get('away_team', str(away_tid))

        home_style_a = get_team_style_stats(conn, home_tid, season, match_date) or {}
        away_style_a = get_team_style_stats(conn, away_tid, season, match_date) or {}

        as_of_a = home_style_a.get('as_of_date') or away_style_a.get('as_of_date') or match_date
        norms_a = get_style_league_norms(conn, season, as_of_a)

        fa_result = compute_family_a(home_style_a, away_style_a, norms_a, tier2_cfg)
        _print_family_a_debug(home_name, away_name, home_style_a, away_style_a, fa_result)

        h_delta_a = fa_result['home_delta']
        a_delta_a = fa_result['away_delta']

        if h_delta_a != 0.0 or a_delta_a != 0.0:
            d = fa_result['debug']
            desc = (
                f"Family A: {home_name} ({d['h_attacks_a_label']}) attacks "
                f"{away_name} ({d['a_attacks_h_label']})"
            )
            adjustments.append({
                'tier_number':  _TIER,
                'tier_name':    _TIER_NAME,
                'adjustment_code': 'family_a_territory_control',
                'adjustment_description': desc,
                'home_points_delta': round(h_delta_a, 3),
                'away_points_delta': round(a_delta_a, 3),
                'margin_delta':      round(h_delta_a - a_delta_a, 3),
                'total_delta':       round(h_delta_a + a_delta_a, 3),
                '_debug':            fa_result['debug'],
            })
            logger.debug(
                "tier2 family_a: home_delta=%.2f away_delta=%.2f", h_delta_a, a_delta_a
            )

    # ------------------------------------------------------------------
    # Family C: Physical Carry & Forward Dominance
    #           run_metres_pg + errors_pg(inv) style vs mt_pg vulnerability
    # ------------------------------------------------------------------
    fc_cfg = tier2_cfg.get('family_c', {})
    if fc_cfg.get('enabled', True) and conn is not None:
        from db.queries import get_team_style_stats, get_style_league_norms

        match_date  = match.get('match_date') or match.get('match_date_str', '')
        season      = match.get('season') or (int(str(match_date)[:4]) if match_date else None)
        home_tid    = match.get('home_team_id')
        away_tid    = match.get('away_team_id')
        home_name   = match.get('home_team', str(home_tid))
        away_name   = match.get('away_team', str(away_tid))

        home_style_c = get_team_style_stats(conn, home_tid, season, match_date) or {}
        away_style_c = get_team_style_stats(conn, away_tid, season, match_date) or {}

        as_of_c = home_style_c.get('as_of_date') or away_style_c.get('as_of_date') or match_date
        norms_c = get_style_league_norms(conn, season, as_of_c)

        fc_result = compute_family_c(home_style_c, away_style_c, norms_c, tier2_cfg)
        _print_family_c_debug(home_name, away_name, home_style_c, away_style_c, fc_result)

        h_delta_c = fc_result['home_delta']
        a_delta_c = fc_result['away_delta']

        if h_delta_c != 0.0 or a_delta_c != 0.0:
            d = fc_result['debug']
            desc = (
                f"Family C: {home_name} ({d['h_attacks_a_label']}) attacks "
                f"{away_name} ({d['a_attacks_h_label']})"
            )
            adjustments.append({
                'tier_number':  _TIER,
                'tier_name':    _TIER_NAME,
                'adjustment_code': 'family_c_physical_carry',
                'adjustment_description': desc,
                'home_points_delta': round(h_delta_c, 3),
                'away_points_delta': round(a_delta_c, 3),
                'margin_delta':      round(h_delta_c - a_delta_c, 3),
                'total_delta':       round(h_delta_c + a_delta_c, 3),
                '_debug':            fc_result['debug'],
            })
            logger.debug(
                "tier2 family_c: home_delta=%.2f away_delta=%.2f", h_delta_c, a_delta_c
            )

    # ------------------------------------------------------------------
    # Family D: Kicking Pressure & Exit Stress  [SOFT LAUNCH]
    #           fdo_pg style vs krm_pg (inverted) vulnerability
    # Conservative caps: inner=2.0 / outer=2.5 (mature = 3.0 / 4.0)
    # ------------------------------------------------------------------
    fd_cfg = tier2_cfg.get('family_d', {})
    if fd_cfg.get('enabled', True) and conn is not None:
        from db.queries import get_team_style_stats, get_style_league_norms

        match_date  = match.get('match_date') or match.get('match_date_str', '')
        season      = match.get('season') or (int(str(match_date)[:4]) if match_date else None)
        home_tid    = match.get('home_team_id')
        away_tid    = match.get('away_team_id')
        home_name   = match.get('home_team', str(home_tid))
        away_name   = match.get('away_team', str(away_tid))

        home_style_d = get_team_style_stats(conn, home_tid, season, match_date) or {}
        away_style_d = get_team_style_stats(conn, away_tid, season, match_date) or {}

        as_of_d = home_style_d.get('as_of_date') or away_style_d.get('as_of_date') or match_date
        norms_d = get_style_league_norms(conn, season, as_of_d)

        # Pass 2A deltas for overlap monitoring only — no effect on 2D calculation.
        fa_home_for_d = next(
            (a['home_points_delta'] for a in adjustments
             if a.get('adjustment_code') == 'family_a_territory_control'), 0.0
        )
        fa_away_for_d = next(
            (a['away_points_delta'] for a in adjustments
             if a.get('adjustment_code') == 'family_a_territory_control'), 0.0
        )

        fd_result = compute_family_d(
            home_style_d, away_style_d, norms_d, tier2_cfg,
            home_2a_delta=fa_home_for_d, away_2a_delta=fa_away_for_d,
        )
        _print_family_d_debug(home_name, away_name, home_style_d, away_style_d, fd_result)

        h_delta_d = fd_result['home_delta']
        a_delta_d = fd_result['away_delta']

        if h_delta_d != 0.0 or a_delta_d != 0.0:
            d = fd_result['debug']
            desc = (
                f"Family D [trial]: {home_name} ({d['h_attacks_a_label']}) attacks "
                f"{away_name} ({d['a_attacks_h_label']})  "
                f"[caps inner={d['inner_cap']} outer={d['outer_cap']}]"
            )
            adjustments.append({
                'tier_number':  _TIER,
                'tier_name':    _TIER_NAME,
                'adjustment_code': 'family_d_kicking_pressure',
                'adjustment_description': desc,
                'home_points_delta': round(h_delta_d, 3),
                'away_points_delta': round(a_delta_d, 3),
                'margin_delta':      round(h_delta_d - a_delta_d, 3),
                'total_delta':       round(h_delta_d + a_delta_d, 3),
                '_debug':            fd_result['debug'],
                '_experimental':     True,
            })
            logger.debug(
                "tier2 family_d [trial]: home_delta=%.2f away_delta=%.2f", h_delta_d, a_delta_d
            )

    # ------------------------------------------------------------------
    # Family B: LB+TB style vs MT+LBC vulnerability
    # ------------------------------------------------------------------
    fb_cfg = tier2_cfg.get('family_b', {})
    if fb_cfg.get('enabled', True) and conn is not None:
        from db.queries import get_team_style_stats, get_style_league_norms

        match_date  = match.get('match_date') or match.get('match_date_str', '')
        season      = match.get('season') or (int(str(match_date)[:4]) if match_date else None)
        home_tid    = match.get('home_team_id')
        away_tid    = match.get('away_team_id')
        home_name   = match.get('home_team', str(home_tid))
        away_name   = match.get('away_team', str(away_tid))

        home_style = get_team_style_stats(conn, home_tid, season, match_date) or {}
        away_style = get_team_style_stats(conn, away_tid, season, match_date) or {}

        as_of = home_style.get('as_of_date') or away_style.get('as_of_date') or match_date
        norms = get_style_league_norms(conn, season, as_of)

        fb_result = compute_family_b(home_style, away_style, norms, tier2_cfg)
        _print_family_b_debug(home_name, away_name, home_style, away_style, fb_result)

        h_delta = fb_result['home_delta']
        a_delta = fb_result['away_delta']

        if h_delta != 0.0 or a_delta != 0.0:
            d = fb_result['debug']
            desc = (
                f"Family B: {home_name} ({d['h_attacks_a_label']}) attacks "
                f"{away_name} ({d['a_attacks_h_label']})"
            )
            adjustments.append({
                'tier_number':  _TIER,
                'tier_name':    _TIER_NAME,
                'adjustment_code': 'family_b_style_vuln',
                'adjustment_description': desc,
                'home_points_delta': round(h_delta, 3),
                'away_points_delta': round(a_delta, 3),
                'margin_delta':      round(h_delta - a_delta, 3),
                'total_delta':       round(h_delta + a_delta, 3),
                '_debug':            fb_result['debug'],
            })
            logger.debug(
                "tier2 family_b: home_delta=%.2f away_delta=%.2f", h_delta, a_delta
            )

    # ------------------------------------------------------------------
    # Bucket 2: Defensive system / discipline
    # NOT YET IMPLEMENTED — stub placeholder
    # ------------------------------------------------------------------
    # defensive_cfg = tier2_cfg.get('defensive_system', {})
    # if defensive_cfg.get('enabled', False):
    #     ... compute_defensive_system_adjustments(home_stats, away_stats, tier2_cfg)

    # ------------------------------------------------------------------
    # Bucket 3: Attacking shape / scoring-actions
    # NOT YET IMPLEMENTED — stub placeholder
    # ------------------------------------------------------------------
    # attacking_cfg = tier2_cfg.get('attacking_shape', {})
    # if attacking_cfg.get('enabled', False):
    #     ... compute_attacking_shape_adjustments(home_stats, away_stats, tier2_cfg)

    # ------------------------------------------------------------------
    # Overlay: Coach H2H
    # NOT YET IMPLEMENTED — requires coach master data + H2H records
    # ------------------------------------------------------------------
    # coach_h2h_cfg = tier2_cfg.get('coach_h2h', {})
    # if coach_h2h_cfg.get('enabled', False):
    #     ... compute_coach_h2h_adjustments(match, tier2_cfg)

    # ------------------------------------------------------------------
    # Overlay: Team-vs-team history
    # NOT YET IMPLEMENTED — requires historical matchup records
    # ------------------------------------------------------------------
    # h2h_cfg = tier2_cfg.get('team_vs_team_history', {})
    # if h2h_cfg.get('enabled', False):
    #     ... compute_team_history_adjustments(match, tier2_cfg)

    # ------------------------------------------------------------------
    # Combined Tier 2 outer cap
    # ------------------------------------------------------------------
    # Each family has its own inner/outer cap that bounds its individual
    # contribution.  When multiple families fire in the same game, their
    # contributions are additive and can together exceed the tier-level
    # ceiling.  This final pass enforces a hard cap on the combined total.
    #
    # Method: proportional scaling.
    #   - Find the scale factor needed so that neither |home_total| nor
    #     |away_total| exceeds its respective tier cap.
    #   - Apply that same factor to every adjustment in the list so that
    #     the relative contributions of each family are preserved.
    #   - Stamp _tier2_scale_applied on every entry when scaling fires,
    #     so the audit trail is always complete.
    #
    # Config keys used:
    #   tier2_matchup.max_home_points_delta  (default 4.0)
    #   tier2_matchup.max_away_points_delta  (default 4.0)
    # ------------------------------------------------------------------
    if adjustments:
        tier2_home_cap = float(tier2_cfg.get('max_home_points_delta', 4.0))
        tier2_away_cap = float(tier2_cfg.get('max_away_points_delta', 4.0))

        raw_home_total = sum(a['home_points_delta'] for a in adjustments)
        raw_away_total = sum(a['away_points_delta'] for a in adjustments)

        scale = 1.0
        if abs(raw_home_total) > tier2_home_cap and raw_home_total != 0.0:
            scale = min(scale, tier2_home_cap / abs(raw_home_total))
        if abs(raw_away_total) > tier2_away_cap and raw_away_total != 0.0:
            scale = min(scale, tier2_away_cap / abs(raw_away_total))

        if scale < 1.0:
            logger.debug(
                "tier2 combined cap: raw_home=%.2f raw_away=%.2f "
                "cap_home=%.1f cap_away=%.1f scale=%.4f",
                raw_home_total, raw_away_total,
                tier2_home_cap, tier2_away_cap, scale,
            )
            for adj in adjustments:
                adj['home_points_delta'] = round(adj['home_points_delta'] * scale, 3)
                adj['away_points_delta'] = round(adj['away_points_delta'] * scale, 3)
                adj['margin_delta']      = round(
                    adj['home_points_delta'] - adj['away_points_delta'], 3)
                adj['total_delta']       = round(
                    adj['home_points_delta'] + adj['away_points_delta'], 3)
                adj['_tier2_scale_applied'] = round(scale, 4)

    return adjustments
