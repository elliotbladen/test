# pricing/tier3_situational.py
# =============================================================================
# Tier 3 — Situational layer
# =============================================================================
#
# OVERVIEW
# --------
# Tier 3 captures schedule and travel context that is independent of team
# quality or style.  It answers:
#   "Is either team physically or logistically disadvantaged for this game?"
#
# ACTIVE COMPONENTS
# -----------------
#   3A: Rest / Turnaround
#       Classifies each team's rest as short / normal / long / bye.
#       Looks up the margin delta from a 4×4 rest matrix (antisymmetric).
#       Positive delta = home team benefits.
#
#   3B: Travel / Fatigue
#       Computes haversine distance from each team's home base to the venue.
#       delta = (away_travel_km - home_travel_km) / 1000 × scale
#       Positive = home advantage.
#
#   3C: Compound rule
#       If a team is on short rest AND travelled > 500 km to the venue,
#       they receive an additional -0.5 pt penalty.
#
# OUTPUT FORMAT
# -------------
# compute_situational_adjustments() returns a dict:
#   home_delta         float   net Tier 3 pts adjustment for home team
#   away_delta         float   net Tier 3 pts adjustment for away team
#   debug              dict    per-component breakdown for auditing
#
# Each named component (3A, 3B, 3C) also returns a dict with the same
# home_delta / away_delta / debug shape — pattern mirrors Tier 2 families.
# =============================================================================

import math
import logging

logger = logging.getLogger(__name__)

_TIER      = 3
_TIER_NAME = 'tier3_situational'

# ---------------------------------------------------------------------------
# 3A helpers
# ---------------------------------------------------------------------------

def _classify_rest(days: int | None, cfg: dict) -> str | None:
    """
    Classify rest days into short / normal / long / bye.
    Returns None if days is None (no prior match found in the season —
    treated as neutral by the rest matrix).
    """
    if days is None:
        return None
    short_max  = int(cfg.get('short_max_days',  6))
    normal_max = int(cfg.get('normal_max_days', 9))
    long_max   = int(cfg.get('long_max_days',  13))
    if days <= short_max:
        return 'short'
    if days <= normal_max:
        return 'normal'
    if days <= long_max:
        return 'long'
    return 'bye'


def _rest_matrix_value(home_class: str | None, away_class: str | None, cfg: dict) -> float:
    """Look up margin delta for (home_class, away_class) pair."""
    if home_class is None or away_class is None:
        return 0.0
    key   = f"{home_class}_vs_{away_class}"
    matrix = cfg.get('matrix', {})
    return float(matrix.get(key, 0.0))


def compute_rest_adjustment(
    home_rest_days: int | None,
    away_rest_days: int | None,
    config: dict,
) -> dict:
    """
    Compute 3A rest adjustment.

    Args:
        home_rest_days: days since home team's last game (None = no prior game)
        away_rest_days: days since away team's last game (None = no prior game)
        config:         tier3_situational config dict

    Returns dict with:
        home_delta      float   margin adjustment (+ve = home advantage)
        away_delta      float   always 0.0 (3A affects margin, not totals)
        debug           dict
    """
    rest_cfg = config.get('rest', {})
    enabled  = rest_cfg.get('enabled', True)

    if not enabled:
        return {'home_delta': 0.0, 'away_delta': 0.0, 'debug': {'enabled': False}}

    home_class = _classify_rest(home_rest_days, rest_cfg)
    away_class = _classify_rest(away_rest_days, rest_cfg)

    raw_delta = _rest_matrix_value(home_class, away_class, rest_cfg)

    cap       = float(rest_cfg.get('cap', 2.0))
    capped    = max(-cap, min(cap, raw_delta))

    debug = {
        'home_rest_days':  home_rest_days,
        'away_rest_days':  away_rest_days,
        'home_class':      home_class,
        'away_class':      away_class,
        'raw_delta':       raw_delta,
        'cap':             cap,
        'capped_delta':    capped,
    }

    return {
        'home_delta': capped,
        'away_delta': 0.0,
        'debug':      debug,
    }


