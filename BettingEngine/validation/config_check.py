# validation/config_check.py
# =============================================================================
# Startup config validation
# =============================================================================
#
# Validates the resolved config dicts loaded from:
#   config/tiers.yaml   → tier1_baseline, tier2_matchup, tier3–7 sections
#   config/kelly.yaml   → kelly, stake_caps, bankroll
#   config/pricing.yaml → ev_thresholds
#
# USAGE
# -----
# Call once at startup before any pricing run:
#
#   from validation.config_check import validate_tier_config, validate_kelly_config
#
#   issues = validate_tier_config(tiers_config)
#   issues += validate_kelly_config(kelly_config)
#   issues += validate_pricing_config(pricing_config)
#
#   for issue in issues:
#       if issue['level'] == 'error':
#           raise SystemExit(f"Config error: {issue['message']}")
#       else:
#           logger.warning("[CONFIG] %s", issue['message'])
#
# Or use validate_all_configs() to check everything in one call.
#
# DESIGN
# ------
# - Returns a list of issue dicts rather than raising immediately.
#   The caller decides whether to abort or warn.
# - Logs a resolved-value table at INFO level for every section checked.
# - 'error'   = hard failure: would cause division-by-zero, nonsensical output,
#               or completely disable a critical component.
# - 'warning' = suspicious: model will run, but output quality is degraded or
#               the value is outside the expected calibration range.
# =============================================================================

import logging
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Public API
# =============================================================================

def validate_all_configs(
    tiers_config: dict,
    kelly_config: dict = None,
    pricing_config: dict = None,
) -> list:
    """
    Validate all config sections in one call.

    Args:
        tiers_config:   full tiers.yaml dict (all tier sections)
        kelly_config:   full kelly.yaml dict, or None to skip
        pricing_config: full pricing.yaml dict, or None to skip

    Returns:
        list of issue dicts, each: {'level': 'error'|'warning', 'message': str}
        Empty list = all checks passed.
    """
    issues = []
    issues += validate_tier_config(tiers_config)
    if kelly_config is not None:
        issues += validate_kelly_config(kelly_config)
    if pricing_config is not None:
        issues += validate_pricing_config(pricing_config)
    return issues


def validate_tier_config(config: dict) -> list:
    """
    Validate tiers.yaml: Tier 1 baseline, Tier 2 yardage, and Tier 3–7 caps.

    Logs resolved values for every section checked.

    Args:
        config: full tiers.yaml dict (top-level keys are tier names)

    Returns:
        list of {'level': 'error'|'warning', 'message': str}
    """
    issues = []
    t1 = config.get('tier1_baseline', {})
    t2 = config.get('tier2_matchup', {})

    issues += _check_tier1(t1)
    issues += _check_tier2_yardage(t2)
    issues += _check_tier_caps(config)

    return issues


def validate_kelly_config(config: dict) -> list:
    """
    Validate kelly.yaml: kelly fraction, stake caps, bankroll.

    Args:
        config: full kelly.yaml dict

    Returns:
        list of {'level': 'error'|'warning', 'message': str}
    """
    issues = []
    kelly      = config.get('kelly', {})
    caps       = config.get('stake_caps', {})
    bankroll   = config.get('bankroll', {})

    issues += _check_kelly(kelly, caps, bankroll)
    return issues


def validate_pricing_config(config: dict) -> list:
    """
    Validate pricing.yaml: EV thresholds.

    Args:
        config: full pricing.yaml dict

    Returns:
        list of {'level': 'error'|'warning', 'message': str}
    """
    issues = []
    ev = config.get('ev_thresholds', {})
    issues += _check_ev_thresholds(ev)
    return issues


# =============================================================================
# Tier 1 checks
# =============================================================================

