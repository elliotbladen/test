# pricing/afl_tier7_weather.py
# =============================================================================
# AFL Tier 7 — Weather / Environmental layer
# =============================================================================
#
# AFL SCORING IS MORE WEATHER-SENSITIVE THAN NRL
# ─────────────────────────────────────────────────────────────────────────────
# NRL is a running game — carries, wrestle, set plays dominate. A wet ball
# matters less when you're driving off the line at close range.
#
# AFL disposal chains are built on accurate kicks of 30–50m. A wet, slippery
# ball directly collapses conversion rates and goal kicking accuracy:
#   - Goal kicking accuracy drops ~4-8% in wet conditions (Champion Data)
#   - Kick-in chains break down → turnovers → fewer inside 50s
#   - Mark counts fall → more contested possessions → lower conversion
#   - Rounds 13–17 (winter) accuracy averages ~47% vs ~51% early season
#
# KEY RESEARCH SOURCES
# ─────────────────────────────────────────────────────────────────────────────
#   AFL Lab (2018) — match-report classifications:
#       dry median: 178 pts  |  damp median: 151.5 pts  |  rain median: 136 pts
#   HPN Footy — heavy rain (10.4mm+) suppresses by ~18 pts (3 goals)
#   StatsInsider (335 poor-weather games) — fine: 177 pts, poor: 164 pts
#
# RAIN TIER STRUCTURE (updated)
# ─────────────────────────────────────────────────────────────────────────────
#   Old boundary was 2mm — too low. 2mm recorded daily can be pre/post-game.
#   New three-tier structure:
#       light_rain:     >0–5mm    -4.5 pts
#       moderate_rain:  5–10mm    -7.0 pts
#       heavy_rain:     >10mm     -9.0 pts   (maps to HPN 10.4mm / 3-goal finding)
#
# WIND DELTA CALIBRATION (updated)
# ─────────────────────────────────────────────────────────────────────────────
#   AFL drop-punt kicks are more wind-sensitive than NRL passing.
#   NFL analogy scaled to AFL: >40 km/h → ~11 pt NFL suppression → AFL larger.
#       moderate_wind  (20–29 km/h):  -2.8 pts  (well-calibrated, unchanged)
#       strong_wind    (30–39 km/h):  -6.0 pts  (raised from -5.0)
#       very_strong_wind (≥40 km/h):  -8.0 pts  (raised from -6.6)
#
# COLD CONDITIONS (added)
# ─────────────────────────────────────────────────────────────────────────────
#   Champion Data: Rounds 13–17 (winter) show measurably lower goal kicking
#   accuracy. Near-freezing games at UTAS Stadium Launceston and Melbourne
#   July night games can produce 6–10 pt combined suppression.
#       cold:  <5°C, no meaningful rain/wind  →  -3.5 pts
#
# MCG WIND SWIRL
# ─────────────────────────────────────────────────────────────────────────────
#   MCG is enclosed by 50–60m grandstands; documented wind channelling and
#   swirl. No quantitative AFL study exists. Use wind_venue_factor=1.1 for MCG
#   (10% uplift on wind delta). Clearly flagged as judgment-based.
#
# AFL GROUND CONTEXTS
# ─────────────────────────────────────────────────────────────────────────────
#   MCG (Melbourne):        open stands, swirling wind inside the bowl.
#                           Night dew games April–August.
#   Adelaide Oval:          open roof, volatile Adelaide weather.
#   Optus Stadium (Perth):  Fremantle Doctor is a SUMMER phenomenon — does not
#                           blow during AFL season (March–Sept). Not a factor.
#   Gabba (Brisbane):       afternoon thunderstorm risk Q1/Q2 of season.
#   Marvel Stadium:         retractable roof. CLOSED → no weather penalty.
#   UTAS / Blundstone:      Launceston / Hobart — cold and wet July/August.
#
# WEATHER → TOTALS DELTA TABLE  (AFL scoring units ~178 pts combined)
# ─────────────────────────────────────────────────────────────────────────────
#   Condition                       Totals Δ    Notes
#   ─────────────────────────────────────────────────────────────────────────
#   clear                             0.0
#   cold           (<5°C)            -3.5       winter accuracy drop, esp UTAS/MCG July
#   dew                              -2.8       night game, wet outfield
#   light_rain     (0–5mm)           -4.5       disposal chains start breaking
#   moderate_rain  (5–10mm)          -7.0       significant accuracy loss
#   heavy_rain     (>10mm)           -9.0       at HPN 10.4mm / 3-goal threshold
#   moderate_wind  (20–29 km/h)      -2.8       kicking affected
#   moderate_wind + dew              -4.5       compound night/wind
#   strong_wind    (30–39 km/h)      -6.0       raised from -5.0; AFL kick-dependency
#   very_strong_wind (≥40 km/h)      -8.0       raised from -6.6; severe kicking impact
#   light_rain + dew                 -6.0       slippery + wet outfield
#   heavy_rain + strong_wind         -9.5       very difficult conditions (capped)
#   extreme  (≥40 km/h + heavy/dew)  -9.5       at cap
#   ─────────────────────────────────────────────────────────────────────────
#   Global AFL cap: -9.5 pts (raised from -9.0)
#
# HEAT / TEMP NOTE
# ─────────────────────────────────────────────────────────────────────────────
#   AFL policy: matches shall not commence if temperature ≥36°C.
#   Heat suppresses player output in Q3/Q4, not kicking accuracy.
#   Heat effect is primarily a T3 situational (travel fatigue) and T4 venue
#   (Optus home advantage) story, not a T7 totals story.
#   Only extreme heat (>38°C) warrants a small totals flag (~-1.5 pts) —
#   apply as a manual override in the WEATHER dict if applicable.
#
# DEW RISK (AFL NIGHT GAMES)  — thresholds updated
# ─────────────────────────────────────────────────────────────────────────────
#   AFL night games in Melbourne (MCG/Marvel) from April–July are prime dew
#   conditions. Updated thresholds (dew point raised from 10°C → 12°C to
#   reduce false positives):
#       kickoff ≥ 18:30 local  (sufficient cooling time post-sunset)
#       dew_point_c  > 12.0°C  (more reliable dew formation threshold)
#       spread       < 5.0°C   (was 4.0°C — slight widening for AFL grounds)
#
# MARVEL STADIUM ROOF
# ─────────────────────────────────────────────────────────────────────────────
#   IMPORTANT: If the game is at Marvel Stadium with roof CLOSED:
#     - Do NOT apply any weather penalty
#     - Pass empty dict {} for weather
#     - The venue is effectively weatherproof
#   Only apply weather when roof is confirmed open or decision not yet made.
#
# DATA ENTRY
# ─────────────────────────────────────────────────────────────────────────────
#   Populate the WEATHER dict in prepare_afl_round.py with game-day conditions.
#   Format: {(home_team, away_team): {'precip_mm', 'wind_kmh', 'temp_c',
#                                      'dew_point_c', 'kickoff'}}
#
#   Example:
#       WEATHER = {
#           ('Essendon Bombers', 'Collingwood Magpies'): {
#               'precip_mm':   2.5,
#               'wind_kmh':    28.0,
#               'temp_c':      14.0,
#               'dew_point_c': 13.0,
#               'kickoff':     '2026-04-25T15:20:00',
#           },
#           ('Melbourne Demons', 'Geelong Cats'): {},    # clear / unknown
#       }
#
#   For MCG games with wind, pass wind_venue_factor=1.1 to compute_t7.
#
# =============================================================================

