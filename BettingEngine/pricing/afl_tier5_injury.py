# pricing/afl_tier5_injury.py
# =============================================================================
# AFL Tier 5 — Injury layer
# =============================================================================
#
# Signals:
#   5A: Key forward out    — goal-kicker absent, team scores drop
#   5B: Ruck out           — hitouts/clearances affected, both teams impacted
#   5C: Key defender out   — intercept defender absent, opposition scores more
#   5D: Midfielder out     — disposal/clearance capacity reduced
#   5E: Compound           — extra penalty when 2+ key players from same team out
#
# Input: INJURIES dict — updated manually each round before pricing.
# Format: list of {'player': str, 'position': str, 'quality': str}
#
# Positions: 'key_forward', 'key_defender', 'ruck', 'midfielder', 'winger', 'utility'
# Quality:   'elite', 'good', 'average', 'depth'
#
# Effects on handicap (home perspective):
#   Home team out → negative (reduces home margin)
#   Away team out → positive (increases home margin)
#
# Effects on totals:
#   Key forward out → lower total (fewer goals)
#   Ruck out        → slightly lower total (fewer clearances)
#   Key defender out → slightly higher total (opposition enters 50 more freely)
#
# All adjustments are additive to the T1-T4 baseline.
# Total T5 capped at ±8 pts handicap, ±6 pts totals.
# =============================================================================

# ── Points impact per player out ─────────────────────────────────────────────
# handicap_pts: impact on the team's margin (negative = team scores less)
# totals_pts:   impact on game total (negative = game total drops)
#
IMPACT_TABLE = {
    #                                  hdcp   totals   notes
    ('key_forward',  'elite'):   (-5.0, -4.0),   # 3+ avg goals, team loses primary scorer
    ('key_forward',  'good'):    (-3.5, -2.5),   # 2-3 avg goals
    ('key_forward',  'average'): (-2.0, -1.5),   # squad player, some impact
    ('key_forward',  'depth'):   (-0.5, -0.5),   # minimal impact

    ('ruck',         'elite'):   (-3.5, -2.0),   # #1 ruck losing hitouts/clearances
    ('ruck',         'good'):    (-2.0, -1.0),
    ('ruck',         'average'): (-1.0, -0.5),
    ('ruck',         'depth'):   (-0.5,  0.0),

    ('key_defender', 'elite'):   (-2.5, +1.5),   # elite intercept defender absent → opposition scores more
    ('key_defender', 'good'):    (-1.5, +1.0),
    ('key_defender', 'average'): (-0.5, +0.5),
    ('key_defender', 'depth'):   ( 0.0,  0.0),

    ('midfielder',   'elite'):   (-3.5, -1.5),   # elite inside mid (Oliver, Cripps) — clearance engine; was -2.5 (too low)
    ('midfielder',   'good'):    (-2.0, -0.5),
    ('midfielder',   'average'): (-0.5, -0.5),
    ('midfielder',   'depth'):   ( 0.0,  0.0),

    ('winger',       'elite'):   (-1.5, -0.5),
    ('winger',       'good'):    (-1.0, -0.5),
    ('winger',       'average'): (-0.5,  0.0),
    ('winger',       'depth'):   ( 0.0,  0.0),

    ('utility',      'elite'):   (-1.5, -0.5),
    ('utility',      'good'):    (-1.0, -0.5),
    ('utility',      'average'): (-0.5,  0.0),
    ('utility',      'depth'):   ( 0.0,  0.0),
}

# Compound effect: when 2+ key players (forward/ruck/midfielder) are out from
# same team — impact is SUBADDITIVE (team restructures, can't be exploited in 2 places).
# Research: 2 players out ≈ 70-85% of purely additive sum, not 115%.
COMPOUND_THRESHOLD = 2       # minimum outs to trigger dampening
COMPOUND_DAMPENER  = 0.85    # multiply summed impact by 0.85 when 2+ key players out

T5_HANDICAP_CAP = 8.0
T5_TOTALS_CAP   = 6.0

KEY_POSITIONS = {'key_forward', 'ruck', 'midfielder'}


def _player_impact(position: str, quality: str) -> tuple[float, float]:
    """Return (handicap_pts, totals_pts) for a single player out."""
    return IMPACT_TABLE.get((position, quality), (0.0, 0.0))