def _check_tier1(t1: dict) -> list:
    issues = []

    # --- Resolved values table ---
    _log_section('tier1_baseline', {
        'league_avg_total':                t1.get('league_avg_total'),
        'margin_std_dev':                  t1.get('margin_std_dev'),
        'home_advantage_points':           t1.get('home_advantage_points'),
        'elo_weight':                      t1.get('elo_weight'),
        'points_per_elo_point':            t1.get('points_per_elo_point'),
        'form_weight_points':              t1.get('form_weight_points'),
        'season_quality_scale':            t1.get('season_quality_scale'),
        'season_quality_win_weight':       t1.get('season_quality_win_weight'),
        'season_quality_ladder_weight':    t1.get('season_quality_ladder_weight'),
        'attack_season_weight':            t1.get('attack_season_weight'),
        'defence_season_weight':           t1.get('defence_season_weight'),
        'totals_conservative_bias':        t1.get('totals_conservative_bias'),
        'team_ha_max_delta':               t1.get('team_ha_max_delta'),
        'season_quality_num_teams':        t1.get('season_quality_num_teams'),
    })

    # --- Hard errors (division-by-zero / impossible values) ---

    # margin_std_dev: used as divisor in _win_probability_from_margin
    _require_positive(issues, t1, 'margin_std_dev', 'tier1_baseline',
                      note='used as divisor in win probability calculation')

    # league_avg_total: used as divisor (league_avg_per_team = total / 2)
    _require_positive(issues, t1, 'league_avg_total', 'tier1_baseline',
                      note='league_avg_per_team = league_avg_total / 2')

    # points_per_elo_point: used as divisor in ELO proxy fallback
    _require_positive(issues, t1, 'points_per_elo_point', 'tier1_baseline',
                      note='used as divisor in ELO quality proxy calculation')

    # season_quality_num_teams: used as (num_teams - 1) in ladder normalisation
    val = _get_float(t1, 'season_quality_num_teams')
    if val is not None and val < 2:
        issues.append(_error(
            'tier1_baseline.season_quality_num_teams',
            f"value={val} — must be >= 2 (denominator is num_teams - 1); "
            "ladder normalisation will divide by zero."
        ))

    # form normalisation denominators: used as divisors
    for key in ('form_margin_norm', 'form_scoring_norm', 'form_conceding_norm'):
        _require_positive(issues, t1, key, 'tier1_baseline',
                          note='used as divisor in form normalisation')

    # --- Warnings (suspicious but not fatal) ---

    # league_avg_total out of NRL calibration range
    _warn_range(issues, t1, 'league_avg_total', 'tier1_baseline', lo=35.0, hi=65.0,
                note='expected NRL range ~44–50; recalibrate each season')

    # margin_std_dev out of NRL calibration range
    _warn_range(issues, t1, 'margin_std_dev', 'tier1_baseline', lo=8.0, hi=18.0,
                note='expected NRL calibration range 10–14')

    # home_advantage_points: negative makes no sense; >10 is implausible
    _warn_range(issues, t1, 'home_advantage_points', 'tier1_baseline', lo=0.0, hi=10.0,
                note='expected NRL range 2.5–5.0')

    # elo_weight: blend ratio must be 0–1
    _require_fraction(issues, t1, 'elo_weight', 'tier1_baseline')

    # form_weight_points: >10 would mean form dominates baseline
    _warn_range(issues, t1, 'form_weight_points', 'tier1_baseline', lo=0.0, hi=10.0,
                note='values >5 give form an unusually large influence')

    # season_quality_scale: very large values amplify quality signal
    _warn_range(issues, t1, 'season_quality_scale', 'tier1_baseline', lo=5.0, hi=50.0,
                note='calibrated around net scoring differentials; typical range 16–32')

    # attack/defence season weights: must be 0–1 (blending fractions)
    _require_fraction(issues, t1, 'attack_season_weight', 'tier1_baseline')
    _require_fraction(issues, t1, 'defence_season_weight', 'tier1_baseline')

    # season quality win+ladder weights: should sum to ~1.0
    _warn_weights_sum(issues, t1, 'tier1_baseline',
                      ['season_quality_win_weight', 'season_quality_ladder_weight'],
                      expected_sum=1.0)

    # form component weights: should sum to ~1.0
    _warn_weights_sum(issues, t1, 'tier1_baseline',
                      ['form_outcome_weight', 'form_margin_weight',
                       'form_scoring_weight', 'form_conceding_weight'],
                      expected_sum=1.0)

    # season_quality_correction_weight: 0–1 blend
    _require_fraction(issues, t1, 'season_quality_correction_weight', 'tier1_baseline')

    # totals_conservative_bias: negative would inflate totals
    val = _get_float(t1, 'totals_conservative_bias')
    if val is not None and val < 0:
        issues.append(_warning(
            'tier1_baseline.totals_conservative_bias',
            f"value={val} is negative — this inflates totals rather than deflating them."
        ))

    # close_call_class_lean_threshold: must be > 0 (used in division)
    _require_positive(issues, t1, 'close_call_class_lean_threshold', 'tier1_baseline',
                      note='used as divisor in closeness calculation')

    # form behavior adjustments: individual effect sizes should be small
    for key in ('blowout_win_dampener', 'blowout_loss_amplifier',
                'narrow_loss_vs_strong_bonus', 'ugly_win_positive_bonus',
                'ugly_win_negative_penalty'):
        _warn_range(issues, t1, key, 'tier1_baseline', lo=0.0, hi=0.5,
                    note='form-score adjustment; values >0.5 are very large')

    # form behavior and quality caps: must be > 0
    for key in ('form_behavior_max_adj', 'form_quality_max_adj'):
        val = _get_float(t1, key)
        if val is not None and val <= 0:
            issues.append(_warning(
                f'tier1_baseline.{key}',
                f"value={val} — cap <= 0 will zero out all form adjustments of this type."
            ))

    # blowout threshold must be > narrow threshold (otherwise logic overlaps)
    blowout = _get_float(t1, 'blowout_threshold')
    narrow  = _get_float(t1, 'narrow_threshold')
    if blowout is not None and narrow is not None and blowout <= narrow:
        issues.append(_warning(
            'tier1_baseline.blowout_threshold / narrow_threshold',
            f"blowout_threshold={blowout} is not greater than narrow_threshold={narrow}. "
            "Rules A and B/C/D rely on these being non-overlapping ranges."
        ))

    return issues


