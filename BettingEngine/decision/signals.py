# decision/signals.py
# =============================================================================
# Signal generation — pure functions, no side effects, no DB access.
# =============================================================================
#
# Signal labels (in ascending order of strength):
#   no_bet | pass | watch | recommend_small | recommend_medium | recommend_strong
#
# generate_signals() signature change from the original stub:
#   Original: generate_signals(conn, model_run_id, bankroll, config)
#   Revised:  generate_signals(prices, snapshots, match, run_validation,
#                              bankroll, config, model_version, model_run_id)
#
# Reason: the decision layer should be a pure function that receives all data
# from the caller (pricing engine / run_pricing). DB reads belong in the caller,
# not here. This keeps the decision layer testable in isolation.
#
# =============================================================================
#
# compute_confidence() signal_inputs keys:
#   'warnings'           list   — RunValidation.warnings (each has 'flag' key)
#   'snapshot_age_hours' float  — age of the specific snapshot in hours
#   'bookmaker_count'    int    — how many bookmakers offer this market/selection
#
# generate_signals() config keys read (merged config dict):
#   ev_thresholds        dict   — from pricing.yaml
#   kelly                dict   — from kelly.yaml  {'fraction': 0.25}
#   stake_caps           dict   — from kelly.yaml  {minimum_actionable_pct, hard_cap_pct}
#   tier1_baseline       dict   — from tiers.yaml  (reads margin_std_dev)
#   extreme_ev_threshold float  — optional; default 0.80
#   snapshot_hard_stale_hours float — optional; default 48.0
#   snapshot_soft_stale_hours float — optional; default 12.0
#
# =============================================================================

import math
import logging
from datetime import datetime
from typing import Optional

from decision.ev import compute_model_probability, compute_ev, compute_ev_percent
from decision.kelly import compute_raw_kelly, apply_quarter_kelly, apply_stake_caps
from decision.veto import check_hard_vetoes, check_soft_vetoes

logger = logging.getLogger(__name__)


# =============================================================================
# Signal label assignment
# =============================================================================

def assign_signal_label(ev_percent: float, config: dict) -> str:
    """
    Map an EV percentage to a signal label using thresholds from pricing config.

    Thresholds are read from config['ev_thresholds'] (the pricing.yaml section).
    Config values are in decimal form (0.10 = 10%); ev_percent is in percent form
    (10.0 = 10%). Conversion is handled internally.

    Labels and default thresholds:
        ev_percent <  0.0%  → no_bet
        0.0% to  9.99%      → pass
        10.0% to 19.99%     → watch
        20.0% to 29.99%     → recommend_small
        30.0% to 49.99%     → recommend_medium
        50.0%+              → recommend_strong   (also sets manual_review_required)

    Args:
        ev_percent: EV as a percentage (e.g. 25.0 for +25% EV)
        config:     full pricing config dict or just the ev_thresholds section

    Returns:
        one of: 'no_bet' | 'pass' | 'watch' | 'recommend_small' |
                'recommend_medium' | 'recommend_strong'
    """
    # Accept both the full pricing config and the raw ev_thresholds section
    thresholds = config.get('ev_thresholds', config)

    no_bet_pct     = float(thresholds.get('no_bet_below',           0.00)) * 100.0
    pass_pct       = float(thresholds.get('pass_below',             0.10)) * 100.0
    watch_pct      = float(thresholds.get('watch_below',            0.20)) * 100.0
    rec_small_pct  = float(thresholds.get('recommend_small_below',  0.30)) * 100.0
    rec_medium_pct = float(thresholds.get('recommend_medium_below', 0.50)) * 100.0

    ev = float(ev_percent)

    if ev < no_bet_pct:
        return 'no_bet'
    if ev < pass_pct:
        return 'pass'
    if ev < watch_pct:
        return 'watch'
    if ev < rec_small_pct:
        return 'recommend_small'
    if ev < rec_medium_pct:
        return 'recommend_medium'
    return 'recommend_strong'


# =============================================================================
# Confidence scoring
# =============================================================================