def _team_injury_effect(outs: list[dict]) -> tuple[float, float, list]:
    """
    Compute total handicap and totals impact for one team's injury list.
    outs: [{'player': str, 'position': str, 'quality': str}, ...]
    Returns (hdcp_pts, tot_pts, breakdown_list) — all as negative numbers
    (team is losing players, so impact is negative for them).
    """
    hdcp_sum = 0.0
    tot_sum  = 0.0
    breakdown = []
    key_out_count = 0

    for p in outs:
        pos  = p.get('position', 'utility')
        qual = p.get('quality',  'average')
        h, t = _player_impact(pos, qual)
        hdcp_sum += h
        tot_sum  += t
        if pos in KEY_POSITIONS and qual in ('elite', 'good'):
            key_out_count += 1
        breakdown.append({
            'player':   p.get('player', 'unknown'),
            'position': pos,
            'quality':  qual,
            'hdcp_pts': round(h, 1),
            'tot_pts':  round(t, 1),
        })

    # Compound dampening: multiple key absences are subadditive — team restructures
    if key_out_count >= COMPOUND_THRESHOLD:
        hdcp_sum = hdcp_sum * COMPOUND_DAMPENER
        tot_sum  = tot_sum  * COMPOUND_DAMPENER

    return (round(hdcp_sum, 2),
            round(tot_sum,  2),
            breakdown,
            key_out_count >= COMPOUND_THRESHOLD)


# ── Master function ───────────────────────────────────────────────────────────

def compute_t5(home_outs: list[dict], away_outs: list[dict]) -> dict:
    """
    Compute T5 injury adjustment.

    Args:
        home_outs: list of injured home team players (dicts with position/quality)
        away_outs: list of injured away team players

    Returns:
        t5_handicap : float  — net pts adjustment (home perspective)
        t5_totals   : float  — net totals adjustment
        home_impact : dict   — breakdown for home team
        away_impact : dict   — breakdown for away team
        signals     : list   — per-player breakdown for audit
    """
    home_hdcp, home_tot, home_bd, home_compound = _team_injury_effect(home_outs)
    away_hdcp, away_tot, away_bd, away_compound = _team_injury_effect(away_outs)

    # From home perspective:
    #   home team loses player → home_hdcp is negative → reduces home margin
    #   away team loses player → away_hdcp is negative → but benefits home team (positive)
    net_handicap = -home_hdcp + (-away_hdcp * -1)   # home loses: bad. away loses: good.
    # Simplify: net = away_impact (positive for home) - home_impact (negative for home)
    net_handicap = (-away_hdcp) - (-home_hdcp)
    net_handicap = (-away_hdcp) + home_hdcp          # home_hdcp is negative; away_hdcp negative but inverted

    # Cleaner:
    # home team injury → home team weaker → net margin drops (negative)
    # away team injury → away team weaker → net margin rises (positive)
    net_handicap = home_hdcp - away_hdcp   # both negative; home_hdcp negative = home loses margin

    # Totals: both teams' total impact combine (both additive to game total)
    net_totals = home_tot + away_tot

    net_handicap = max(-T5_HANDICAP_CAP, min(T5_HANDICAP_CAP, net_handicap))
    net_totals   = max(-T5_TOTALS_CAP,   min(T5_TOTALS_CAP,   net_totals))

    return {
        't5_handicap': round(net_handicap, 2),
        't5_totals':   round(net_totals,   2),
        'home_impact': {
            'hdcp':     round(home_hdcp, 2),
            'tot':      round(home_tot,  2),
            'compound': home_compound,
            'players':  home_bd,
        },
        'away_impact': {
            'hdcp':     round(away_hdcp, 2),
            'tot':      round(away_tot,  2),
            'compound': away_compound,
            'players':  away_bd,
        },
        'signals': [{
            'signal': '5_injury',
            'home_hdcp': round(home_hdcp, 2),
            'away_hdcp': round(away_hdcp, 2),
            'home_tot':  round(home_tot, 2),
            'away_tot':  round(away_tot, 2),
            'net_hdcp':  round(net_handicap, 2),
            'net_tot':   round(net_totals,   2),
            'pts':       round(net_handicap, 2),
            'applied':   net_handicap != 0.0 or net_totals != 0.0,
        }],
    }
