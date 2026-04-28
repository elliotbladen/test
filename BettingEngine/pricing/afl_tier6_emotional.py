# pricing/afl_tier6_emotional.py
# =============================================================================
# AFL Tier 6 — Emotional / Human Context layer
# =============================================================================
#
# AFL crowds (60-100k) amplify emotional swings significantly more than NRL.
# All magnitudes are calibrated for the AFL scoring environment (~170-185 pts).
#
# SUPPORTED FLAG TYPES
# ─────────────────────────────────────────────────────────────────────────────
#   milestone        — career appearance milestone (see grading table below)
#   new_coach        — first game under a new head coach
#   star_return      — elite/key player back from 6+ weeks absent
#   shame_blowout    — coming off a 60+ point loss  ← AFL threshold (not NRL's 20)
#   farewell         — player or coach farewell / final season game
#   personal_tragedy — team rallying around personal adversity
#   rivalry_derby    — recognised AFL derby fixture
#   must_win         — finals-positioning desperation game
#   club_drama       — active trade/contract saga consuming org bandwidth (suppressive)
#
# NOTE: no origin_boost — State of Origin does not exist in AFL.
# NOTE: T6 is used for emotional in AFL because T6 (umpire) is disabled.
#       Equivalent to T7 in NRL.
#
# MILESTONE GRADING
# ─────────────────────────────────────────────────────────────────────────────
#   Game number        Strength   Margin pts   Notes
#   Debut / 50th /
#   150th / 250th  →  minor      1.0 pt       mid-tier — acknowledged, not celebrated
#   100th / 200th  →  normal     2.0 pts      proper milestone — guard of honour
#   300th+         →  major      3.0 pts      elite career landmark
#
#   Use the milestone_flag() helper below — it sets strength automatically.
#
# RIVALRY DERBY EXAMPLES
# ─────────────────────────────────────────────────────────────────────────────
#   ANZAC Day (Essendon vs Collingwood)   → major  (largest regular-season event)
#   Showdown (Adelaide vs Port Adelaide)  → major
#   WA Derby (Eagles vs Dockers)          → major
#   MCG blockbusters (Collingwood/Richmond/Melbourne)  → normal
#   Other recognised rivalries            → normal or minor
#
# SHAME BLOWOUT NOTE
# ─────────────────────────────────────────────────────────────────────────────
#   In AFL a "shame blowout" requires a 60+ point losing margin (10 goals).
#   This is the genuine humiliation threshold in AFL. Do NOT apply this flag
#   for losses of 30-50 pts — those are normal AFL defeats.
#
# POINT SUMMARY  (at normal strength × 1.0)
# ─────────────────────────────────────────────────────────────────────────────
#   Flag               Margin Δ   Totals Δ   Evidence quality
#   milestone            +1.5       +0.5      Weak — umpire bias data, not perf uplift
#   new_coach            +2.5       +0.0      Moderate — AFL caretaker data (47% vs 28% win rate)
#   star_return          +3.5       +1.5      Good — injury burden study (12% table position var)
#   shame_blowout        +1.5       +0.0      Weak — no AFL-specific data; cross-sport only
#   farewell             +1.5       +0.5      Weak — narrative only
#   personal_tragedy     +2.5       +0.0      None — judgement call; grief can suppress scoring
#   rivalry_derby        +1.5       +0.0      Good — derbies are empirically lower-scoring (170 vs 178 avg)
#   must_win             +2.0       +0.5      Moderate — MoS late-season motivation finding
#   club_drama           -2.0       +0.0      Moderate — anecdotal AFL cases; org bandwidth suppression
#
# CAPS
# ─────────────────────────────────────────────────────────────────────────────
#   Per-team margin contribution   capped at  ±5.0 pts
#   Net totals delta               capped at  +3.0 pts  (totals never go DOWN)
#
# DATA ENTRY
# ─────────────────────────────────────────────────────────────────────────────
#   Populate EMOTIONAL_FLAGS dict in prepare_afl_round.py before each round.
#   Use the milestone_flag() helper for milestones — it auto-grades strength.
#   Use plain dicts for all other flag types.
#
#   Example:
#       from pricing.afl_tier6_emotional import milestone_flag
#       EMOTIONAL_FLAGS = {
#           8: {
#               'Essendon Bombers': [
#                   {'flag_type': 'rivalry_derby', 'flag_strength': 'major',
#                    'player_name': None, 'notes': 'ANZAC Day vs Collingwood'},
#               ],
#               'Collingwood Magpies': [
#                   {'flag_type': 'rivalry_derby', 'flag_strength': 'major',
#                    'player_name': None, 'notes': 'ANZAC Day vs Essendon'},
#               ],
#               'Brisbane Lions': [
#                   milestone_flag('Lachie Neale', 200),
#               ],
#           }
#       }
# =============================================================================

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pricing.tier7_emotional import compute_emotional_adjustments