# =============================================================================
# Tier 2 yardage checks
# =============================================================================

def _check_tier2_yardage(t2: dict) -> list:
    issues = []
    y = t2.get('yardage', {})

    _log_section('tier2_matchup.yardage', {
        'enabled':                    y.get('enabled'),
        'max_points_swing':           y.get('max_points_swing'),
        'run_metres_weight':          y.get('run_metres_weight'),
        'completion_weight':          y.get('completion_weight'),
        'kick_weight':                y.get('kick_weight'),
        'ruck_weight':                y.get('ruck_weight'),
        'run_metres_norm':            y.get('run_metres_norm'),
        'post_contact_metres_norm':   y.get('post_contact_metres_norm'),
        'completion_rate_norm':       y.get('completion_rate_norm'),
        'errors_pg_norm':             y.get('errors_pg_norm'),
        'penalties_pg_norm':          y.get('penalties_pg_norm'),
        'kick_metres_norm':           y.get('kick_metres_norm'),
        'ruck_speed_norm':            y.get('ruck_speed_norm'),
        'run_metres_only_weight':     y.get('run_metres_only_weight'),
        'post_contact_metres_weight': y.get('post_contact_metres_weight'),
        'completion_rate_weight':     y.get('completion_rate_weight'),
        'errors_weight':              y.get('errors_weight'),
        'penalties_weight':           y.get('penalties_weight'),
        'min_sample_games':           y.get('min_sample_games'),
    })

    if not y:
        return issues  # yardage section absent — not an error, bucket just won't run

    # --- Hard errors ---

    # All normalisation denominators are used as divisors
    for key in ('run_metres_norm', 'post_contact_metres_norm',
                'completion_rate_norm', 'errors_pg_norm', 'penalties_pg_norm',
                'kick_metres_norm', 'ruck_speed_norm'):
        _require_positive(issues, y, key, 'tier2_matchup.yardage',
                          note='used as divisor in signal normalisation')

    # max_points_swing: used as multiplier; 0 means bucket always returns 0
    val = _get_float(y, 'max_points_swing')
    if val is not None and val <= 0:
        issues.append(_error(
            'tier2_matchup.yardage.max_points_swing',
            f"value={val} — yardage bucket will always produce zero adjustment."
        ))

    # --- Warnings ---

    # max_points_swing suspiciously large (> outer tier cap is contradictory)
    outer_cap = _get_float(t2, 'max_home_points_delta')
    if val is not None and outer_cap is not None and val > outer_cap:
        issues.append(_warning(
            'tier2_matchup.yardage.max_points_swing',
            f"value={val} exceeds tier2 outer cap max_home_points_delta={outer_cap}. "
            "The outer cap will always be the binding constraint — "
            "inner cap has no independent effect."
        ))

    # Signal weights should sum to ~1.0
    _warn_weights_sum(issues, y, 'tier2_matchup.yardage',
                      ['run_metres_weight', 'completion_weight',
                       'kick_weight', 'ruck_weight'],
                      expected_sum=1.0)

    # Signal 1 sub-weights should sum to ~1.0
    _warn_weights_sum(issues, y, 'tier2_matchup.yardage (signal 1)',
                      ['run_metres_only_weight', 'post_contact_metres_weight'],
                      expected_sum=1.0)

    # Signal 2 sub-weights should sum to ~1.0
    _warn_weights_sum(issues, y, 'tier2_matchup.yardage (signal 2)',
                      ['completion_rate_weight', 'errors_weight', 'penalties_weight'],
                      expected_sum=1.0)

    # min_sample_games: 0 means no gate — early-season noise will propagate
    val = _get_float(y, 'min_sample_games')
    if val is not None and val < 1:
        issues.append(_warning(
            'tier2_matchup.yardage.min_sample_games',
            f"value={val} — sample gate is disabled. "
            "Yardage signals will fire from round 1 on very thin data."
        ))

    return issues


