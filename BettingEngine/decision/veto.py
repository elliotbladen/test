# decision/veto.py
# =============================================================================
# Veto rules — pure functions, no side effects, no DB access.
# =============================================================================
#
# Hard vetoes block a signal entirely: (True, reason_string).
# Soft vetoes downgrade or flag a signal: list of reason strings (may be empty).
#
# Context dict expected keys (all optional — missing keys are treated as unknown):
#
#   'match'              dict    — from get_match_by_id()
#   'snapshot'           dict    — the specific market snapshot being evaluated
#   'ev'                 float   — computed EV decimal (e.g. 0.25)
#   'model_probability'  float   — model's implied probability
#   'market_odds'        float   — bookmaker's decimal odds
#   'confidence'         str     — 'low'|'medium'|'high'
#   'warnings'           list    — RunValidation.warnings (each has 'flag' key)
#   'bookmaker_count'    int     — number of bookmakers offering this market/selection
#   'snapshot_age_hours' float   — age of snapshot relative to match kickoff
#   'pricing_warnings'   list    — warnings from validate_pricing_output()
#
# =============================================================================

# Hard veto codes
_MISSING_MARKET_DATA      = 'MISSING_MARKET_DATA'
_INVALID_ODDS             = 'INVALID_ODDS'
_MODEL_INTEGRITY          = 'MODEL_INTEGRITY'
_EXTREME_EV_ANOMALY       = 'EXTREME_EV_ANOMALY'
_MATCH_NOT_SCHEDULED      = 'MATCH_NOT_SCHEDULED'
_STALE_SNAPSHOT           = 'STALE_SNAPSHOT'
_PRICING_INTEGRITY        = 'PRICING_INTEGRITY'

# Soft veto codes
_SINGLE_BOOKMAKER         = 'SINGLE_BOOKMAKER_SOURCE'
_LOW_CONFIDENCE           = 'LOW_CONFIDENCE'
_UNCERTAIN_REFEREE        = 'UNCERTAIN_REFEREE'
_MODERATELY_STALE_ODDS    = 'MODERATELY_STALE_ODDS'
_PRICING_WARNING          = 'PRICING_WARNING'
_EXPERIMENTAL_TIER        = 'EXPERIMENTAL_TIER_ACTIVE'

# Default thresholds
_DEFAULT_EXTREME_EV           = 0.80   # 80% EV — almost certainly bad data
_DEFAULT_HARD_STALE_HOURS     = 48.0   # snapshot age hard veto threshold
_DEFAULT_SOFT_STALE_HOURS     = 12.0   # snapshot age soft veto threshold


def check_hard_vetoes(signal: dict, context: dict, config: dict) -> tuple:
    """
    Check all hard veto conditions for a signal.

    A hard veto blocks the signal entirely. The caller should set
    signal['veto'] = True and signal['veto_reason'] = reason.

    Args:
        signal:  partial signal dict being constructed (read-only here)
        context: dict of supporting context (see module docstring for keys)
        config:  merged config dict; reads 'extreme_ev_threshold' if present

    Returns:
        (vetoed: bool, reason: str)
        If not vetoed: (False, '')
        If vetoed: (True, human-readable reason string starting with a veto code)
    """
    warnings     = context.get('warnings') or []
    warning_flags = {w.get('flag') for w in warnings}
    pricing_warnings = context.get('pricing_warnings') or []
    pricing_flags = {w.get('flag') for w in pricing_warnings}

    # 1. Model integrity: pre-run validation found blocking errors
    if not context.get('can_proceed', True):
        return True, (
            f"{_MODEL_INTEGRITY}: pre-run validation failed — "
            "pricing inputs had blocking errors. Do not act on this signal."
        )

    # 2. Missing or invalid market data
    snapshot = context.get('snapshot') or {}
    market_odds = context.get('market_odds')
    if market_odds is None or snapshot.get('odds_decimal') is None:
        return True, (
            f"{_MISSING_MARKET_DATA}: no odds available for this "
            f"{snapshot.get('market_type', 'unknown')} / "
            f"{snapshot.get('selection_name', 'unknown')} market."
        )

    # 3. Invalid odds value
    try:
        odds_val = float(market_odds)
    except (TypeError, ValueError):
        return True, (
            f"{_INVALID_ODDS}: market_odds={market_odds!r} is not a valid number."
        )
    if odds_val <= 1.0:
        return True, (
            f"{_INVALID_ODDS}: market_odds={odds_val} <= 1.0 — "
            "no payout possible on a win."
        )
    if odds_val > 1000.0:
        return True, (
            f"{_INVALID_ODDS}: market_odds={odds_val} > 1000 — "
            "implausibly large odds; likely a data error."
        )

    # 4. Extreme EV anomaly
    ev = context.get('ev')
    extreme_threshold = float(config.get('extreme_ev_threshold', _DEFAULT_EXTREME_EV))
    if ev is not None and ev > extreme_threshold:
        return True, (
            f"{_EXTREME_EV_ANOMALY}: EV={ev:.1%} exceeds the extreme threshold "
            f"({extreme_threshold:.0%}). This almost certainly reflects bad data "
            "rather than a genuine edge."
        )

    # 5. Match not confirmed as scheduled
    match = context.get('match') or {}
    status = match.get('status', '').lower()
    if status and status not in ('scheduled', 'upcoming', ''):
        return True, (
            f"{_MATCH_NOT_SCHEDULED}: match status='{status}'. "
            "Signals should only be generated for scheduled matches."
        )

    # 6. Stale snapshot (hard threshold from pre-run validation)
    snapshot_age = context.get('snapshot_age_hours')
    hard_stale = float(config.get('snapshot_hard_stale_hours', _DEFAULT_HARD_STALE_HOURS))
    if snapshot_age is not None and snapshot_age > hard_stale:
        return True, (
            f"{_STALE_SNAPSHOT}: snapshot is {snapshot_age:.0f}h old "
            f"(hard threshold: {hard_stale:.0f}h). "
            "Re-capture odds before generating signals."
        )

    # 7. Pricing integrity concern (absurd total or margin in output)
    hard_pricing_flags = {'ABSURD_TOTAL', 'ABSURD_MARGIN'}
    triggered = hard_pricing_flags & pricing_flags
    if triggered:
        return True, (
            f"{_PRICING_INTEGRITY}: pricing output has integrity warnings: "
            f"{sorted(triggered)}. Investigate before acting on this signal."
        )

    return False, ''