# ---------------------------------------------------------------------------
# 3B helpers
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in km between two lat/lng points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def compute_travel_adjustment(
    home_travel_km: float | None,
    away_travel_km: float | None,
    config: dict,
) -> dict:
    """
    Compute 3B travel adjustment.

    delta = (away_travel_km - home_travel_km) / 1000 × scale
    Positive = home advantage (away team travelled more).

    Returns 0.0 if either travel distance is missing.

    Args:
        home_travel_km: km from home team base to venue (None if missing)
        away_travel_km: km from away team base to venue (None if missing)
        config:         tier3_situational config dict

    Returns dict with home_delta, away_delta, debug.
    """
    travel_cfg = config.get('travel', {})
    enabled    = travel_cfg.get('enabled', True)

    if not enabled or home_travel_km is None or away_travel_km is None:
        return {
            'home_delta': 0.0,
            'away_delta': 0.0,
            'debug': {
                'enabled':        enabled,
                'home_travel_km': home_travel_km,
                'away_travel_km': away_travel_km,
                'reason':         'missing geo data' if (home_travel_km is None or away_travel_km is None) else 'disabled',
            },
        }

    scale = float(travel_cfg.get('scale', 1.1))
    cap   = float(travel_cfg.get('cap',   2.0))

    raw_delta = (away_travel_km - home_travel_km) / 1000.0 * scale
    capped    = max(-cap, min(cap, raw_delta))

    debug = {
        'home_travel_km': round(home_travel_km, 1),
        'away_travel_km': round(away_travel_km, 1),
        'net_km':         round(away_travel_km - home_travel_km, 1),
        'scale':          scale,
        'raw_delta':      round(raw_delta, 4),
        'cap':            cap,
        'capped_delta':   round(capped, 4),
    }

    return {
        'home_delta': round(capped, 4),
        'away_delta': 0.0,
        'debug':      debug,
    }


# ---------------------------------------------------------------------------
# 3C: Compound rule
# ---------------------------------------------------------------------------