# ---------------------------------------------------------------------------
# AFL-specific config
# ---------------------------------------------------------------------------
AFL_T6_CONFIG = {
    'enabled': True,

    # Margin points at normal (1.0×) strength.
    # Multiply by strength_multipliers below for minor/major variants.
    'flag_margin_pts': {
        'milestone':        1.5,   # was 2.0 — umpire bias ≠ performance uplift
        'new_coach':        2.5,
        'star_return':      3.5,
        'shame_blowout':    1.5,   # was 2.0 — no AFL-specific data; reduced
        'farewell':         1.5,
        'personal_tragedy': 2.5,   # was 3.0 — no quantitative evidence; reduced
        'rivalry_derby':    1.5,
        'must_win':         2.0,
        'club_drama':      -2.0,   # suppressive — trade/contract saga consuming org bandwidth
    },

    # Totals points at normal (1.0×) strength.
    'flag_totals_pts': {
        'milestone':        0.5,
        'new_coach':        0.0,   # tactical bounce, not a scoring environment shift
        'star_return':      1.5,   # returning key forward → more scoring shots
        'shame_blowout':    0.0,   # was 1.0 — response games are defensive, not high-scoring
        'farewell':         0.5,
        'personal_tragedy': 0.0,   # grief can suppress open play
        'rivalry_derby':    0.0,   # was 1.5 — derbies are empirically lower-scoring (Showdown/WA Derby avg ~170 vs 178)
        'must_win':         0.5,   # was 1.0 — weakly supported
        'club_drama':       0.0,
    },

    # Strength multipliers
    'strength_multipliers': {
        'minor':  0.5,   # debut / 50th / 150th / 250th  → ×0.5 of base
        'normal': 1.0,   # 100th / 200th                 → ×1.0 of base
        'major':  1.5,   # 300th+ / ANZAC Day / Showdown → ×1.5 of base
    },

    # Per-team margin contribution cap (before taking home - away difference)
    'max_home_points_delta': 5.0,
    'max_away_points_delta': 5.0,

    # Total tier totals output cap
    'max_totals_delta': 3.0,
}


# ---------------------------------------------------------------------------
# Milestone strength table
# ─────────────────────────────────────────────────────────────────────────────
# Maps game number → strength label.
# Rounds DOWN to the nearest milestone bucket.
# ---------------------------------------------------------------------------
def _milestone_strength(game_number: int) -> str:
    """
    Return the correct strength label for an AFL milestone game.

    Grading:
        300+        → major   (3.0 pts)
        200 / 100   → normal  (2.0 pts)
        250 / 150 / 50 / debut (1st game)  → minor  (1.0 pt)
    """
    if game_number >= 300:
        return 'major'
    if game_number in (100, 200):
        return 'normal'
    # 50, 150, 250 and debut (treat game_number=1 as debut)
    return 'minor'


def milestone_flag(player_name: str, game_number: int, notes: str = '') -> dict:
    """
    Build a correctly-graded milestone flag dict for EMOTIONAL_FLAGS data entry.

    Args:
        player_name:  Player's full name.
        game_number:  Career AFL game number for this match.
        notes:        Optional additional context string.

    Returns a flag dict ready for use in EMOTIONAL_FLAGS.

    Example:
        milestone_flag('Lachie Neale', 200)
        # → {'flag_type': 'milestone', 'flag_strength': 'normal',
        #     'player_name': 'Lachie Neale', 'notes': '200th AFL game'}
    """
    strength = _milestone_strength(game_number)
    auto_note = f'{game_number}{"st" if game_number == 1 else "th"} AFL game'
    return {
        'flag_type':     'milestone',
        'flag_strength': strength,
        'player_name':   player_name,
        'notes':         notes or auto_note,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_t6(home_flags: list, away_flags: list) -> dict:
    """
    Compute AFL Tier 6 emotional adjustments.

    Args:
        home_flags: list of flag dicts for the home team.
                    Each dict must have 'flag_type' and 'flag_strength'.
                    Optional: 'player_name', 'notes'.
                    Use milestone_flag() helper for milestone entries.
        away_flags: same for the away team.

    Returns dict:
        t6_handicap  float  positive = home emotional edge, negative = away edge
        t6_totals    float  always >= 0.0
        signals      dict   full debug breakdown (fired flags, raw values, clamps)
    """
    result = compute_emotional_adjustments(home_flags, away_flags, AFL_T6_CONFIG)
    return {
        't6_handicap': result['handicap_delta'],
        't6_totals':   result['totals_delta'],
        'signals':     result['_debug'],
    }
