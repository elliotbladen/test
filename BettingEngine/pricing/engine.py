# pricing/engine.py
# =============================================================================
# Main pricing engine orchestrator
# =============================================================================
#
# OVERVIEW
# --------
# run_pricing() drives the full 7-tier pricing sequence for a single match.
# derive_final_prices() converts final expected home/away points into market
# prices (H2H odds, handicap line, total line).
#
# TIER SEQUENCE
# -------------
# Each tier receives the current state (expected home/away points) and returns
# an adjustment dict. Adjustments are accumulated and logged separately so
# the contribution of each tier is always auditable.
#
#   Tier 1 — Baseline         (implemented)
#   Tier 2 — Matchup style    (stub — not yet implemented)
#   Tier 3 — Situational      (stub — not yet implemented)
#   Tier 4 — Venue            (stub — not yet implemented)
#   Tier 5 — Injury           (stub — not yet implemented)
#   Tier 6 — Referee          (stub — not yet implemented)
#   Tier 7 — Environment      (stub — not yet implemented)
#
# PRICE DERIVATION
# ----------------
# All three markets (H2H, handicap, total) are derived from the same pair of
# expected-points numbers. This keeps them internally consistent: if expected
# home points rise, home H2H shortens, home handicap improves, and the total
# increases automatically.
#
# The conversion from expected margin to win probability uses a normal
# distribution model calibrated to historical NRL margin variance.
# See derive_final_prices() and _win_probability_from_margin() for details.
#
# =============================================================================

import logging
import math
from datetime import datetime
from typing import Optional

from pricing.tier1_baseline import compute_baseline
from pricing.tier2_matchup import compute_matchup_adjustments
from pricing.tier3_situational import compute_situational_adjustments
from pricing.tier4_venue import compute_venue_adjustments
from pricing.tier5_injury import compute_injury_adjustments
from pricing.tier6_referee import compute_referee_adjustments
from pricing.tier7_environment import compute_environment_adjustments

from db.queries import (
    get_match_by_id,
    get_team_stats,
    get_latest_snapshots_for_match,
    get_match_context,
)
from validation.pre_run import validate_run_inputs, validate_pricing_output
from decision.signals import generate_signals

logger = logging.getLogger(__name__)


# =============================================================================
# Price derivation
# =============================================================================

def derive_final_prices(
    final_home_points: float,
    final_away_points: float,
    config: dict,
) -> dict:
    """
    Convert final expected home/away points into market prices.

    This is the single source of truth for all derived prices.
    All three markets are produced from the same expected-points input,
    keeping them internally consistent.

    HANDICAP LINE CONVENTION
    ------------------------
    The fair_handicap_line is expressed from the home team's perspective.
    A negative value means the home team gives points (is favoured).
    A positive value means the home team receives points (is the underdog).

    Examples:
        expected_home = 28.0, expected_away = 20.0
        margin = +8.0  (home favoured by 8)
        fair_handicap_line = -8.0  (home -8, away +8)

        expected_home = 20.0, expected_away = 27.0
        margin = -7.0  (away favoured by 7)
        fair_handicap_line = +7.0  (home +7, away -7)

    WIN PROBABILITY MODEL
    ---------------------
    The margin of an NRL match is modelled as normally distributed:
        actual_margin ~ N(expected_margin, margin_std_dev²)

    P(home wins) = P(actual_margin > 0) = Φ(expected_margin / margin_std_dev)

    margin_std_dev is configured in tiers.yaml and should be calibrated
    from historical data. A higher value reflects more uncertainty
    (flatter probability distribution).

    Args:
        final_home_points: final expected home team score (after all tier adjustments)
        final_away_points: final expected away team score (after all tier adjustments)
        config: tier1_baseline section of tiers.yaml (needs 'margin_std_dev')

    Returns:
        dict with keys:
            final_margin           float   positive = home favoured
            final_total            float
            home_win_probability   float   in (0, 1)
            away_win_probability   float   in (0, 1)
            fair_home_odds         float   decimal, >= 1.001
            fair_away_odds         float   decimal, >= 1.001
            fair_handicap_line     float   from home perspective (negative = home gives points)
            fair_total_line        float
    """
    margin = final_home_points - final_away_points
    total  = final_home_points + final_away_points

    std_dev = float(config.get('margin_std_dev', 12.0))
    home_win_prob = _win_probability_from_margin(margin, std_dev)
    away_win_prob = 1.0 - home_win_prob

    # Guard against probabilities so extreme that decimal odds become nonsensical.
    # 0.001 → max fair odds of 1000.0; reasonable ceiling for pre-match markets.
    home_p = max(0.001, min(0.999, home_win_prob))
    away_p = max(0.001, min(0.999, away_win_prob))

    fair_home_odds = 1.0 / home_p
    fair_away_odds = 1.0 / away_p

    # Handicap line: negative means home gives points (home is favoured).
    fair_handicap_line = -margin

    # Total line is the expected total — over/under is centred on this.
    fair_total_line = total

    logger.debug(
        "derive_final_prices: home=%.2f away=%.2f margin=%.2f total=%.2f "
        "P(home)=%.4f -> %.3f / %.3f",
        final_home_points, final_away_points,
        margin, total, home_win_prob,
        fair_home_odds, fair_away_odds,
    )

    return {
        'final_margin':           round(margin, 2),
        'final_total':            round(total, 2),
        'home_win_probability':   round(home_win_prob, 4),
        'away_win_probability':   round(away_win_prob, 4),
        'fair_home_odds':         round(fair_home_odds, 3),
        'fair_away_odds':         round(fair_away_odds, 3),
        'fair_handicap_line':     round(fair_handicap_line, 1),
        'fair_total_line':        round(fair_total_line, 1),
    }


