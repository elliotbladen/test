# pricing/afl_tier4_venue.py
# =============================================================================
# AFL Tier 4 — Venue layer
# =============================================================================
#
# Signals:
#   4A: Team fortress    — team-specific home win rate vs league baseline
#   4B: Venue scoring    — venue total deviation from league average
#
# T1 (rules baseline) uses only ELO and team scoring rates — no venue adjustment.
# T4 is the sole source of venue signals in the pricing stack:
#   - Team × venue interaction (e.g. Geelong specifically at GMHBA)
#   - Venue scoring profile (how a ground affects total points scored)
#
# Positive delta = home team advantage.
# All signals have individual caps; total T4 capped at ±5 pts handicap, ±5 pts totals.
#
# Sources: 2018-2026 Footywire data, min 20 home games at venue.
# League avg home win rate baseline: 56.3%
# =============================================================================

# ── Fortress ratings ──────────────────────────────────────────────────────────
# Derived from: team home win% at this venue vs 56.3% league baseline
# Formula: (win_pct - 0.563) * 20  → ~1 pt per 5% above baseline
# Positive = strong home fortress. Negative = below-average at this venue.
# Only included where n >= 20 games and effect >= 1.0 pt (i.e. ~5% deviation).
#
# (team_name, venue_name): fortress_pts
#
FORTRESS_RATINGS = {
    # Strong fortresses (2018-2026 data, baseline 56-57%)
    ('Sydney Swans',                  'SCG'):                  +3.0,   # 73% win rate — strongest in modern era
    ('Geelong Cats',                  'GMHBA Stadium'):        +3.0,   # 72% win rate (was +4.5, that was pre-2018 era)
    ('Geelong Cats',                  'Kardinia Park'):        +3.0,   # alias
    ('Greater Western Sydney Giants', 'ENGIE Stadium'):        +2.5,   # 69% win rate
    ('Collingwood Magpies',           'MCG'):                  +2.5,   # 69% win rate
    ('Brisbane Lions',                'The Gabba'):            +2.0,   # 67% win rate
    ('Brisbane Lions',                'Gabba'):                +2.0,   # alias
    ('Port Adelaide Power',           'Adelaide Oval'):        +1.5,   # 61-62% win rate
    ('Hawthorn Hawks',                'UTAS Stadium'):         +1.0,   # fortress largely gone — 46.7% recent (was +3.5)
    ('Hawthorn Hawks',                'Blundstone Arena'):     +1.0,   # alias
    # Neutral / shared venues — no team-specific bonus beyond normal home advantage
    # Negative fortresses (team home win rate meaningfully below league baseline)
    ('West Coast Eagles',             'Optus Stadium'):        -3.0,   # 23% home win rate 2022-26 — dire
    ('Gold Coast Suns',               'People First Stadium'): -4.0,   # ~34% home win rate since 2018
}

