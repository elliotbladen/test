# pricing/tier4_venue.py
# Tier 4 — Venue layer
#
# Adjusts handicap (margin) and totals based on:
#   1. Each team's historical signed-margin performance at this specific venue
#      (home AND away games combined — captures genuine venue affinity / aversion).
#   2. The venue's overall scoring tendency vs league average.
#
# Returns point-based deltas — not probability tweaks.
# Keep clamps conservative in V1: venue data is noisy, especially early season.

import logging
logger = logging.getLogger(__name__)


def compute_venue_adjustments(
    home_team_id: int,
    away_team_id: int,
    venue_id: int,
    home_venue_edge: float,
    away_venue_edge: float,
    venue_total_edge: float,
    config: dict,
) -> dict:
    """
    Tier 4 venue adjustments.

    handicap_delta = clamp(home_venue_edge - away_venue_edge, -handicap_clamp, +handicap_clamp)
    totals_delta   = clamp(venue_total_edge, -totals_clamp, +totals_clamp)

    Args:
        home_team_id:     home team canonical id
        away_team_id:     away team canonical id
        venue_id:         venue canonical id
        home_venue_edge:  home team's avg signed margin at this venue (0.0 if < 3 games)
        away_venue_edge:  away team's avg signed margin at this venue (0.0 if < 3 games)
        venue_total_edge: venue avg_total - league_avg (0.0 if not seeded)
        config:           tier4_venue section from tiers.yaml

    Returns:
        dict with:
            handicap_delta   float   margin adjustment (positive = home favoured more)
            totals_delta     float   total points adjustment (positive = higher-scoring venue)
            _debug           dict    raw intermediate values for logging
    """
    hcap_clamp   = float(config.get('handicap_clamp', 1.5))
    totals_clamp = float(config.get('totals_clamp', 2.0))

    raw_delta      = home_venue_edge - away_venue_edge
    handicap_delta = max(-hcap_clamp, min(hcap_clamp, raw_delta))
    totals_delta   = max(-totals_clamp, min(totals_clamp, venue_total_edge))

    logger.debug(
        "T4 venue: home_edge=%.2f away_edge=%.2f raw_delta=%.2f "
        "hcap_delta=%.2f venue_total_edge=%.2f totals_delta=%.2f",
        home_venue_edge, away_venue_edge, raw_delta,
        handicap_delta, venue_total_edge, totals_delta,
    )

    return {
        'handicap_delta':   round(handicap_delta, 3),
        'totals_delta':     round(totals_delta, 3),
        '_debug': {
            'home_venue_edge':  home_venue_edge,
            'away_venue_edge':  away_venue_edge,
            'raw_delta':        round(raw_delta, 3),
            'venue_total_edge': venue_total_edge,
        },
    }