# =============================================================================
# Tier 3–7 cap checks
# =============================================================================

def _check_tier_caps(config: dict) -> list:
    issues = []

    cap_checks = [
        ('tier2_matchup',    'max_home_points_delta', 0, 15),
        ('tier2_matchup',    'max_away_points_delta', 0, 15),
        ('tier3_situational','max_home_points_delta', 0, 10),
        ('tier3_situational','max_away_points_delta', 0, 10),
        ('tier4_venue',      'max_home_points_delta', 0, 10),
        ('tier4_venue',      'max_away_points_delta', 0, 10),
        ('tier5_injury',     'max_home_points_delta', 0, 15),
        ('tier5_injury',     'max_away_points_delta', 0, 15),
        ('tier6_referee',    'max_total_delta',        0, 8),
        ('tier6_referee',    'max_margin_delta',       0, 6),
    ]

    resolved = {}
    for tier, key, lo, hi in cap_checks:
        section = config.get(tier, {})
        val = _get_float(section, key)
        label = f'{tier}.{key}'
        resolved[label] = val
        if val is None:
            continue
        if val < 0:
            issues.append(_error(
                label,
                f"value={val} — negative cap will invert tier adjustments."
            ))
        elif val > hi:
            issues.append(_warning(
                label,
                f"value={val} exceeds expected maximum of {hi} pts. "
                "This tier could dominate the final price."
            ))

    _log_section('tier caps', resolved)

    # Tier 7 lunar — experimental; warn if enabled and values are large
    lunar = config.get('tier7_environment', {}).get('lunar', {})
    if lunar.get('enabled'):
        for key in ('max_home_points_delta', 'max_away_points_delta', 'max_total_delta'):
            val = _get_float(lunar, key)
            if val is not None and val > 2.0:
                issues.append(_warning(
                    f'tier7_environment.lunar.{key}',
                    f"value={val} — lunar factor is experimental and should be bounded "
                    "tightly (≤ 1.0 recommended)."
                ))

    return issues


# =============================================================================
# Kelly / stake cap checks
# =============================================================================

def _check_kelly(kelly: dict, caps: dict, bankroll: dict) -> list:
    issues = []

    _log_section('kelly + stake_caps', {
        'kelly.fraction':                     kelly.get('fraction'),
        'stake_caps.minimum_actionable_pct':  caps.get('minimum_actionable_pct'),
        'stake_caps.soft_review_threshold_pct': caps.get('soft_review_threshold_pct'),
        'stake_caps.hard_cap_pct':            caps.get('hard_cap_pct'),
        'bankroll.starting_bankroll':         bankroll.get('starting_bankroll'),
    })

    # Kelly fraction: 0 → no bets ever placed; > 0.25 violates V1 spec
    frac = _get_float(kelly, 'fraction')
    if frac is None:
        issues.append(_error(
            'kelly.fraction',
            "key is missing — stake sizing cannot run."
        ))
    elif frac <= 0:
        issues.append(_error(
            'kelly.fraction',
            f"value={frac} — Kelly fraction <= 0 means no bet will ever be sized."
        ))
    elif frac > 0.25:
        issues.append(_warning(
            'kelly.fraction',
            f"value={frac} exceeds quarter Kelly (0.25) — V1 spec requires <= 0.25. "
            "Full Kelly is too aggressive for Year 1."
        ))

    # hard_cap_pct must be > 0
    hard_cap = _get_float(caps, 'hard_cap_pct')
    if hard_cap is not None and hard_cap <= 0:
        issues.append(_error(
            'stake_caps.hard_cap_pct',
            f"value={hard_cap} — hard cap <= 0 means stakes will always be zero."
        ))

    # Cap ordering: minimum < soft_review < hard_cap
    min_pct    = _get_float(caps, 'minimum_actionable_pct')
    soft_pct   = _get_float(caps, 'soft_review_threshold_pct')
    if (min_pct is not None and soft_pct is not None and hard_cap is not None):
        if not (min_pct < soft_pct < hard_cap):
            issues.append(_warning(
                'stake_caps',
                f"Cap thresholds are not in ascending order: "
                f"minimum={min_pct}, soft_review={soft_pct}, hard_cap={hard_cap}. "
                "Expected: minimum < soft_review < hard_cap."
            ))

    # Starting bankroll must be positive
    br = _get_float(bankroll, 'starting_bankroll')
    if br is not None and br <= 0:
        issues.append(_error(
            'bankroll.starting_bankroll',
            f"value={br} — bankroll must be positive for stake calculations."
        ))

    return issues