import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# AFL-specific condition table
# Larger deltas than NRL — disposal accuracy is kicking-dependent.
# ---------------------------------------------------------------------------

AFL_CONDITION_DELTAS: dict = {
    'clear':                        0.0,
    'cold':                        -3.5,   # <5°C — winter accuracy drop (UTAS/MCG July)
    'dew':                         -2.8,
    'light_rain':                  -4.5,   # 0–5mm (was -3.3 at 0–2mm boundary)
    'moderate_rain':               -7.0,   # 5–10mm (new tier)
    'heavy_rain':                  -9.0,   # >10mm — HPN 10.4mm / 3-goal threshold
    'moderate_wind':               -2.8,   # 20–29 km/h
    'moderate_wind + dew':         -4.5,
    'strong_wind':                 -6.0,   # 30–39 km/h (raised from -5.0)
    'very_strong_wind':            -8.0,   # ≥40 km/h (raised from -6.6)
    'light_rain + dew':            -6.0,
    'heavy_rain + strong_wind':    -9.5,
    'extreme':                     -9.5,   # ≥40 km/h + heavy rain or dew
}

AFL_TOTALS_DELTA_CAP = -9.5    # raised from -9.0


# ---------------------------------------------------------------------------
# Condition classification — AFL-specific thresholds
# ---------------------------------------------------------------------------