# ── Venue scoring profiles ────────────────────────────────────────────────────
# Residual totals deviation from league avg (2018-2026), scaled at 30%.
# (The ML already captures ~70% via venue_avg_total feature.)
# Positive = higher scoring venue. Negative = lower scoring.
#
# League avg total: 161.4 pts
# Raw deviations (from data):
#   ENGIE Stadium:        +6.7  →  *0.30 = +2.0
#   Marvel Stadium:       +6.3  →  *0.30 = +1.9
#   Ninja Stadium:        +5.1  →  *0.30 = +1.5
#   Manuka Oval:          +4.0  →  *0.30 = +1.2
#   GMHBA Stadium:        +2.5  →  *0.30 = +0.8
#   SCG:                  +1.7  →  *0.30 = +0.5
#   MCG:                  +0.9  →  *0.30 = +0.3  (negligible — skip)
#   Adelaide Oval:        -1.7  →  *0.30 = -0.5  (negligible — skip)
#   Optus Stadium:        -3.1  →  *0.30 = -0.9
#   Gabba:                -3.2  →  *0.30 = -1.0
#   UTAS Stadium:         -7.4  →  *0.30 = -2.2
#   People First Stadium: -15.3 →  *0.30 = -4.6  (capped at -5)
#
VENUE_SCORING_PROFILE = {
    'ENGIE Stadium':          +2.0,
    'Marvel Stadium':         +1.9,
    'Marvel':                 +1.9,   # alias
    'Docklands':              +1.9,   # alias
    'Ninja Stadium':          +1.5,
    'Manuka Oval':            +1.2,
    'GMHBA Stadium':          +1.5,   # updated: modern era data supports +1.5 (was +0.8)
    'Kardinia Park':          +1.5,   # alias
    'SCG':                    +0.5,
    'Optus Stadium':          -0.9,
    'The Gabba':              -1.0,
    'Gabba':                  -1.0,   # alias
    'UTAS Stadium':           -1.5,   # historical avg ~165 pts (near league avg); -2.2 was too punishing
    'Blundstone Arena':       -1.5,   # alias
    'People First Stadium':   -4.6,
    'Cazalys Stadium':        -3.0,   # Cairns — small, hot, affects scoring
    'TIO Stadium':            -3.0,   # Darwin — heat/humidity effect
    'Traeger Park':           -3.0,   # Alice Springs — thin air, heat
}

# Caps
T4_HANDICAP_CAP = 5.0
T4_TOTALS_CAP   = 5.0


# ── Signal functions ──────────────────────────────────────────────────────────

def signal_4a_fortress(home: str, away: str, venue: str) -> dict:
    """
    Team-specific fortress adjustment.
    Looks up home team's record at this venue vs league baseline.
    Positive = home team has a proven fortress here.
    """
    home_pts = FORTRESS_RATINGS.get((home, venue), 0.0)
    away_pts = FORTRESS_RATINGS.get((away, venue), 0.0)

    # If away team has a fortress here, that's a home-team disadvantage
    pts = home_pts - away_pts
    pts = max(-T4_HANDICAP_CAP, min(T4_HANDICAP_CAP, pts))

    notes = []
    if home_pts != 0.0:
        notes.append(f'{home.split()[-1]} fortress ({home_pts:+.1f})')
    if away_pts != 0.0:
        notes.append(f'{away.split()[-1]} away at own fortress ({away_pts:+.1f})')

    return {
        'signal':    '4A_fortress',
        'home_pts':  home_pts,
        'away_pts':  away_pts,
        'pts':       round(pts, 2),
        'note':      ' | '.join(notes),
        'applied':   pts != 0.0,
    }


def signal_4b_venue_scoring(venue: str) -> dict:
    """
    Residual venue scoring profile — totals adjustment only.
    Positive = higher scoring venue. Negative = lower scoring.
    """
    pts = VENUE_SCORING_PROFILE.get(venue, 0.0)
    pts = max(-T4_TOTALS_CAP, min(T4_TOTALS_CAP, pts))

    return {
        'signal':  '4B_venue_scoring',
        'venue':   venue,
        'pts':     round(pts, 2),
        'applied': pts != 0.0,
    }


# ── Master function ───────────────────────────────────────────────────────────

def compute_t4(home: str, away: str, venue: str) -> dict:
    """
    Compute all T4 venue signals and return combined result.

    Returns:
        t4_handicap : float  — total handicap adjustment (home perspective)
        t4_totals   : float  — totals adjustment (venue scoring profile)
        signals     : list   — per-signal breakdown for audit
    """
    s4a = signal_4a_fortress(home, away, venue)
    s4b = signal_4b_venue_scoring(venue)

    t4_handicap = max(-T4_HANDICAP_CAP, min(T4_HANDICAP_CAP, s4a['pts']))
    t4_totals   = max(-T4_TOTALS_CAP,   min(T4_TOTALS_CAP,   s4b['pts']))

    return {
        't4_handicap': round(t4_handicap, 2),
        't4_totals':   round(t4_totals,   2),
        'signals':     [s4a, s4b],
    }