# =============================================================================
# EV threshold checks
# =============================================================================

def _check_ev_thresholds(ev: dict) -> list:
    issues = []

    _log_section('ev_thresholds', {
        'no_bet_below':           ev.get('no_bet_below'),
        'pass_below':             ev.get('pass_below'),
        'watch_below':            ev.get('watch_below'),
        'recommend_small_below':  ev.get('recommend_small_below'),
        'recommend_medium_below': ev.get('recommend_medium_below'),
    })

    thresholds = [
        ('no_bet_below', 'pass_below'),
        ('pass_below',   'watch_below'),
        ('watch_below',  'recommend_small_below'),
        ('recommend_small_below', 'recommend_medium_below'),
    ]

    for lower_key, upper_key in thresholds:
        lo = _get_float(ev, lower_key)
        hi = _get_float(ev, upper_key)
        if lo is not None and hi is not None and lo >= hi:
            issues.append(_warning(
                f'ev_thresholds.{lower_key} / {upper_key}',
                f"{lower_key}={lo} is not less than {upper_key}={hi}. "
                "EV bands must be strictly ascending."
            ))

    # recommend_medium_below >= 1.0 would mean 100% EV required — no bet ever fires
    val = _get_float(ev, 'recommend_medium_below')
    if val is not None and val >= 1.0:
        issues.append(_warning(
            'ev_thresholds.recommend_medium_below',
            f"value={val} — EV threshold >= 100% means recommend_medium and "
            "recommend_strong signals will never fire."
        ))

    return issues


# =============================================================================
# Helpers
# =============================================================================

def _get_float(d: dict, key: str) -> Any:
    """Return float(d[key]) or None if missing/unconvertible."""
    val = d.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _require_positive(issues, section, key, section_name, note=''):
    val = _get_float(section, key)
    if val is None:
        issues.append(_error(
            f'{section_name}.{key}',
            f"key is missing or non-numeric{f' ({note})' if note else ''}."
        ))
    elif val <= 0:
        issues.append(_error(
            f'{section_name}.{key}',
            f"value={val} — must be > 0{f' ({note})' if note else ''}."
        ))


def _require_fraction(issues, section, key, section_name):
    """Warn if value is outside [0.0, 1.0]."""
    val = _get_float(section, key)
    if val is None:
        return
    if not (0.0 <= val <= 1.0):
        issues.append(_warning(
            f'{section_name}.{key}',
            f"value={val} — expected a blend fraction in [0.0, 1.0]."
        ))


def _warn_range(issues, section, key, section_name, lo, hi, note=''):
    val = _get_float(section, key)
    if val is None:
        return
    if not (lo <= val <= hi):
        issues.append(_warning(
            f'{section_name}.{key}',
            f"value={val} is outside expected range [{lo}, {hi}]"
            f"{f' — {note}' if note else ''}."
        ))


def _warn_weights_sum(issues, section, section_name, keys, expected_sum=1.0, tolerance=0.02):
    vals = [_get_float(section, k) for k in keys]
    if any(v is None for v in vals):
        return  # missing keys — other checks will catch those
    total = sum(vals)
    if abs(total - expected_sum) > tolerance:
        issues.append(_warning(
            f'{section_name} weights',
            f"[{', '.join(keys)}] sum to {total:.4f}, expected {expected_sum}. "
            "Weights should sum to 1.0 for the bucket score to be interpretable."
        ))


def _error(key: str, message: str) -> dict:
    return {'level': 'error', 'key': key, 'message': f"{key}: {message}"}


def _warning(key: str, message: str) -> dict:
    return {'level': 'warning', 'key': key, 'message': f"{key}: {message}"}


def _log_section(section_name: str, resolved: dict) -> None:
    """Log resolved config values for a section at INFO level."""
    logger.info("Config resolved — %s:", section_name)
    for k, v in resolved.items():
        logger.info("  %-45s = %s", k, v if v is not None else '(not set)')
