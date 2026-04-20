# pricing/tier6_referee.py
# Tier 6 — Referee layer.
#
# Captures officiating tendencies that affect game flow and scoring.
# Primary effect on totals, secondary on handicap, minor on H2H.
# Examples: penalty count tendency, six-again frequency, stop-start profile.
#
# Returns a handicap_delta (margin adjustment) and totals_delta.
#
# Bucket definitions:
#   whistle_heavy  — High penalty/six-again rate; stop-start profile; suppresses scoring
#   flow_heavy     — Low penalty rate; fast play-the-ball; boosts scoring
#   neutral        — Near league average on all measures

import sqlite3
from typing import Optional


def compute_referee_adjustments(
    home_bucket_edge: float,
    away_bucket_edge: float,
    bucket: str,
    config: dict,
) -> dict:
    """
    Tier 6 referee adjustments.

    handicap_delta:
        home_bucket_edge minus away_bucket_edge, multiplied by shrink factor,
        clamped to ±handicap_clamp (default ±1.5).
        Positive = home team benefits from this ref's tendencies.

    totals_delta:
        whistle_heavy → -2.0  (stop-start suppresses scoring)
        flow_heavy    → +2.0  (fast game boosts scoring)
        neutral       →  0.0
        Clamped to ±totals_clamp (default ±2.0).

    Args:
        home_bucket_edge:  avg signed margin for the home team under this bucket
        away_bucket_edge:  avg signed margin for the away team under this bucket
        bucket:            referee bucket ('whistle_heavy' | 'flow_heavy' | 'neutral')
        config:            tier6_referee config dict from tiers.yaml

    Returns:
        dict with:
            handicap_delta    float    margin adjustment (positive = home advantage)
            totals_delta      float    total-points adjustment
            bucket            str      referee bucket used
            home_bucket_edge  float    passed-through for logging
            away_bucket_edge  float    passed-through for logging
            _debug            dict     intermediate values for auditability
    """
    SHRINK = float(config.get('shrink', 1.0))
    hcap_clamp  = float(config.get('handicap_clamp',  1.5))
    tot_clamp   = float(config.get('totals_clamp',    2.0))

    raw_hcap = (home_bucket_edge - away_bucket_edge) * SHRINK
    handicap_delta = max(-hcap_clamp, min(hcap_clamp, raw_hcap))

    base_totals = {
        'whistle_heavy': float(config.get('totals_whistle_heavy', -2.0)),
        'flow_heavy':    float(config.get('totals_flow_heavy',     2.0)),
        'neutral':       float(config.get('totals_neutral',        0.0)),
    }
    raw_totals = base_totals.get(bucket, 0.0)
    totals_delta = max(-tot_clamp, min(tot_clamp, raw_totals))

    return {
        'handicap_delta':    round(handicap_delta, 3),
        'totals_delta':      round(totals_delta, 3),
        'bucket':            bucket,
        'home_bucket_edge':  home_bucket_edge,
        'away_bucket_edge':  away_bucket_edge,
        '_debug': {
            'raw_hcap':            round(raw_hcap, 3),
            'shrink':              SHRINK,
            'hcap_clamp':          hcap_clamp,
            'totals_clamp':        tot_clamp,
            'base_totals_lookup':  raw_totals,
        },
    }


def get_ref_context(
    conn: sqlite3.Connection,
    match_id: int,
    home_team_id: int,
    away_team_id: int,
    season: int,
) -> Optional[dict]:
    """
    Look up the referee assignment, profile, and team bucket stats for a match.

    Queries:
        weekly_ref_assignments → referee_profiles → team_ref_bucket_stats

    Args:
        conn:         active DB connection
        match_id:     canonical match identifier
        home_team_id: home team for bucket edge lookup
        away_team_id: away team for bucket edge lookup
        season:       season for bucket stats lookup

    Returns:
        dict with:
            referee_id       int
            referee_name     str
            bucket           str   ('whistle_heavy' | 'flow_heavy' | 'neutral')
            home_bucket_edge float
            away_bucket_edge float
        or None if no referee assignment exists for this match.
    """
    from db.queries import get_ref_assignment, get_referee_profile, get_team_ref_bucket_edge

    assignment = get_ref_assignment(conn, match_id)
    if assignment is None:
        return None

    referee_id   = assignment['referee_id']
    referee_name = assignment['referee_name']

    profile = get_referee_profile(conn, referee_id)
    if profile is None:
        # Referee exists but has no profile — treat as neutral
        bucket = 'neutral'
    else:
        bucket = profile['bucket']

    home_edge = get_team_ref_bucket_edge(conn, home_team_id, bucket, season)
    away_edge = get_team_ref_bucket_edge(conn, away_team_id, bucket, season)

    return {
        'referee_id':        referee_id,
        'referee_name':      referee_name,
        'bucket':            bucket,
        'home_bucket_edge':  home_edge,
        'away_bucket_edge':  away_edge,
    }