def check_soft_vetoes(signal: dict, context: dict, config: dict) -> list:
    """
    Check all soft veto conditions for a signal.

    Soft vetoes do not block the signal but should downgrade it or add
    a review flag. The caller appends these to signal['soft_veto_reasons'].

    Args:
        signal:  partial signal dict being constructed (read-only here)
        context: dict of supporting context (see module docstring for keys)
        config:  merged config dict

    Returns:
        list of reason strings — empty if no soft vetoes triggered
    """
    reasons = []
    warnings      = context.get('warnings') or []
    warning_flags = {w.get('flag') for w in warnings}
    pricing_warnings = context.get('pricing_warnings') or []
    pricing_flags = {w.get('flag') for w in pricing_warnings}

    # 1. Only one bookmaker source — less confirmation of the edge
    bookmaker_count = context.get('bookmaker_count', 0)
    if bookmaker_count < 2:
        reasons.append(
            f"{_SINGLE_BOOKMAKER}: only {bookmaker_count} bookmaker source for this "
            "market. Edge unconfirmed by a second sharp price."
        )

    # 2. Low confidence
    if context.get('confidence') == 'low':
        reasons.append(
            f"{_LOW_CONFIDENCE}: confidence is low — "
            "data quality or model stability concerns exist."
        )

    # 3. Referee uncertain
    match = context.get('match') or {}
    if match.get('referee_name') is None:
        reasons.append(
            f"{_UNCERTAIN_REFEREE}: referee not yet assigned for this match. "
            "Tier 6 scoring environment signal cannot run."
        )

    # 4. Moderately stale odds (soft threshold)
    snapshot_age = context.get('snapshot_age_hours')
    hard_stale = float(config.get('snapshot_hard_stale_hours', _DEFAULT_HARD_STALE_HOURS))
    soft_stale = float(config.get('snapshot_soft_stale_hours', _DEFAULT_SOFT_STALE_HOURS))
    if snapshot_age is not None and soft_stale < snapshot_age <= hard_stale:
        reasons.append(
            f"{_MODERATELY_STALE_ODDS}: snapshot is {snapshot_age:.0f}h old "
            f"(soft threshold: {soft_stale:.0f}h). Odds may have moved."
        )

    # 5. Pricing warnings that are non-blocking
    non_blocking_pricing = {'LARGE_TIER_ADJUSTMENT'} & pricing_flags
    if non_blocking_pricing:
        reasons.append(
            f"{_PRICING_WARNING}: pricing output has non-blocking warnings: "
            f"{sorted(non_blocking_pricing)}. Review tier adjustments before acting."
        )

    # 6. Experimental tier active (lunar)
    if 'LUNAR_ACTIVE' in warning_flags:
        reasons.append(
            f"{_EXPERIMENTAL_TIER}: the lunar (Tier 7B) adjustment was active. "
            "This is experimental and must not be the primary driver of the signal."
        )

    return reasons
