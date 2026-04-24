# pricing/tier5_injury.py
# =============================================================================
# Tier 5 — Injury & Suspension layer
# =============================================================================
#
# Converts team-level absence burden (injuries AND suspensions) into two
# adjustments. Both absence types are treated identically in the pricing
# math — a suspended halfback suppresses the model the same way an injured
# one does.  The absence_type field in injury_reports distinguishes them for
# reporting and filtering, but does not change the point weights below.
#
#   handicap_delta
#       Captures the relative strength shift between the two teams.
#       Formula: clamp(away_absence_pts - home_absence_pts, -3.0, +3.0)
#       Positive = home favoured (away has more key players absent).
#       Negative = away favoured (home has more key players absent).
#
#   totals_delta
#       Captures the aggregate scoring suppression from absences on both sides.
#       Formula: -0.3 per combined absence point above threshold (default 4.0).
#       Capped at -3.0. Both teams losing key players reduces expected scoring.
#
# V1 absence points are supplied per-team from the injury_reports table
# (loaded via scripts/load_injury_round.py).
# Role-based scale (illustrative):
#   Elite spine (halfback, hooker, fullback): 3.0 pts
#   Key playmaker / five-eighth:              2.0 pts
#   Quality back-rower / prop:                1.0 pt
#   Depth player:                             0.5 pts
# =============================================================================

import logging

logger = logging.getLogger(__name__)


def compute_injury_adjustments(
    home_injury_pts: float,
    away_injury_pts: float,
    config: dict,
) -> dict:
    """
    Compute Tier 5 absence adjustments (injuries and suspensions combined).

    Both absence types contribute identically to the pricing math.
    Callers should sum all absence points regardless of absence_type before
    passing them in.

    Args:
        home_injury_pts: total absence burden for home team (sum of role-based pts)
        away_injury_pts: total absence burden for away team
        config: tier5_injury section of tiers.yaml

    Returns dict with:
        handicap_delta   float  positive = home favoured
        totals_delta     float  always <= 0
        _debug           dict
    """
    hcap_clamp     = float(config.get('handicap_clamp', 3.0))
    totals_cap     = float(config.get('totals_cap', -3.0))
    totals_thresh  = float(config.get('totals_threshold', 4.0))
    totals_rate    = float(config.get('totals_rate', -0.3))

    # Handicap: relative injury differential
    raw_hcap       = away_injury_pts - home_injury_pts
    handicap_delta = max(-hcap_clamp, min(hcap_clamp, raw_hcap))

    # Totals: combined burden above threshold suppresses scoring
    combined       = home_injury_pts + away_injury_pts
    excess         = max(0.0, combined - totals_thresh)
    raw_totals     = totals_rate * excess
    totals_delta   = max(totals_cap, raw_totals)

    logger.debug(
        "T5 injury: home_pts=%.2f away_pts=%.2f raw_hcap=%.2f hcap_delta=%.2f "
        "combined=%.2f excess=%.2f totals_delta=%.2f",
        home_injury_pts, away_injury_pts, raw_hcap, handicap_delta,
        combined, excess, totals_delta,
    )

    return {
        'handicap_delta': round(handicap_delta, 3),
        'totals_delta':   round(totals_delta, 3),
        '_debug': {
            'home_injury_pts': home_injury_pts,
            'away_injury_pts': away_injury_pts,
            'raw_hcap':        round(raw_hcap, 3),
            'combined_pts':    round(combined, 3),
            'excess_above_threshold': round(excess, 3),
            'raw_totals':      round(raw_totals, 3),
        },
    }
