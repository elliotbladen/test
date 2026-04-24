# pricing/tier8_weather.py
# =============================================================================
# Tier 8 — Weather layer  (game-day pricing only)
# =============================================================================
#
# Weather is priced on game day once actual conditions are known.
# It is NOT applied during mid-week model runs.
#
# Sub-layer A: Weather conditions
#   Rain, wind, and dew suppress scoring (totals only — no handicap shift).
#   Logic is sourced from weather_conditions rows already fetched and stored
#   in the DB by scripts/fetch_weather.py. This module does NOT call any
#   external API.
#
# Sub-layer B: Lunar phase (experimental, off by default in V1)
#   Configurable via tiers.yaml tier8_weather.lunar.enabled.
#
# Condition → totals_delta table:
#   clear                         0.0
#   dew                          -2.0
#   light_rain                   -2.0
#   heavy_rain                   -4.0
#   moderate_wind                -2.0
#   moderate_wind + dew          -3.0
#   strong_wind                  -3.0
#   very_strong_wind             -4.0
#   light_rain + dew             -3.0
#   heavy_rain + strong_wind     -5.0
#   extreme                      -6.0
#
# =============================================================================

from datetime import datetime


# ---------------------------------------------------------------------------
# Condition classification
# ---------------------------------------------------------------------------

CONDITION_DELTAS: dict = {
    'clear':                        0.0,
    'dew':                         -2.0,
    'light_rain':                  -2.0,
    'heavy_rain':                  -4.0,
    'moderate_wind':               -2.0,
    'moderate_wind + dew':         -3.0,
    'strong_wind':                 -3.0,
    'very_strong_wind':            -4.0,
    'light_rain + dew':            -3.0,
    'heavy_rain + strong_wind':    -5.0,
    'extreme':                     -6.0,
}

TOTALS_DELTA_CAP = -6.0


def classify_condition(
    precip_mm: float,
    wind_kmh: float,
    dew_risk: bool,
) -> tuple:
    """
    Classify weather into a condition_type and return its totals_delta.

    Priority order (most severe first):
        1. extreme           wind >= 40 km/h AND (heavy rain OR dew)
        2. heavy_rain + strong_wind
        3. very_strong_wind  wind >= 40 km/h
        4. heavy_rain        precip > 2 mm
        5. strong_wind       wind 30-39 km/h
        6. light_rain + dew
        7. moderate_wind + dew
        8. moderate_wind     wind 20-29 km/h
        9. light_rain        precip 0-2 mm
       10. dew
       11. clear

    Returns (condition_type, totals_delta).
    """
    heavy       = precip_mm > 2.0
    light       = 0.0 < precip_mm <= 2.0
    very_strong = wind_kmh >= 40.0
    strong      = 30.0 <= wind_kmh < 40.0
    moderate    = 20.0 <= wind_kmh < 30.0

    if very_strong and (heavy or dew_risk):
        ct = 'extreme'
    elif heavy and (strong or very_strong):
        ct = 'heavy_rain + strong_wind'
    elif very_strong:
        ct = 'very_strong_wind'
    elif heavy:
        ct = 'heavy_rain'
    elif strong:
        ct = 'strong_wind'
    elif light and dew_risk:
        ct = 'light_rain + dew'
    elif moderate and dew_risk:
        ct = 'moderate_wind + dew'
    elif moderate:
        ct = 'moderate_wind'
    elif light:
        ct = 'light_rain'
    elif dew_risk:
        ct = 'dew'
    else:
        ct = 'clear'

    raw_delta = CONDITION_DELTAS[ct]
    delta = max(TOTALS_DELTA_CAP, raw_delta)
    return ct, delta