def _win_probability_from_margin(expected_margin: float, std_dev: float) -> float:
    """
    Convert expected margin to home win probability using a normal distribution.

    The actual margin of a match is modelled as:
        actual_margin ~ N(expected_margin, std_dev²)

    P(home wins) = P(actual_margin > 0)
                 = Φ(expected_margin / std_dev)

    where Φ is the standard normal CDF, computed via math.erf (stdlib, no deps).

    Calibration:
        std_dev should be estimated from the standard deviation of
        (actual_margin - expected_margin) across a large historical sample.
        For NRL, a reasonable starting estimate is 10-14 points.

        A smaller std_dev makes the model more confident (steeper odds).
        A larger std_dev makes the model less confident (odds closer to evens).

    Example (std_dev = 12.0):
        expected_margin = +12.0  ->  P(home wins) ≈ 0.841
        expected_margin =   0.0  ->  P(home wins) = 0.500
        expected_margin = -12.0  ->  P(home wins) ≈ 0.159

    Args:
        expected_margin: positive = home team expected to win
        std_dev: standard deviation of NRL margin distribution

    Returns:
        float in (0, 1)
    """
    if std_dev <= 0:
        raise ValueError(f"std_dev must be positive, got {std_dev}")
    z = expected_margin / std_dev
    # Standard normal CDF via math.erf (exact, no external dependencies)
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# =============================================================================
# Main orchestration
# =============================================================================

