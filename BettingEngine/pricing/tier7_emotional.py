# pricing/tier7_emotional.py
# =============================================================================
# Tier 7 — Emotional / Human Context layer
# =============================================================================
#
# NRL is a high-emotion sport. Certain off-field and narrative contexts
# materially lift a team's effort and performance on the day.
#
# Supported flag types:
#   milestone        — 100th/200th/300th game, debut, captain's first game
#   new_coach        — first game under a new head coach (team lifts hard)
#   star_return      — elite/key player back from a long absence
#   shame_blowout    — team coming off a 30+ point loss (bounce-back energy)
#   origin_boost     — players just returned from Origin camp, peak condition
#   farewell         — player or coach farewell game / final season
#   personal_tragedy — team rallying around personal adversity
#   rivalry_derby    — recognized derby/rivalry fixture (crowd intensity)
#   must_win         — backs-against-the-wall finals-position game
#
# Each flag has a strength: minor (0.5×), normal (1.0×), major (1.5×).
# Most flags boost one team's margin over the other.
# A few also lift the total — emotional games tend to produce more scoring.
#
# Pricing rules:
#   1. For each team, sum (base_margin_pts[flag_type] * strength_mult)
#   2. Clamp per-team margin sum at max_home/away_points_delta
#   3. handicap_delta = home_margin_sum - away_margin_sum
#      Positive = home favoured; negative = away favoured.
#   4. totals_delta = sum of totals_pts contributions across both teams,
#      capped at max_totals_delta. Totals only go UP (emotional games
#      score more, not less).
#
# Expect 0–2 games per round to fire this tier. It is dormant most weeks.
# =============================================================================

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strength_mult(strength: str, config: dict) -> float:
    return float(config.get('strength_multipliers', {}).get(strength, 1.0))


def _flag_margin_pts(flag_type: str, config: dict) -> float:
    return float(config.get('flag_margin_pts', {}).get(flag_type, 0.0))


def _flag_totals_pts(flag_type: str, config: dict) -> float:
    return float(config.get('flag_totals_pts', {}).get(flag_type, 0.0))


# ---------------------------------------------------------------------------
# Main pricing function (called by price_round.py / run.py)
# ---------------------------------------------------------------------------

def compute_emotional_adjustments(
    home_flags: list,
    away_flags: list,
    config: dict,
) -> dict:
    """
    Compute Tier 7 emotional adjustments from pre-loaded emotional_flags rows.

    Args:
        home_flags: list of emotional_flags rows for the home team this match.
                    Each must have: flag_type (str), flag_strength (str).
                    Optional: player_name, notes.
        away_flags: same for the away team.
        config:     tiers.yaml['tier7_emotional'] section.

    Returns dict with:
        handicap_delta   float  positive = home team gets the emotional edge
        totals_delta     float  always >= 0 (emotional games score more)
        _debug           dict   all intermediate values for logging
    """
    if not config.get('enabled', True):
        return {
            'handicap_delta': 0.0,
            'totals_delta':   0.0,
            '_debug': {'reason': 'tier7_emotional disabled'},
        }

    max_h = float(config.get('max_home_points_delta', 2.5))
    max_a = float(config.get('max_away_points_delta', 2.5))
    max_t = float(config.get('max_totals_delta', 1.5))

    home_margin_raw = 0.0
    away_margin_raw = 0.0
    totals_raw      = 0.0

    fired_home = []
    fired_away = []

    for flag in home_flags:
        ftype    = str(flag.get('flag_type', '')).strip()
        strength = str(flag.get('flag_strength', 'normal')).strip()
        mult = _strength_mult(strength, config)
        mp   = _flag_margin_pts(ftype, config) * mult
        tp   = _flag_totals_pts(ftype, config) * mult
        home_margin_raw += mp
        totals_raw      += tp
        fired_home.append({
            'flag_type':   ftype,
            'strength':    strength,
            'player':      flag.get('player_name'),
            'notes':       flag.get('notes'),
            'margin_pts':  round(mp, 3),
            'totals_pts':  round(tp, 3),
        })

    for flag in away_flags:
        ftype    = str(flag.get('flag_type', '')).strip()
        strength = str(flag.get('flag_strength', 'normal')).strip()
        mult = _strength_mult(strength, config)
        mp   = _flag_margin_pts(ftype, config) * mult
        tp   = _flag_totals_pts(ftype, config) * mult
        away_margin_raw += mp
        totals_raw      += tp
        fired_away.append({
            'flag_type':   ftype,
            'strength':    strength,
            'player':      flag.get('player_name'),
            'notes':       flag.get('notes'),
            'margin_pts':  round(mp, 3),
            'totals_pts':  round(tp, 3),
        })

    # Clamp per-team margin contribution before taking the difference
    home_margin = max(-max_h, min(max_h, home_margin_raw))
    away_margin = max(-max_a, min(max_a, away_margin_raw))

    # handicap_delta: positive means home team has the emotional edge
    handicap_delta = home_margin - away_margin

    # Totals only go up — emotional intensity never suppresses scoring
    totals_delta = min(max_t, max(0.0, totals_raw))

    logger.debug(
        "T7 emotional: home_flags=%d away_flags=%d "
        "home_margin=%.2f away_margin=%.2f "
        "hcap_delta=%.2f totals_delta=%.2f",
        len(home_flags), len(away_flags),
        home_margin, away_margin,
        handicap_delta, totals_delta,
    )

    return {
        'handicap_delta': round(handicap_delta, 3),
        'totals_delta':   round(totals_delta, 3),
        '_debug': {
            'home_flags':       fired_home,
            'away_flags':       fired_away,
            'home_margin_raw':  round(home_margin_raw, 3),
            'away_margin_raw':  round(away_margin_raw, 3),
            'home_margin':      round(home_margin, 3),
            'away_margin':      round(away_margin, 3),
            'totals_raw':       round(totals_raw, 3),
        },
    }


# ---------------------------------------------------------------------------
# Engine shim — engine.py calls this via _try_tier
# Returns [] until the engine loads emotional_flags from the DB directly.
# price_round.py / run.py use compute_emotional_adjustments() above instead.
# ---------------------------------------------------------------------------

def compute_emotional_adjustments_stub(match: dict, context: dict, config: dict) -> list:
    """Stub for engine.py _try_tier loop. Returns empty list."""
    return []