def compute_compound_adjustment(
    home_rest_class: str | None,
    away_rest_class: str | None,
    home_travel_km: float | None,
    away_travel_km: float | None,
    config: dict,
) -> dict:
    """
    Compute 3C compound rule:
        short rest AND travel > threshold → additional pts penalty to that team.

    Each team is evaluated independently. Both can fire simultaneously.

    Args:
        home_rest_class: 'short'|'normal'|'long'|'bye'|None
        away_rest_class: same
        home_travel_km:  float or None
        away_travel_km:  float or None
        config:          tier3_situational config dict

    Returns dict with home_delta, away_delta, debug.
    """
    comp_cfg  = config.get('compound', {})
    enabled   = comp_cfg.get('enabled', True)

    if not enabled:
        return {'home_delta': 0.0, 'away_delta': 0.0, 'debug': {'enabled': False}}

    threshold = float(comp_cfg.get('threshold_km', 500.0))
    delta_pts = float(comp_cfg.get('delta',        -0.5))
    cap       = float(comp_cfg.get('cap',           0.5))

    home_fires = (
        home_rest_class == 'short'
        and home_travel_km is not None
        and home_travel_km > threshold
    )
    away_fires = (
        away_rest_class == 'short'
        and away_travel_km is not None
        and away_travel_km > threshold
    )

    raw_home = delta_pts if home_fires else 0.0
    raw_away = delta_pts if away_fires else 0.0

    # Per-team cap (the cap is a magnitude bound, not directional)
    home_capped = max(-cap, min(cap, raw_home))
    away_capped = max(-cap, min(cap, raw_away))

    debug = {
        'threshold_km':  threshold,
        'delta_pts':     delta_pts,
        'home_fires':    home_fires,
        'away_fires':    away_fires,
        'home_rest_class': home_rest_class,
        'away_rest_class': away_rest_class,
        'home_travel_km':  round(home_travel_km, 1) if home_travel_km is not None else None,
        'away_travel_km':  round(away_travel_km, 1) if away_travel_km is not None else None,
    }

    return {
        'home_delta': home_capped,
        'away_delta': away_capped,
        'debug':      debug,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_situational_adjustments(context: dict, config: dict) -> dict:
    """
    Compute all Tier 3 situational adjustments for one game.

    Args:
        context: dict from get_situational_context() containing:
                   home_rest_days, away_rest_days,
                   home_travel_km, away_travel_km
        config:  full tiers config dict (contains 'tier3_situational' key)

    Returns dict with:
        home_delta       float   net Tier 3 pts adjustment (pre-cap)
        away_delta       float
        home_delta_capped float  after outer cap
        away_delta_capped float
        scale_applied    float | None   scaling factor if cap was hit, else None
        debug            dict    full per-component breakdown
    """
    t3_cfg = config.get('tier3_situational', {})

    if not t3_cfg.get('enabled', True):
        return {
            'home_delta': 0.0, 'away_delta': 0.0,
            'home_delta_capped': 0.0, 'away_delta_capped': 0.0,
            'scale_applied': None,
            'debug': {'enabled': False},
        }

    home_rest_days = context.get('home_rest_days')
    away_rest_days = context.get('away_rest_days')
    home_travel_km = context.get('home_travel_km')
    away_travel_km = context.get('away_travel_km')

    # Derive rest classes (needed by 3A and 3C)
    rest_cfg       = t3_cfg.get('rest', {})
    home_rest_class = _classify_rest(home_rest_days, rest_cfg)
    away_rest_class = _classify_rest(away_rest_days, rest_cfg)

    # --- 3A ---
    r3a = compute_rest_adjustment(home_rest_days, away_rest_days, t3_cfg)

    # --- 3B ---
    r3b = compute_travel_adjustment(home_travel_km, away_travel_km, t3_cfg)

    # --- 3C ---
    r3c = compute_compound_adjustment(
        home_rest_class, away_rest_class,
        home_travel_km, away_travel_km,
        t3_cfg,
    )

    raw_home = r3a['home_delta'] + r3b['home_delta'] + r3c['home_delta']
    raw_away = r3a['away_delta'] + r3b['away_delta'] + r3c['away_delta']

    # --- Tier 3 totals delta ---
    # 3A: both teams short rest → -1.5; one team short → -0.75.
    # 3B: combined travel km > 1000 → -1.0.
    # 3C: compound stress fires for either team → -0.5.
    # Combined cap: ±2.0.
    t3_totals = 0.0
    both_short = (home_rest_class == 'short' and away_rest_class == 'short')
    one_short  = ((home_rest_class == 'short') != (away_rest_class == 'short'))
    if both_short:
        t3_totals += -1.5
    elif one_short:
        t3_totals += -0.75

    combined_travel = (home_travel_km or 0.0) + (away_travel_km or 0.0)
    if home_travel_km is not None and away_travel_km is not None and combined_travel > 1000.0:
        t3_totals += -1.0

    r3c_debug = r3c['debug']
    if r3c_debug.get('home_fires') or r3c_debug.get('away_fires'):
        t3_totals += -0.5

    t3_totals_cap = 2.0
    t3_totals = max(-t3_totals_cap, min(t3_totals_cap, t3_totals))

    # --- Combined outer cap ---
    cap_h = float(t3_cfg.get('max_home_points_delta', 3.0))
    cap_a = float(t3_cfg.get('max_away_points_delta', 3.0))
    scale = 1.0
    if abs(raw_home) > cap_h and raw_home != 0.0:
        scale = min(scale, cap_h / abs(raw_home))
    if abs(raw_away) > cap_a and raw_away != 0.0:
        scale = min(scale, cap_a / abs(raw_away))

    home_capped = round(raw_home * scale, 3)
    away_capped = round(raw_away * scale, 3)

    debug = {
        'home_rest_days':   home_rest_days,
        'away_rest_days':   away_rest_days,
        'home_rest_class':  home_rest_class,
        'away_rest_class':  away_rest_class,
        'home_travel_km':   round(home_travel_km, 1) if home_travel_km is not None else None,
        'away_travel_km':   round(away_travel_km, 1) if away_travel_km is not None else None,
        '3a': r3a['debug'],
        '3b': r3b['debug'],
        '3c': r3c['debug'],
        'raw_home':         round(raw_home, 4),
        'raw_away':         round(raw_away, 4),
        'outer_cap_h':      cap_h,
        'outer_cap_a':      cap_a,
        'scale':            round(scale, 4),
    }

    return {
        'home_delta':        round(raw_home, 4),
        'away_delta':        round(raw_away, 4),
        'home_delta_capped': home_capped,
        'away_delta_capped': away_capped,
        'scale_applied':     round(scale, 4) if scale < 1.0 else None,
        '3a_home_delta':     r3a['home_delta'],
        '3b_home_delta':     r3b['home_delta'],
        '3c_home_delta':     r3c['home_delta'],
        '3c_away_delta':     r3c['away_delta'],
        'totals_delta':      round(t3_totals, 3),
        'debug':             debug,
    }