def run_pricing(
    conn,
    match_id: int,
    config: dict,
    model_version: str = 'v1',
    bankroll: float = 0.0,
    match_date: Optional[str] = None,
) -> dict:
    """
    Execute the 7-tier pricing sequence for a single match.

    Thin orchestration only: loads data, calls each tier in sequence,
    accumulates point adjustments, derives final prices, generates signals.
    Does NOT write to the database — the caller (run.py) handles logging.

    RETURN DICT
    -----------
    Always returns a dict. On early exit (validation failed), most price
    and signal fields are absent — check 'run_status' and 'can_proceed' first.

    Common fields (always present):
        match_id            int
        model_version       str
        run_timestamp       str     ISO UTC datetime
        run_status          str     'success' | 'partial' | 'failed'
        can_proceed         bool
        run_validation      RunValidation
        match               dict | None
        home_stats          dict | None
        away_stats          dict | None
        snapshots           list
        match_context       dict | None
        adjustments         list    all tier adjustment dicts (empty on failure)
        signals             list    signal dicts from generate_signals()

    Additional fields when run_status is not 'failed':
        baseline_home_points  float
        baseline_away_points  float
        baseline_margin       float
        baseline_total        float
        final_home_points     float
        final_away_points     float
        prices                dict    from derive_final_prices()
        pricing_validation    RunValidation

    TIER EXECUTION
    --------------
    Tier 1:   runs fully (implemented).
    Tier 2:   yardage bucket runs fully (implemented); other buckets skip safely.
    Tier 3–7: stubs — caught with NotImplementedError, skipped with a debug log.
              When each tier is implemented, it activates automatically.

    RUN STATUS
    ----------
    'success'  — validation passed and pricing output was clean
    'partial'  — validation passed but pricing output has non-blocking warnings
    'failed'   — pre-run validation found blocking errors; no pricing was run

    Args:
        conn:         active database connection
        match_id:     canonical match identifier
        config:       merged config dict (must contain 'tier1_baseline' key,
                      or be the tier1_baseline section directly)
        model_version: version string for audit trail
        bankroll:     current bankroll for Kelly stake sizing (0.0 → no sizing)
        match_date:   ISO date string for point-in-time stats lookup.
                      If None, falls back to match.match_date from the DB.

    Returns:
        dict — see field descriptions above
    """
    run_timestamp = datetime.utcnow().isoformat()

    # -------------------------------------------------------------------------
    # 1. Load data from DB
    # -------------------------------------------------------------------------
    match       = get_match_by_id(conn, match_id)
    as_of       = match_date or (match or {}).get('match_date')

    if match:
        home_stats = get_team_stats(
            conn, match['home_team_id'], match['season'], as_of
        )
        away_stats = get_team_stats(
            conn, match['away_team_id'], match['season'], as_of
        )
    else:
        home_stats = None
        away_stats = None

    snapshots     = get_latest_snapshots_for_match(conn, match_id) if match else []
    match_context = get_match_context(conn, match_id) if match else None

    logger.debug(
        "run_pricing: match_id=%d home_team_id=%s away_team_id=%s "
        "home_stats=%s away_stats=%s snapshots=%d",
        match_id,
        (match or {}).get('home_team_id'),
        (match or {}).get('away_team_id'),
        'ok' if home_stats else 'MISSING',
        'ok' if away_stats else 'MISSING',
        len(snapshots),
    )

    # -------------------------------------------------------------------------
    # 2. Pre-run validation
    # -------------------------------------------------------------------------
    t1_cfg = config.get('tier1_baseline', config)

    run_validation = validate_run_inputs(
        conn, match_id, home_stats, away_stats, snapshots, t1_cfg, as_of
    )

    if not run_validation.can_proceed:
        logger.warning(
            "run_pricing: match_id=%d blocked — errors: %s",
            match_id,
            [e['flag'] for e in run_validation.errors],
        )
        return {
            'match_id':        match_id,
            'model_version':   model_version,
            'run_timestamp':   run_timestamp,
            'run_status':      'failed',
            'can_proceed':     False,
            'run_validation':  run_validation,
            'match':           match,
            'home_stats':      home_stats,
            'away_stats':      away_stats,
            'snapshots':       snapshots,
            'match_context':   match_context,
            'adjustments':     [],
            'signals':         [],
        }

    # -------------------------------------------------------------------------
    # 3. Tier 1 — Baseline
    # -------------------------------------------------------------------------
    # Build a minimal venue dict from the match row (Tier 1 receives it but
    # does not use it — it is passed through for downstream tiers).
    venue = {
        'venue_id':   (match or {}).get('venue_id'),
        'venue_name': (match or {}).get('venue_name'),
        'city':       (match or {}).get('venue_city'),
    }

    baseline = compute_baseline(home_stats, away_stats, venue, t1_cfg)
    baseline_home = baseline['baseline_home_points']
    baseline_away = baseline['baseline_away_points']

    logger.debug(
        "tier1 baseline: home=%.2f away=%.2f margin=%.2f total=%.2f",
        baseline_home, baseline_away,
        baseline['baseline_margin'], baseline['baseline_total'],
    )

    # Running totals — each tier adds its deltas here.
    current_home = baseline_home
    current_away = baseline_away

    # Adjustment list — one dict per tier adjustment (written to model_adjustments).
    # Tier 1 itself is the starting point, not a delta; record it for completeness
    # so the full audit chain is preserved.
    adjustments = [
        {
            'tier_number':  1,
            'tier_name':    'tier1_baseline',
            'adjustment_code': 'baseline',
            'adjustment_description': (
                'Tier 1 baseline expected points. '
                'Combines ELO, team strength, attack/defence ratings, '
                'recent form, and home advantage.'
            ),
            'home_points_delta': 0.0,
            'away_points_delta': 0.0,
            'margin_delta':      0.0,
            'total_delta':       0.0,
            'applied_flag':      1,
            '_debug':            baseline.get('_debug', {}),
        }
    ]

    # -------------------------------------------------------------------------
    # 4. Tier 2 — Matchup adjustments (yardage bucket implemented)
    # -------------------------------------------------------------------------
    match_with_stats = {
        **(match or {}),
        'home_stats': home_stats,
        'away_stats': away_stats,
    }
    tier2_adjs = compute_matchup_adjustments(
        match_with_stats, match_context or {}, config, conn=conn
    )
    for adj in tier2_adjs:
        current_home += float(adj.get('home_points_delta', 0.0))
        current_away += float(adj.get('away_points_delta', 0.0))
    adjustments.extend(tier2_adjs)

    logger.debug(
        "tier2 done: %d adjustment(s); running totals home=%.2f away=%.2f",
        len(tier2_adjs), current_home, current_away,
    )

    # -------------------------------------------------------------------------
    # 5–9. Tiers 3–7 — stubs; skipped safely until implemented
    # -------------------------------------------------------------------------
    # Each call is wrapped so that NotImplementedError from the stub is caught
    # and execution continues. When a tier module is implemented, its adjustments
    # are automatically applied without any change needed here.

    def _try_tier(tier_num, tier_name, call, *args):
        """Call a tier function; catch NotImplementedError and skip gracefully."""
        nonlocal current_home, current_away
        try:
            tier_adjs = call(*args)
            for adj in tier_adjs:
                current_home += float(adj.get('home_points_delta', 0.0))
                current_away += float(adj.get('away_points_delta', 0.0))
            adjustments.extend(tier_adjs)
            logger.debug("tier%d %s: %d adjustment(s)", tier_num, tier_name, len(tier_adjs))
        except NotImplementedError:
            logger.debug("tier%d %s: stub — skipped", tier_num, tier_name)

    _try_tier(3, 'situational',  compute_situational_adjustments,
              match_with_stats, match_context or {}, config)

    _try_tier(4, 'venue',        compute_venue_adjustments,
              match_with_stats, venue, match_context or {}, config)

    _try_tier(5, 'injury',       compute_injury_adjustments,
              match_with_stats, [], config)   # injury_reports not yet loaded

    _try_tier(6, 'referee',      compute_referee_adjustments,
              match_with_stats, {}, config)   # referee stats dict not yet loaded

    _try_tier(7, 'environment',  compute_environment_adjustments,
              match_with_stats, match_context or {}, config)

    # -------------------------------------------------------------------------
    # 10. Derive final prices
    # -------------------------------------------------------------------------
    prices = derive_final_prices(current_home, current_away, t1_cfg)

    logger.debug(
        "final prices: home=%.2f away=%.2f | H2H %.3f / %.3f | "
        "handicap %.1f | total %.1f",
        current_home, current_away,
        prices['fair_home_odds'], prices['fair_away_odds'],
        prices['fair_handicap_line'], prices['fair_total_line'],
    )

    # -------------------------------------------------------------------------
    # 11. Validate pricing output
    # -------------------------------------------------------------------------
    pricing_validation = validate_pricing_output(
        baseline_home, baseline_away, current_home, current_away
    )

    run_status = 'partial' if pricing_validation.warnings else 'success'

    if pricing_validation.warnings:
        logger.warning(
            "run_pricing: match_id=%d pricing output warnings: %s",
            match_id,
            [w['flag'] for w in pricing_validation.warnings],
        )

    # -------------------------------------------------------------------------
    # 12. Generate signals
    # -------------------------------------------------------------------------
    signals = generate_signals(
        prices=prices,
        snapshots=snapshots,
        match=match,
        run_validation=run_validation,
        bankroll=bankroll,
        config=config,
        model_version=model_version,
        model_run_id=None,   # not yet persisted; caller sets this after logging
        pricing_warnings=pricing_validation.warnings,
    )

    logger.info(
        "run_pricing: match_id=%d status=%s adjustments=%d signals=%d "
        "(tier1: home=%.1f away=%.1f  final: home=%.1f away=%.1f)",
        match_id, run_status, len(adjustments), len(signals),
        baseline_home, baseline_away, current_home, current_away,
    )

    return {
        # Identity
        'match_id':           match_id,
        'model_version':      model_version,
        'run_timestamp':      run_timestamp,
        'run_status':         run_status,
        'can_proceed':        True,

        # Validation
        'run_validation':     run_validation,
        'pricing_validation': pricing_validation,

        # Inputs (passed through for caller/logger)
        'match':          match,
        'home_stats':     home_stats,
        'away_stats':     away_stats,
        'snapshots':      snapshots,
        'match_context':  match_context,

        # Tier 1 baseline outputs
        'baseline_home_points': round(baseline_home, 2),
        'baseline_away_points': round(baseline_away, 2),
        'baseline_margin':      round(baseline_home - baseline_away, 2),
        'baseline_total':       round(baseline_home + baseline_away, 2),

        # Final outputs (after all tiers)
        'final_home_points': round(current_home, 2),
        'final_away_points': round(current_away, 2),

        # Prices (H2H odds, handicap, total — from derive_final_prices)
        'prices': prices,

        # All tier adjustments (for model_adjustments table)
        'adjustments': adjustments,

        # Signals (for signals table)
        'signals': signals,
    }
