# pricing/afl_tier3_situational.py
# =============================================================================
# AFL Tier 3 — Situational / Momentum layer
# =============================================================================
#
# Signals:
#   3A: Rest advantage  — bye / normal / short turnaround matchup matrix
#   3B: Travel burden   — interstate km differential
#   3C: Compound        — short rest AND long travel (extra penalty)
#   3D: Form momentum   — off big win / off big loss angles
#   3E: Occasion        — ANZAC Day crowd effect (home team boost)
#
# All signals are additive to the T1+T2 baseline.
# Positive delta = home team advantage.
# Each signal has its own cap; total T3 capped at ±6 pts.
#
# NOTE: T1 (rules baseline) uses only ELO and team scoring rates — no rest or
# travel adjustment.  T3 is the sole source of rest, travel, and momentum
# signals in the pricing stack.
# =============================================================================

# ── Team home bases (lat, lng) ────────────────────────────────────────────────
TEAM_BASES = {
    'Adelaide Crows':                  (-34.9285, 138.6007),
    'Brisbane Lions':                  (-27.4698, 153.0251),
    'Carlton Blues':                   (-37.8136, 144.9631),
    'Collingwood Magpies':             (-37.8136, 144.9631),
    'Essendon Bombers':                (-37.8136, 144.9631),
    'Fremantle Dockers':               (-31.9505, 115.8605),
    'Geelong Cats':                    (-38.1499, 144.3617),
    'Gold Coast Suns':                 (-28.0167, 153.4000),
    'Greater Western Sydney Giants':   (-33.8688, 151.2093),
    'Hawthorn Hawks':                  (-37.8136, 144.9631),
    'Melbourne Demons':                (-37.8136, 144.9631),
    'North Melbourne Kangaroos':       (-37.8136, 144.9631),
    'Port Adelaide Power':             (-34.9285, 138.6007),
    'Richmond Tigers':                 (-37.8136, 144.9631),
    'St Kilda Saints':                 (-37.8136, 144.9631),
    'Sydney Swans':                    (-33.8688, 151.2093),
    'West Coast Eagles':               (-31.9505, 115.8605),
    'Western Bulldogs':                (-37.8136, 144.9631),
}

# ── Venue coordinates ─────────────────────────────────────────────────────────
VENUE_COORDS = {
    'MCG':              (-37.8200, 144.9836),
    'Marvel Stadium':   (-37.8168, 144.9520),
    'GMHBA Stadium':    (-38.1580, 144.3550),
    'Adelaide Oval':    (-34.9158, 138.5960),
    'Optus Stadium':    (-31.9505, 115.8897),
    'The Gabba':        (-27.4858, 153.0381),
    'SCG':              (-33.8914, 151.2247),
    'UTAS Stadium':     (-41.4545, 147.1347),
    'Manuka Oval':      (-35.3200, 149.1300),
    'Giants Stadium':   (-33.8472, 150.9869),
    'Marvel':           (-37.8168, 144.9520),
    'Docklands':        (-37.8168, 144.9520),
    'Blundstone Arena': (-42.8821, 147.3272),
    'Cazalys Stadium':  (-16.9186, 145.7781),
    'TIO Stadium':      (-12.4634, 130.8456),
    'Mars Stadium':     (-37.5622, 143.8503),
    'Kardinia Park':    (-38.1580, 144.3550),
    'Norwood Oval':     (-34.9200, 138.6300),
    'Traeger Park':     (-23.6980, 133.8807),
}

import math


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlng/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def _travel_km(team: str, venue: str) -> float:
    base   = TEAM_BASES.get(team)
    v_coord = VENUE_COORDS.get(venue)
    if not base or not v_coord:
        return 0.0
    d = _haversine_km(base[0], base[1], v_coord[0], v_coord[1])
    return d if d > 50 else 0.0   # <50 km = effectively home, no travel burden


def _classify_rest(days: int | None) -> str:
    if days is None:
        return 'normal'
    if days <= 6:
        return 'short'
    if days <= 9:
        return 'normal'
    if days <= 13:
        return 'long'
    return 'bye'