def compute_confidence(signal_inputs: dict, config: dict) -> str:
    """
    Compute confidence level from signal context factors.

    Confidence is separate from EV. A signal can have high EV but low
    confidence (e.g. thin data, stale snapshot, single bookmaker).

    Scoring:
        Starts at 0 (neutral → 'medium').
        Penalty factors push score negative → 'low'.
        Bonus factors push score positive  → 'high'.

    Penalty factors:
        THIN_DATA in warnings:       -2  (early season, small sample)
        ELO_FALLBACK in warnings:    -1  (weaker strength signal)
        FORM_FALLBACK in warnings:   -1  (form from stored rating, not results)
        STALE_STATS in warnings:     -1  (team stats may be out of date)
        snapshot_age_hours > 24:     -1  (odds may have moved)
        bookmaker_count < 2:         -1  (edge unconfirmed by second source)
        more than 3 total warnings:  -1  (many data quality concerns)

    Bonus factors:
        bookmaker_count >= 2:        +1  (confirmed by second sharp price)
        snapshot_age_hours < 6:      +1  (fresh snapshot)
        no warnings at all:          +1  (clean data)

    Final mapping:
        score <= -2  → 'low'
        score >= +2  → 'high'
        otherwise    → 'medium'

    Args:
        signal_inputs: dict with keys:
            'warnings'           list  — RunValidation.warnings (flag+message dicts)
            'snapshot_age_hours' float — age of the specific snapshot in hours
            'bookmaker_count'    int   — number of bookmakers for this market
        config: pricing config dict (currently unused; reserved for future tuning)

    Returns:
        'low' | 'medium' | 'high'
    """
    warnings     = signal_inputs.get('warnings') or []
    warning_flags = {w.get('flag') for w in warnings}
    age_hours     = signal_inputs.get('snapshot_age_hours')
    bk_count      = int(signal_inputs.get('bookmaker_count', 0))

    score = 0

    # --- Penalty factors ---
    if 'THIN_DATA' in warning_flags:
        score -= 2
    if 'ELO_FALLBACK' in warning_flags:
        score -= 1
    if 'FORM_FALLBACK' in warning_flags:
        score -= 1
    if 'STALE_STATS' in warning_flags:
        score -= 1
    if age_hours is not None and age_hours > 24.0:
        score -= 1
    if bk_count < 2:
        score -= 1
    if len(warnings) > 3:
        score -= 1

    # --- Bonus factors ---
    if bk_count >= 2:
        score += 1
    if age_hours is not None and age_hours < 6.0:
        score += 1
    if not warnings:
        score += 1

    if score <= -2:
        return 'low'
    if score >= 2:
        return 'high'
    return 'medium'


# =============================================================================
# Signal generation
# =============================================================================

