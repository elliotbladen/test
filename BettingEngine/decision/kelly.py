# decision/kelly.py
# =============================================================================
# Kelly staking logic — pure functions, no side effects, no DB access.
# =============================================================================
#
# Raw Kelly formula (decimal odds):
#
#   b = market_odds - 1          (net odds: what you win per $1 staked)
#   p = model_probability        (model's win probability)
#   q = 1 - p                    (model's loss probability)
#
#   raw_kelly = (b * p - q) / b
#             = ((market_odds - 1) * p - (1 - p)) / (market_odds - 1)
#
# If raw_kelly <= 0: no bet — the model does not have an edge at this price.
#
# V1 policy:
#   applied_kelly = raw_kelly * kelly_fraction   (default: 0.25 = quarter Kelly)
#   then apply stake caps (minimum actionable, hard cap)
#
# Quarter Kelly is mandatory in V1. Full Kelly is too aggressive for a new model.
# =============================================================================


def compute_raw_kelly(model_probability: float, market_odds: float) -> float:
    """
    Compute the raw (full) Kelly fraction.

    A positive value means bet; a negative value means no edge at this price.
    Callers should pass this to apply_quarter_kelly() before using it for sizing.

    Formula:
        b = market_odds - 1
        raw_kelly = (b * model_probability - (1 - model_probability)) / b

    Args:
        model_probability: model's implied win probability — must be in (0, 1]
        market_odds:       bookmaker decimal odds — must be > 1.0

    Returns:
        float — raw Kelly fraction (can be negative; negative means no bet)

    Raises:
        ValueError: if market_odds <= 1.0 (division by zero)
    """
    if not (0.0 < model_probability <= 1.0):
        raise ValueError(
            f"model_probability must be in (0, 1], got {model_probability}"
        )
    if market_odds <= 1.0:
        raise ValueError(
            f"market_odds must be > 1.0 (got {market_odds}); "
            "b = market_odds - 1 would be <= 0, causing division by zero."
        )
    b = float(market_odds) - 1.0
    p = float(model_probability)
    q = 1.0 - p
    return (b * p - q) / b


def apply_quarter_kelly(raw_kelly: float, kelly_config: dict = None) -> float:
    """
    Scale raw Kelly by the V1 Kelly fraction (default: 0.25).

    If raw_kelly is zero or negative, returns 0.0 — no bet.

    The Kelly fraction is read from kelly_config['fraction'] if provided,
    defaulting to 0.25 (quarter Kelly) per the V1 spec.

    Args:
        raw_kelly:    output of compute_raw_kelly()
        kelly_config: optional dict with key 'fraction' (e.g. {'fraction': 0.25})

    Returns:
        float >= 0.0 — applied Kelly fraction (as a proportion of bankroll)
    """
    if raw_kelly <= 0.0:
        return 0.0
    fraction = float((kelly_config or {}).get('fraction', 0.25))
    # Safety: fraction must be in (0, 1]
    fraction = max(0.0, min(1.0, fraction))
    return raw_kelly * fraction


def apply_stake_caps(
    kelly_fraction: float,
    bankroll: float,
    stake_caps_config: dict,
) -> tuple:
    """
    Apply minimum actionable threshold and hard cap to a Kelly fraction.

    Rules (thresholds are proportions of bankroll):
        < minimum_actionable_pct  → stake_amount = 0.0 (below threshold, pass/watch)
        <= hard_cap_pct           → stake_amount = kelly_fraction * bankroll
        > hard_cap_pct            → capped at hard_cap_pct * bankroll

    The capped_fraction is always returned for audit purposes, even when
    stake_amount is 0.0 (so the caller can see what Kelly said before capping).

    Args:
        kelly_fraction:     output of apply_quarter_kelly() — proportion of bankroll
        bankroll:           current bankroll in base currency
        stake_caps_config:  dict with keys:
                                minimum_actionable_pct  (default 0.0025 = 0.25%)
                                hard_cap_pct            (default 0.02   = 2.00%)

    Returns:
        (capped_stake_fraction, recommended_stake_amount)
        capped_stake_fraction:    fraction after hard cap applied (for audit)
        recommended_stake_amount: dollar amount to stake; 0.0 if below minimum
    """
    if kelly_fraction <= 0.0 or bankroll <= 0.0:
        return 0.0, 0.0

    min_pct  = float(stake_caps_config.get('minimum_actionable_pct', 0.0025))
    hard_cap = float(stake_caps_config.get('hard_cap_pct',           0.02))

    # Apply hard cap
    capped_fraction = min(float(kelly_fraction), hard_cap)

    # Below minimum actionable → not worth placing
    if capped_fraction < min_pct:
        return capped_fraction, 0.0

    stake_amount = capped_fraction * float(bankroll)
    return capped_fraction, round(stake_amount, 2)