def compute_dew_risk(kickoff_datetime: str, temp_c: float, dew_point_c: float) -> bool:
    """
    Return True when all three dew conditions are met:
        1. Night game — kickoff after 18:00 local time
        2. dew_point_c > 10.0 C
        3. (temp_c - dew_point_c) < 4.0 C  (air near saturation)
    """
    if temp_c is None or dew_point_c is None:
        return False
    try:
        dt = datetime.fromisoformat(kickoff_datetime)
        night = dt.hour >= 18
    except (ValueError, TypeError):
        night = False
    spread = temp_c - dew_point_c
    return night and dew_point_c > 10.0 and spread < 4.0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_weather_adjustments(
    weather_row: dict | None,
    kickoff_datetime: str,
    config: dict,
) -> dict:
    """
    Compute Tier 8 weather adjustments from a weather_conditions DB row.

    Game-day only — should not be called during mid-week model runs.

    Args:
        weather_row:       Row from weather_conditions (None if not fetched yet).
        kickoff_datetime:  ISO local datetime string from matches.kickoff_datetime.
        config:            tiers.yaml['tier8_weather'] dict.

    Returns dict with:
        totals_delta      float  negative or 0.0
        condition_type    str
        dew_risk          bool
        _debug            dict
    """
    cfg = config.get('weather', {})
    if not cfg.get('enabled', True):
        return {
            'totals_delta':   0.0,
            'condition_type': 'clear',
            'dew_risk':       False,
            '_debug': {'reason': 'tier8 weather disabled'},
        }

    if not weather_row:
        return {
            'totals_delta':   0.0,
            'condition_type': 'clear',
            'dew_risk':       False,
            '_debug': {'reason': 'no weather data — assuming clear'},
        }

    temp_c           = weather_row.get('temp_c') or 0.0
    dew_point_c      = weather_row.get('dew_point_c') or 0.0
    wind_kmh         = weather_row.get('wind_kmh') or 0.0
    precipitation_mm = weather_row.get('precipitation_mm') or 0.0

    dew_risk_stored = weather_row.get('dew_risk')
    if dew_risk_stored is not None:
        dew_risk = bool(dew_risk_stored)
    else:
        dew_risk = compute_dew_risk(kickoff_datetime, temp_c, dew_point_c)

    condition_type, totals_delta = classify_condition(precipitation_mm, wind_kmh, dew_risk)

    max_delta = abs(cfg.get('max_total_delta', 6.0))
    totals_delta = max(-max_delta, totals_delta)

    return {
        'totals_delta':   totals_delta,
        'condition_type': condition_type,
        'dew_risk':       dew_risk,
        '_debug': {
            'temp_c':            temp_c,
            'dew_point_c':       dew_point_c,
            'wind_kmh':          wind_kmh,
            'precipitation_mm':  precipitation_mm,
            'dew_risk':          dew_risk,
            'condition_type':    condition_type,
            'totals_delta':      totals_delta,
            'data_source':       weather_row.get('data_source', '?'),
        },
    }


# ---------------------------------------------------------------------------
# Lunar sub-layer (Tier 8B) — experimental, off by default
# ---------------------------------------------------------------------------

def compute_lunar_adjustments(
    full_moon_flag: bool,
    new_moon_flag: bool,
    config: dict,
) -> dict:
    """
    Compute Tier 8B lunar phase adjustments.
    Only runs if tiers.yaml tier8_weather.lunar.enabled is True.
    """
    lunar_cfg = config.get('lunar', {})
    if not lunar_cfg.get('enabled', False):
        return {
            'home_delta':    0.0,
            'away_delta':    0.0,
            'totals_delta':  0.0,
            '_debug': {'reason': 'lunar disabled'},
        }

    home_delta   = 0.0
    away_delta   = 0.0
    totals_delta = 0.0

    if full_moon_flag:
        home_delta   += lunar_cfg.get('full_moon_home_delta', 0.5)
        totals_delta += lunar_cfg.get('full_moon_total_delta', 0.5)
    if new_moon_flag:
        away_delta   += lunar_cfg.get('new_moon_away_delta', 0.5)
        totals_delta += lunar_cfg.get('new_moon_total_delta', -0.5)

    max_h = lunar_cfg.get('max_home_points_delta', 1.0)
    max_a = lunar_cfg.get('max_away_points_delta', 1.0)
    max_t = lunar_cfg.get('max_total_delta', 1.5)

    return {
        'home_delta':    max(-max_h, min(max_h, home_delta)),
        'away_delta':    max(-max_a, min(max_a, away_delta)),
        'totals_delta':  max(-max_t, min(max_t, totals_delta)),
        '_debug': {
            'full_moon': full_moon_flag,
            'new_moon':  new_moon_flag,
        },
    }


# ---------------------------------------------------------------------------
# Engine shim — returns [] so engine.py _try_tier skips gracefully.
# Game-day weather is applied directly by price_round.py.
# ---------------------------------------------------------------------------

def compute_weather_stub(match: dict, context: dict, config: dict) -> list:
    """Stub for engine.py _try_tier. Weather runs game-day only."""
    return []