def _classify_afl_condition(
    precip_mm: float,
    wind_kmh: float,
    temp_c: float,
    dew_risk: bool,
    wind_venue_factor: float = 1.0,
) -> tuple:
    """
    Classify weather into an AFL condition_type and return the totals_delta.

    Priority order (most severe first):
        1.  extreme           wind >= 40 km/h AND (heavy rain OR dew)
        2.  heavy_rain + strong_wind
        3.  very_strong_wind  wind >= 40 km/h
        4.  heavy_rain        precip > 10 mm
        5.  moderate_rain     precip 5–10 mm
        6.  strong_wind       wind 30–39 km/h
        7.  light_rain + dew
        8.  moderate_wind + dew
        9.  moderate_wind     wind 20–29 km/h
       10.  light_rain        precip 0–5 mm
       11.  dew
       12.  cold              temp < 5°C (no meaningful rain/wind)
       13.  clear

    Rain tiers (updated from 2mm boundary):
        light:    0 < precip <= 5mm
        moderate: 5 < precip <= 10mm
        heavy:    precip > 10mm

    Wind venue factor: pass 1.1 for MCG to account for documented wind swirl.
    Only applied to wind-dominant conditions (not rain-dominant).

    Returns (condition_type: str, totals_delta: float).
    """
    heavy    = precip_mm > 10.0
    moderate = 5.0 < precip_mm <= 10.0
    light    = 0.0 < precip_mm <= 5.0
    very_strong = wind_kmh >= 40.0
    strong      = 30.0 <= wind_kmh < 40.0
    mod_wind    = 20.0 <= wind_kmh < 30.0
    cold        = temp_c < 5.0

    if very_strong and (heavy or dew_risk):
        ct = 'extreme'
    elif (heavy or moderate) and (strong or very_strong):
        ct = 'heavy_rain + strong_wind'
    elif very_strong:
        ct = 'very_strong_wind'
    elif heavy:
        ct = 'heavy_rain'
    elif moderate:
        ct = 'moderate_rain'
    elif strong:
        ct = 'strong_wind'
    elif light and dew_risk:
        ct = 'light_rain + dew'
    elif mod_wind and dew_risk:
        ct = 'moderate_wind + dew'
    elif mod_wind:
        ct = 'moderate_wind'
    elif light:
        ct = 'light_rain'
    elif dew_risk:
        ct = 'dew'
    elif cold:
        ct = 'cold'
    else:
        ct = 'clear'

    raw_delta = AFL_CONDITION_DELTAS[ct]

    # Apply venue wind factor to wind-dominant conditions
    wind_conditions = {
        'moderate_wind', 'moderate_wind + dew', 'strong_wind',
        'very_strong_wind', 'extreme',
    }
    if wind_venue_factor != 1.0 and ct in wind_conditions:
        raw_delta = raw_delta * wind_venue_factor

    delta = max(AFL_TOTALS_DELTA_CAP, raw_delta)
    return ct, delta


# ---------------------------------------------------------------------------
# Dew risk — AFL night game logic  (thresholds updated)
# ---------------------------------------------------------------------------