def generate_signals(
    prices: dict,
    snapshots: list,
    match: dict,
    run_validation,
    bankroll: float,
    config: dict,
    model_version: str = 'v1',
    model_run_id: Optional[int] = None,
    pricing_warnings: Optional[list] = None,
) -> list:
    """
    Generate all bet signals for a match by comparing model prices to snapshots.

    One signal is produced per (bookmaker, market_type, selection_name) combination
    in the snapshots list. Signals are produced for all combinations — including
    no_bet and pass — so every comparison is auditable. The caller filters by
    signal label if only actionable signals are needed.

    Market type support:
        h2h:       uses fair_home_odds / fair_away_odds directly from prices
        handicap:  uses normal distribution against fair_handicap_line and final_margin
        total:     uses normal distribution against fair_total_line and final_total

    For handicap and total, the normal distribution std_dev is read from
    config['tier1_baseline']['margin_std_dev'] (default 12.0). This is the same
    value used in derive_final_prices(). A separate total_std_dev can be set via
    config['tier1_baseline']['total_std_dev'] (default: same as margin_std_dev).

    Args:
        prices:           dict from derive_final_prices():
                              fair_home_odds, fair_away_odds,
                              fair_handicap_line, fair_total_line,
                              final_margin, final_total,
                              home_win_probability, away_win_probability
        snapshots:        list from get_latest_snapshots_for_match()
                              each dict has: market_type, selection_name,
                              odds_decimal, line_value, captured_at,
                              bookmaker_name, bookmaker_code
        match:            dict from get_match_by_id()
        run_validation:   RunValidation object from validate_run_inputs()
                          (or None — treated as no warnings, can_proceed=True)
        bankroll:         current bankroll in base currency
        config:           merged config dict containing ev_thresholds, kelly,
                          stake_caps, and tier1_baseline sections
        model_version:    model version string for audit trail
        model_run_id:     model run id if already logged (optional, for linking)
        pricing_warnings: list of warning dicts from validate_pricing_output()
                          (or None). Passed into the veto context so that
                          ABSURD_TOTAL, ABSURD_MARGIN, and LARGE_TIER_ADJUSTMENT
                          flags can trigger hard or soft vetoes.

    Returns:
        list of signal dicts, one per snapshot. Each dict contains all fields
        required by the signals table schema. Empty list if no snapshots.
    """
    if not snapshots:
        return []

    # Extract sub-configs
    ev_config      = config.get('ev_thresholds', {})
    kelly_config   = config.get('kelly', {})
    caps_config    = config.get('stake_caps', {})
    t1_config      = config.get('tier1_baseline', config)
    margin_std_dev = float(t1_config.get('margin_std_dev', 12.0))
    total_std_dev  = float(t1_config.get('total_std_dev', margin_std_dev))

    # Resolve run_validation fields defensively
    warnings    = getattr(run_validation, 'warnings', []) or []
    can_proceed = getattr(run_validation, 'can_proceed', True)

    # Snapshot age: compute relative to kickoff
    kickoff_str = (match or {}).get('kickoff_datetime') or (match or {}).get('match_date')

    # Count bookmakers per (market_type, selection_name) for confidence scoring
    bk_market_counts: dict = {}
    for snap in snapshots:
        key = (snap.get('market_type'), snap.get('selection_name'))
        bk_market_counts[key] = bk_market_counts.get(key, 0) + 1

    signals = []
    timestamp = datetime.utcnow().isoformat()

    for snap in snapshots:
        market_type    = (snap.get('market_type') or '').lower()
        selection_name = (snap.get('selection_name') or '').lower()
        market_odds    = snap.get('odds_decimal')
        line_value     = snap.get('line_value')
        bookmaker_name = snap.get('bookmaker_name', '')
        bookmaker_code = snap.get('bookmaker_code', '')

        # --- Resolve model odds for this market/selection ---
        model_odds = _resolve_model_odds(
            market_type, selection_name, line_value,
            prices, margin_std_dev, total_std_dev,
        )
        if model_odds is None:
            logger.debug(
                "generate_signals: cannot resolve model odds for "
                "%s / %s — skipping", market_type, selection_name
            )
            continue

        # --- Snapshot age ---
        snapshot_age_hours = _snapshot_age_hours(
            snap.get('captured_at'), kickoff_str
        )

        # --- EV ---
        try:
            model_prob = compute_model_probability(model_odds)
            ev         = compute_ev(model_prob, float(market_odds)) if market_odds else None
            ev_pct     = compute_ev_percent(ev) if ev is not None else None
        except (ValueError, TypeError) as exc:
            logger.warning(
                "generate_signals: EV calculation failed for %s / %s: %s",
                market_type, selection_name, exc,
            )
            ev = ev_pct = model_prob = None

        # --- Kelly ---
        raw_kelly = applied_kelly = capped_fraction = stake_amount = None
        if ev is not None and model_prob is not None and market_odds:
            try:
                raw_kelly      = compute_raw_kelly(model_prob, float(market_odds))
                applied_kelly  = apply_quarter_kelly(raw_kelly, kelly_config)
                capped_fraction, stake_amount = apply_stake_caps(
                    applied_kelly, bankroll, caps_config
                )
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "generate_signals: Kelly calculation failed for %s / %s: %s",
                    market_type, selection_name, exc,
                )

        # --- Signal label ---
        label = assign_signal_label(ev_pct or -999.0, ev_config)

        # --- Confidence ---
        signal_inputs = {
            'warnings':           warnings,
            'snapshot_age_hours': snapshot_age_hours,
            'bookmaker_count':    bk_market_counts.get(
                                      (snap.get('market_type'), snap.get('selection_name')), 0
                                  ),
        }
        confidence = compute_confidence(signal_inputs, config)

        # --- Veto context ---
        context = {
            'match':              match,
            'snapshot':           snap,
            'ev':                 ev,
            'model_probability':  model_prob,
            'market_odds':        market_odds,
            'confidence':         confidence,
            'warnings':           warnings,
            'can_proceed':        can_proceed,
            'bookmaker_count':    signal_inputs['bookmaker_count'],
            'snapshot_age_hours': snapshot_age_hours,
            'pricing_warnings':   pricing_warnings or [],
        }

        # Partial signal dict passed to veto checks (read-only)
        partial_signal = {
            'market_type':    market_type,
            'selection_name': selection_name,
            'ev':             ev,
            'label':          label,
        }

        hard_vetoed, veto_reason = check_hard_vetoes(partial_signal, context, config)
        soft_veto_reasons        = check_soft_vetoes(partial_signal, context, config)

        # --- Assemble final signal ---
        signal = {
            # Identity
            'match_id':              (match or {}).get('match_id'),
            'model_run_id':          model_run_id,
            'model_version':         model_version,
            'timestamp':             timestamp,

            # Market
            'bookmaker_name':        bookmaker_name,
            'bookmaker_code':        bookmaker_code,
            'market_type':           market_type,
            'selection_name':        selection_name,
            'line_value':            line_value,

            # Prices
            'market_odds':           float(market_odds) if market_odds else None,
            'model_odds':            round(model_odds, 3) if model_odds else None,
            'model_probability':     round(model_prob, 4) if model_prob is not None else None,

            # EV
            'ev':                    round(ev, 4) if ev is not None else None,
            'ev_percent':            round(ev_pct, 2) if ev_pct is not None else None,

            # Kelly / sizing
            'raw_kelly':             round(raw_kelly, 4) if raw_kelly is not None else None,
            'applied_kelly':         round(applied_kelly, 4) if applied_kelly is not None else None,
            'capped_stake_fraction': round(capped_fraction, 4) if capped_fraction is not None else None,
            'recommended_stake':     stake_amount,

            # Decision
            'signal_label':          label,
            'confidence':            confidence,
            'veto':                  hard_vetoed,
            'veto_reason':           veto_reason if hard_vetoed else None,
            'soft_veto_reasons':     soft_veto_reasons,
            'manual_review_required': label == 'recommend_strong',

            # Snapshot linkage
            'snapshot_id':           snap.get('snapshot_id'),
            'snapshot_captured_at':  snap.get('captured_at'),
            'snapshot_age_hours':    round(snapshot_age_hours, 1) if snapshot_age_hours is not None else None,
        }

        signals.append(signal)

        logger.debug(
            "signal: %s %s %s %s | model=%.3f market=%.3f ev=%s label=%s veto=%s",
            bookmaker_name, market_type, selection_name,
            f"line={line_value}" if line_value else "",
            model_odds or 0,
            float(market_odds) if market_odds else 0,
            f"{ev_pct:.1f}%" if ev_pct is not None else "n/a",
            label,
            veto_reason if hard_vetoed else "none",
        )

    return signals