# Rest matrix: rows = home rest class, cols = away rest class
# Value = pts advantage to home team from this rest matchup
# Antisymmetric: if home is on short and away is on bye, home is at a disadvantage
#
# Bye edges reduced ~15% vs original — research shows bye advantage is unreliable
# in recent AFL seasons (2023 post-bye teams went 2-10 at one point; effect can reverse).
# Relative rest differential is the key signal; absolute bye bonus is overstated.
_REST_MATRIX = {
    #              away: short  normal  long   bye
    'short':  {'short':  0.0, 'normal': -1.5, 'long': -2.5, 'bye': -3.0},
    'normal': {'short':  1.5, 'normal':  0.0, 'long': -1.0, 'bye': -1.5},
    'long':   {'short':  2.5, 'normal':  1.0, 'long':  0.0, 'bye': -1.0},
    'bye':    {'short':  3.0, 'normal':  1.5, 'long':  1.0, 'bye':  0.0},
}


# ── Signal functions ──────────────────────────────────────────────────────────

def signal_3a_rest(home_rest: int | None, away_rest: int | None) -> dict:
    """Rest matchup matrix."""
    hc = _classify_rest(home_rest)
    ac = _classify_rest(away_rest)
    pts = _REST_MATRIX.get(hc, {}).get(ac, 0.0)
    pts = max(-3.5, min(3.5, pts))
    return {
        'signal': '3A_rest',
        'home_rest_days': home_rest, 'away_rest_days': away_rest,
        'home_class': hc, 'away_class': ac,
        'pts': round(pts, 2),
        'applied': pts != 0.0,
    }


def signal_3b_travel(home: str, away: str, venue: str) -> dict:
    """Travel burden differential."""
    h_km = _travel_km(home, venue)
    a_km = _travel_km(away, venue)
    diff_km = a_km - h_km   # positive = away team travelled more
    # Scale: every 600 km net disadvantage ≈ 1.0 pt
    # Increased from 500→600: general AFL interstate travel is less impactful than
    # assumed (6-7 day rest neutralises physiology). WA trips (2700km+) still hit cap.
    raw_pts = (diff_km / 600.0) * 1.0
    pts = max(-3.0, min(3.0, raw_pts))
    return {
        'signal': '3B_travel',
        'home_km': round(h_km), 'away_km': round(a_km),
        'diff_km': round(diff_km),
        'pts': round(pts, 2),
        'applied': abs(pts) >= 0.3,
    }


def signal_3c_compound(home: str, away: str, venue: str,
                        home_rest: int | None, away_rest: int | None) -> dict:
    """Extra penalty when short rest AND long travel combine."""
    h_km = _travel_km(home, venue)
    a_km = _travel_km(away, venue)
    hc   = _classify_rest(home_rest)
    ac   = _classify_rest(away_rest)

    pts = 0.0
    note = ''

    # Home team on short rest AND had to travel far
    if hc == 'short' and h_km > 1500:
        pts -= 2.0
        note = f'home short+travel ({h_km:.0f}km)'
    elif hc == 'short' and h_km > 800:
        pts -= 1.0
        note = f'home short+travel ({h_km:.0f}km)'

    # Away team on short rest AND had to travel far (helps home)
    if ac == 'short' and a_km > 1500:
        pts += 2.0
        note += f' away short+travel ({a_km:.0f}km)'
    elif ac == 'short' and a_km > 800:
        pts += 1.0
        note += f' away short+travel ({a_km:.0f}km)'

    pts = max(-2.5, min(2.5, pts))
    return {
        'signal': '3C_compound',
        'note': note.strip(),
        'pts': round(pts, 2),
        'applied': pts != 0.0,
    }


def signal_3d_form_momentum(home_last_margin: float | None,
                             away_last_margin: float | None) -> dict:
    """
    Bounce-back and flat-spot angles.
    Team off big loss at home → slight positive (motivated bounce-back).
    Team off big win away → slight negative (flat-spot risk).
    These are small — the ML already captures last_margin.
    Only apply when the effect is pronounced (>40 pts).
    """
    pts  = 0.0
    note = ''
    BIG  = 40.0

    if home_last_margin is not None and home_last_margin < -BIG:
        pts  += 1.5
        note += f'home bounce-back (lost by {abs(home_last_margin):.0f})'
    if away_last_margin is not None and away_last_margin > BIG:
        pts  += 1.0
        note += f' away flat-spot (won by {away_last_margin:.0f})'
    if home_last_margin is not None and home_last_margin > BIG:
        pts  -= 1.0
        note += f' home flat-spot (won by {home_last_margin:.0f})'
    if away_last_margin is not None and away_last_margin < -BIG:
        pts  -= 1.5
        note += f' away bounce-back (lost by {abs(away_last_margin):.0f})'

    pts = max(-2.0, min(2.0, pts))
    return {
        'signal': '3D_momentum',
        'home_last_margin': home_last_margin,
        'away_last_margin': away_last_margin,
        'note': note.strip(),
        'pts': round(pts, 2),
        'applied': pts != 0.0,
    }