def _compute_afl_dew_risk(kickoff: str, temp_c: float, dew_point_c: float) -> bool:
    """
    Return True when AFL dew conditions are met:
        1. Night game — kickoff at or after 18:30 local time
        2. dew_point_c > 12.0 °C   (raised from 10°C — fewer false positives)
        3. (temp_c - dew_point_c) < 5.0 °C  (raised from 4°C — broader spread)

    Relevant for MCG, Gabba, Adelaide Oval night games April–August.
    Not relevant for Marvel Stadium (roof can close) or Optus Stadium (dry Perth nights).
    """
    if temp_c is None or dew_point_c is None:
        return False
    try:
        dt = datetime.fromisoformat(kickoff)
        night = dt.hour > 18 or (dt.hour == 18 and dt.minute >= 30)
    except (ValueError, TypeError):
        try:
            h, m = kickoff.split(':')
            h_int = int(h)
            night = h_int > 18 or (h_int == 18 and int(m) >= 30)
        except Exception:
            night = False
    spread = temp_c - dew_point_c
    return night and dew_point_c > 12.0 and spread < 5.0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_t7(
    weather: dict,
    kickoff: str,
    max_total_delta: float = 9.5,
    wind_venue_factor: float = 1.0,
) -> dict:
    """
    Compute AFL Tier 7 weather adjustments.

    Game-day only — not applied during mid-week model runs.

    Args:
        weather: dict with any of:
                    precip_mm    float  precipitation in mm
                    wind_kmh     float  sustained wind speed km/h
                    temp_c       float  temperature in °C
                    dew_point_c  float  dew point in °C (for night dew check)
                    dew_risk     bool   override auto-computed dew risk
                 Pass empty dict {} for clear/unknown conditions.
        kickoff: ISO datetime string ('2026-04-25T15:20:00') or 'HH:MM'.
                 Used for the night-game dew risk check.
        max_total_delta: AFL cap from afl.yaml tier8.weather.max_total_delta.
                         Defaults to 9.5.
        wind_venue_factor: multiplier on wind delta for venue-specific wind effects.
                           Pass 1.1 for MCG (documented swirl effect, judgment-based).

    Returns dict:
        t7_handicap      float  always 0.0 (weather is totals-only in AFL)
        t7_totals        float  negative or 0.0
        condition_type   str    classified condition label
        dew_risk         bool
        signals          dict   full debug breakdown
    """
    if not weather:
        return {
            't7_handicap':    0.0,
            't7_totals':      0.0,
            'condition_type': 'clear',
            'dew_risk':       False,
            'signals': {'reason': 'no weather data provided — assuming clear'},
        }

    precip_mm   = float(weather.get('precip_mm',    0.0) or 0.0)
    wind_kmh    = float(weather.get('wind_kmh',     0.0) or 0.0)
    temp_c      = float(weather.get('temp_c',      15.0) or 15.0)
    dew_point_c = float(weather.get('dew_point_c', 10.0) or 10.0)

    # Dew risk: use override if supplied, otherwise compute from conditions
    dew_risk_override = weather.get('dew_risk')
    if dew_risk_override is not None:
        dew_risk = bool(dew_risk_override)
    else:
        dew_risk = _compute_afl_dew_risk(kickoff, temp_c, dew_point_c)

    condition_type, totals_delta = _classify_afl_condition(
        precip_mm, wind_kmh, temp_c, dew_risk, wind_venue_factor,
    )

    # Apply config cap
    totals_delta = max(-abs(max_total_delta), totals_delta)

    return {
        't7_handicap':    0.0,
        't7_totals':      round(totals_delta, 2),
        'condition_type': condition_type,
        'dew_risk':       dew_risk,
        'signals': {
            'precip_mm':          precip_mm,
            'wind_kmh':           wind_kmh,
            'temp_c':             temp_c,
            'dew_point_c':        dew_point_c,
            'dew_risk':           dew_risk,
            'wind_venue_factor':  wind_venue_factor,
            'condition_type':     condition_type,
            'totals_delta':       round(totals_delta, 2),
            'cap_applied':        max_total_delta,
        },
    }