# =============================================================================
# Internal helpers
# =============================================================================

def _norm_cdf(z: float) -> float:
    """Standard normal CDF via math.erf — no external dependencies."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _resolve_model_odds(
    market_type: str,
    selection_name: str,
    line_value,
    prices: dict,
    margin_std_dev: float,
    total_std_dev: float,
) -> Optional[float]:
    """
    Return the model's fair decimal odds for a given market/selection.

    H2H:
        home → prices['fair_home_odds']
        away → prices['fair_away_odds']

    Handicap (home gives/takes points):
        Model probability = P(home actual margin > -line_value)
                          = Φ((final_margin + line_value) / margin_std_dev)
        where line_value is the bookmaker's handicap from home's perspective
        (negative means home gives points, e.g. -3.5 = home gives 3.5).

    Total:
        over  → P(actual_total > line_value) = Φ((final_total - line_value) / total_std_dev)
        under → complement

    Returns None if the market/selection is unrecognised or required data is missing.
    """
    if market_type == 'h2h':
        if selection_name == 'home':
            odds = prices.get('fair_home_odds')
        elif selection_name == 'away':
            odds = prices.get('fair_away_odds')
        else:
            return None
        return float(odds) if odds else None

    if market_type == 'handicap':
        if line_value is None:
            return None
        final_margin = prices.get('final_margin')
        if final_margin is None:
            return None
        try:
            # line_value is stored from each selection's own perspective.
            # The z-score formula requires the line in home-team perspective
            # (negative = home gives points). Negate for the away selection.
            if selection_name == 'away':
                home_line = -float(line_value)
            else:
                home_line = float(line_value)
            z = (float(final_margin) + home_line) / margin_std_dev
            p_home = _norm_cdf(z)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

        if selection_name == 'home':
            prob = max(0.001, min(0.999, p_home))
        elif selection_name == 'away':
            prob = max(0.001, min(0.999, 1.0 - p_home))
        else:
            return None
        return round(1.0 / prob, 3)

    if market_type == 'total':
        if line_value is None:
            return None
        final_total = prices.get('final_total')
        if final_total is None:
            return None
        try:
            z = (float(final_total) - float(line_value)) / total_std_dev
            p_over = _norm_cdf(z)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

        if selection_name == 'over':
            prob = max(0.001, min(0.999, p_over))
        elif selection_name == 'under':
            prob = max(0.001, min(0.999, 1.0 - p_over))
        else:
            return None
        return round(1.0 / prob, 3)

    return None


def _snapshot_age_hours(
    captured_at_str: Optional[str],
    kickoff_str: Optional[str],
) -> Optional[float]:
    """
    Compute the age of a snapshot relative to the match kickoff in hours.

    Returns None if either timestamp cannot be parsed.
    A positive value means the snapshot was captured before kickoff (normal).
    A negative value means it was captured after (unusual).
    """
    if not captured_at_str or not kickoff_str:
        return None
    try:
        captured = datetime.fromisoformat(str(captured_at_str).replace('T', ' '))
        kickoff  = datetime.fromisoformat(str(kickoff_str).replace('T', ' '))
        delta = kickoff - captured
        return delta.total_seconds() / 3600.0
    except (ValueError, TypeError):
        return None
