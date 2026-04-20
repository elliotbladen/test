# decision/ev.py
# =============================================================================
# EV calculation — pure functions, no side effects, no DB access.
# =============================================================================
#
# Official formula (decimal odds):
#   model_probability = 1 / model_odds
#   EV = (model_probability * market_odds) - 1
#   EV_percent = EV * 100
#
# Example:
#   model_odds = 2.40   →   model_probability = 0.4167
#   market_odds = 3.00
#   EV = (0.4167 * 3.00) - 1 = 0.25   →   +25% EV
#
# All functions raise ValueError on invalid inputs rather than returning
# silent garbage. The caller is responsible for validating inputs upstream.
# =============================================================================


def compute_model_probability(model_odds: float) -> float:
    """
    Convert model fair odds to implied probability.

    model_odds must be strictly greater than 1.0. Odds of exactly 1.0
    imply 100% probability — a certainty — which the model should never produce.

    Args:
        model_odds: fair decimal odds from the pricing engine (must be > 1.0)

    Returns:
        float in (0, 1) — implied probability

    Raises:
        ValueError: if model_odds <= 1.0
    """
    if not isinstance(model_odds, (int, float)) or model_odds != model_odds:
        raise ValueError(f"model_odds must be a finite number, got {model_odds!r}")
    if model_odds <= 1.0:
        raise ValueError(
            f"model_odds must be > 1.0 (got {model_odds}). "
            "Odds of 1.0 or below imply >= 100% probability."
        )
    return 1.0 / float(model_odds)


def compute_ev(model_probability: float, market_odds: float) -> float:
    """
    Compute expected value for a $1 stake.

    Formula: EV = (model_probability * market_odds) - 1

    Positive EV means the market is offering better odds than the model's
    fair price — a potential edge. Negative EV means the bookmaker has the
    better of this market.

    Args:
        model_probability: implied probability from compute_model_probability()
                           must be in (0, 1]
        market_odds:       bookmaker's available decimal odds, must be > 1.0

    Returns:
        float — EV per $1 stake (e.g. 0.25 = +25% EV, -0.05 = -5% EV)

    Raises:
        ValueError: if inputs are out of range
    """
    if not (0.0 < model_probability <= 1.0):
        raise ValueError(
            f"model_probability must be in (0, 1], got {model_probability}. "
            "Use compute_model_probability() to derive it from model odds."
        )
    if not isinstance(market_odds, (int, float)) or market_odds != market_odds:
        raise ValueError(f"market_odds must be a finite number, got {market_odds!r}")
    if market_odds <= 1.0:
        raise ValueError(
            f"market_odds must be > 1.0 (got {market_odds}). "
            "Odds of 1.0 or below mean the bookmaker pays nothing on a win."
        )
    return (model_probability * float(market_odds)) - 1.0


def compute_ev_percent(ev: float) -> float:
    """
    Convert EV to percentage form.

    Args:
        ev: output of compute_ev() (e.g. 0.25)

    Returns:
        float — EV as a percentage (e.g. 25.0)
    """
    return float(ev) * 100.0