def _is_queens_birthday(game_date: str) -> bool:
    """Return True if game_date falls on the second Monday of June (Vic Queen's Birthday)."""
    if not game_date:
        return False
    try:
        import datetime
        # Accept 'YYYY-MM-DD' or any string containing that pattern
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
            try:
                d = datetime.datetime.strptime(game_date[:10], fmt).date()
                break
            except ValueError:
                continue
        else:
            return False
        if d.month != 6:
            return False
        if d.weekday() != 0:   # Monday = 0
            return False
        # Second Monday of June: day in [8, 14]
        return 8 <= d.day <= 14
    except Exception:
        return False


def signal_3e_occasion(game_date: str, home: str, venue: str) -> dict:
    """
    Occasion crowd effects:
      ANZAC Day  — Essendon or Collingwood at MCG on April 25 → +1.5 pts home
      Queen's Birthday — Collingwood or Melbourne at MCG on 2nd Monday of June → +1.0 pts home
        Collingwood 15 wins vs Melbourne 7 since 2006 (home team advantage confirmed).
    """
    pts  = 0.0
    note = ''

    if game_date and '04-25' in game_date:
        anzac_teams = {'Essendon Bombers', 'Collingwood Magpies'}
        if home in anzac_teams and venue == 'MCG':
            pts  = 1.5
            note = 'ANZAC Day home crowd boost'

    if _is_queens_birthday(game_date):
        qb_teams = {'Collingwood Magpies', 'Melbourne Demons'}
        if home in qb_teams and venue == 'MCG':
            pts  += 1.0
            note += (' ' if note else '') + "Queen's Birthday home crowd boost"

    return {
        'signal': '3E_occasion',
        'note': note.strip(),
        'pts': round(pts, 2),
        'applied': pts != 0.0,
    }


# ── Master function ───────────────────────────────────────────────────────────

T3_TOTAL_CAP = 6.0


def compute_t3(home: str, away: str, venue: str, game_date: str,
               home_rest: int | None, away_rest: int | None,
               home_last_margin: float | None = None,
               away_last_margin: float | None = None) -> dict:
    """
    Compute all T3 situational signals and return combined result.

    Returns:
        t3_handicap : float  — total pts adjustment (home perspective)
        t3_totals   : float  — totals adjustment (short rest = lower total)
        signals     : list   — per-signal breakdown for audit
    """
    s3a = signal_3a_rest(home_rest, away_rest)
    s3b = signal_3b_travel(home, away, venue)
    s3c = signal_3c_compound(home, away, venue, home_rest, away_rest)
    s3d = signal_3d_form_momentum(home_last_margin, away_last_margin)
    s3e = signal_3e_occasion(game_date, home, venue)

    raw = s3a['pts'] + s3b['pts'] + s3c['pts'] + s3d['pts'] + s3e['pts']
    t3_handicap = max(-T3_TOTAL_CAP, min(T3_TOTAL_CAP, raw))

    # Totals: short rest on either side suppresses scoring slightly
    # Reduced from -2.0 → -1.5 per team: AFL 6-7 day structure means short rest
    # scoring impact is modest; -4.0 combined cap was too aggressive.
    tot_adj = 0.0
    hc = _classify_rest(home_rest)
    ac = _classify_rest(away_rest)
    if hc == 'short':
        tot_adj -= 1.5
    if ac == 'short':
        tot_adj -= 1.5
    t3_totals = max(-3.0, min(3.0, tot_adj))

    return {
        't3_handicap': round(t3_handicap, 2),
        't3_totals':   round(t3_totals,   2),
        'signals': [s3a, s3b, s3c, s3d, s3e],
        'raw': round(raw, 2),
        'capped': abs(raw) > T3_TOTAL_CAP,
    }
