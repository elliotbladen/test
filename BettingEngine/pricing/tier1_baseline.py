# pricing/tier1_baseline.py
# =============================================================================
# Tier 1 — Baseline bookmaker-style pricing layer
# =============================================================================
#
# PURPOSE
# -------
# Produce a baseline expected score for each team.
# All downstream tiers (2-7) express their effects as adjustments to these
# baseline expected points. Keeping everything in expected-points units means
# H2H, handicap, and totals all stay internally consistent.
#
# This module contains every component function so each can be tested and
# inspected independently. compute_baseline() is the main entry point —
# it calls everything in order and returns the full output + audit trail.
#
# =============================================================================
# MODEL OVERVIEW
# =============================================================================
#
# The model separates team quality into four distinct signals:
#
#   1. Season-long quality       — sustained strength across the full season
#                                   (net scoring differential, ELO rating)
#
#   2. Recent form (last N games) — short-term momentum, may diverge from
#                                   season averages (streak, injury recovery, etc.)
#
#   3. Attack and defence ratings — directional breakdown of season quality
#                                   (how well they score vs how well they prevent)
#
#   4. Team-specific home advantage — this team's own home/away differential,
#                                      not just the league-wide average
#
# These are combined to produce expected home and away scores:
#
#   expected_home_points =
#       league_avg_per_team
#     + home_attack_rating          (home team scores above/below average)
#     - away_defence_rating         (away defence suppresses home scoring)
#     + home_team_home_advantage    (team-specific home ground benefit)
#     + home_form_delta             (bounded short-term form adjustment)
#
#   expected_away_points =
#       league_avg_per_team
#     + away_attack_rating          (away team scores above/below average)
#     - home_defence_rating         (home defence suppresses away scoring)
#     + away_form_delta             (bounded short-term form adjustment)
#     [no home advantage — applies to home team only]
#
# An ELO-based expected margin is also computed independently and blended
# with the ratings-based margin (configurable blend weight).
# ELO guards against thin data early in the season.
# Season quality rating is used as an ELO fallback when no ELO is stored.
#
# =============================================================================
# INPUTS (team_stats dict keys)
# =============================================================================
#
# From the team_stats table (computed as-of a specific date):
#
#   games_played              int    — total games played in the stat window
#   wins                      int    — total wins (primary quality signal); None = fallback
#   losses                    int    — total losses; None = fallback
#   win_pct                   float  — wins / games_played; None = use scoring diff only
#   ladder_position           int    — ladder rank (1 = top); nullable / informational
#   points_for_avg            float  — season average points scored per game
#   points_against_avg        float  — season average points conceded per game
#   home_points_for_avg       float  — average points scored in HOME games
#   home_points_against_avg   float  — average points conceded in HOME games
#   away_points_for_avg       float  — average points scored in AWAY games
#   away_points_against_avg   float  — average points conceded in AWAY games
#   elo_rating                float  — current ELO rating (None = use fallback)
#   recent_form_rating        float  — pre-computed form score in [-1.0, 1.0]
#                                      used as fallback when last_n_results not provided
#
# Optional (passed separately to compute_baseline):
#   last_n_results            list   — actual last-N game result dicts
#                                      (see compute_recent_form for format)
#
# =============================================================================
# OUTPUTS
# =============================================================================
#
# compute_baseline() returns:
#   baseline_home_points   float
#   baseline_away_points   float
#   baseline_margin        float  (positive = home favoured)
#   baseline_total         float
#   _debug                 dict   (every intermediate value — for audit log)
#
# =============================================================================
# CONFIG (from tiers.yaml tier1_baseline section)
# =============================================================================
# See tiers.yaml for all keys, defaults, and calibration notes.
# =============================================================================

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Internal helper
# =============================================================================

def _recent_avg(results: list, n: int, key: str):
    """
    Average a numeric field over the last n result dicts.

    Returns None if results is None or empty (signals no recent data available).
    Used to derive recent_avg_for and recent_avg_against for attack/defence blending.
    """
    if not results:
        return None
    games = results[:n]
    if not games:
        return None
    return sum(float(r.get(key, 0)) for r in games) / len(games)


# =============================================================================
# 1. Season-long quality
# =============================================================================

def compute_season_quality_rating(
    stats: dict,
    league_avg_per_team: float,
    config: dict = None,
) -> float:
    """
    Assess this team's overall quality based on full-season performance.

    This is the "sustained strength signal." Result is in expected-points units
    for compatibility with the ELO proxy calculation.

    PRIMARY SIGNALS (wins and ladder position express class):
        win_quality    = (win_pct - 0.5) * season_quality_scale
        ladder_quality = ladder_norm * (season_quality_scale / 2)
            where ladder_norm = 1 - 2*(ladder_position - 1) / (num_teams - 1)
            position 1 (top)  → ladder_norm = +1.0 → +12 pts
            position 16 (bot) → ladder_norm = -1.0 → -12 pts

        primary = win_quality * win_weight + ladder_quality * ladder_weight
            (default: 60% win record, 40% ladder position)

    SECONDARY CORRECTION (scoring diff corrects misleading records):
        quality = primary * (1 - correction_weight) + scoring_diff * correction_weight
            (default correction_weight = 0.2)

    DEGRADED MODES:
        No ladder_position → primary = win_quality only.
        No win_pct         → quality = scoring_diff (backward-compatible fallback).

    HOW THIS IS USED:
    - Logged in _debug for every model run.
    - Used as ELO proxy when no ELO stored:
          elo_proxy = default_elo + (quality / points_per_elo_point)

    Args:
        stats: team_stats dict (reads win_pct, ladder_position, games_played,
               avg_points_for, avg_points_against)
        league_avg_per_team: league average points per team per game
        config: tier1_baseline config dict; None = use defaults

    Returns:
        float — quality in expected-points units (positive = above average)
    """
    if config is None:
        config = {}

    scale         = float(config.get('season_quality_scale', 24.0))
    corr_weight   = max(0.0, min(1.0, float(config.get('season_quality_correction_weight', 0.2))))
    win_weight    = float(config.get('season_quality_win_weight',    0.6))
    ladder_weight = float(config.get('season_quality_ladder_weight', 0.4))
    num_teams     = max(2, int(config.get('season_quality_num_teams', 16)))

    avg_for      = float(stats.get('points_for_avg')     or league_avg_per_team)
    avg_against  = float(stats.get('points_against_avg') or league_avg_per_team)
    scoring_diff = avg_for - avg_against

    win_pct      = stats.get('win_pct')
    ladder_pos   = stats.get('ladder_position')
    games_played = int(stats.get('games_played') or 0)

    if win_pct is not None and games_played > 0:
        win_pct     = float(win_pct)
        win_quality = (win_pct - 0.5) * scale

        if ladder_pos is not None:
            # Normalise: position 1 (top) → +1.0, position num_teams → -1.0
            ladder_norm    = 1.0 - 2.0 * (float(ladder_pos) - 1.0) / (num_teams - 1)
            ladder_quality = ladder_norm * (scale / 2.0)
            primary = win_quality * win_weight + ladder_quality * ladder_weight
        else:
            # No ladder data — full primary weight on win record alone
            ladder_quality = None
            primary = win_quality

        quality = primary * (1.0 - corr_weight) + scoring_diff * corr_weight

        logger.debug(
            "season_quality: win_pct=%.3f win_q=%.2f ladder=%s ladder_q=%s "
            "primary=%.2f scoring_diff=%.2f -> %.2f",
            win_pct, win_quality,
            ladder_pos, f"{ladder_quality:.2f}" if ladder_quality is not None else "n/a",
            primary, scoring_diff, quality,
        )

    else:
        # No win record — fall back to scoring differential
        quality = scoring_diff
        logger.debug("season_quality: no win_pct, scoring_diff fallback: %.2f", quality)

    return quality


# =============================================================================
# 2. Recent form
# =============================================================================

def compute_recent_form(
    last_n_results: list,
    config: dict,
    league_avg_per_team: float = None,
) -> float:
    """
    Compute a form score from the last N game results.

    This reflects SHORT-TERM momentum — whether this team is currently playing
    above or below their season-long level.

    INPUT FORMAT:
    Each element of last_n_results must be a dict with:
        points_for      int   — points scored by THIS team in that game
        points_against  int   — points conceded by THIS team in that game
        is_home         bool  — whether THIS team was playing at home (optional)

    The list should be ordered most-recent first (index 0 = latest game).
    The function uses at most the first `recent_form_games` config entries.

    FORMULA (4-component blend per game):

    Each game contributes four normalised signals, combined using configurable
    weights (default: outcome 40%, margin 20%, scoring 20%, conceding 20%):

    1. OUTCOME  win=+1.0, draw=0.0, loss=-1.0
       Primary signal — wins and losses matter most.

    2. MARGIN   clamp((pts_for - pts_against) / form_margin_norm, -1, +1)
       A blowout win (+) or blowout loss (-) moves the score more.
       Saturates at ±form_margin_norm points (default 20).

    3. SCORING  clamp((pts_for - league_avg_per_team) / form_scoring_norm, -1, +1)
       Scoring above league average (+); below average (-).

    4. CONCEDING  clamp((league_avg_per_team - pts_against) / form_conceding_norm, -1, +1)
       Conceding below league average (+, good defence); above average (-).

    Per-game score = sum(component * weight for each component).
    Final form score = weighted average of per-game scores (recency-weighted optional).
    Result is clamped to [-1.0, 1.0].

    CONVERTING TO POINTS DELTA:
    This function returns the raw form score, not a points delta.
    In compute_baseline(), the form score is scaled:
        form_delta = form_score * form_weight_points * form_balance_weight
    where both multipliers are configured in tiers.yaml.

    NOTES:
    - An empty list or fewer games than expected returns 0.0 (neutral).
    - Situational angles (bye, short turnaround, etc.) remain in Tier 3.
    - If league_avg_per_team is not provided, it is inferred from
      league_avg_total in config (fallback: 47.0 / 2 = 23.5).

    Args:
        last_n_results: list of result dicts ordered most-recent first
        config: tier1_baseline config dict
        league_avg_per_team: league average points per team per game;
            if None, derived from config['league_avg_total']

    Returns:
        float in [-1.0, 1.0] — positive means good recent form
    """
    n                = int(config.get('recent_form_games', 5))
    recency_weighted = bool(config.get('form_recency_weighted', False))

    # Component weights
    w_outcome   = float(config.get('form_outcome_weight',   0.4))
    w_margin    = float(config.get('form_margin_weight',    0.2))
    w_scoring   = float(config.get('form_scoring_weight',   0.2))
    w_conceding = float(config.get('form_conceding_weight', 0.2))

    # Normalisation denominators (avoid division by zero)
    margin_norm   = max(1.0, float(config.get('form_margin_norm',   20.0)))
    scoring_norm  = max(1.0, float(config.get('form_scoring_norm',  12.0)))
    conceding_norm = max(1.0, float(config.get('form_conceding_norm', 12.0)))

    # League average — used to contextualise scoring and conceding
    if league_avg_per_team is None:
        league_avg_total = float(config.get('league_avg_total', 47.0))
        league_avg_per_team = league_avg_total / 2.0

    games = last_n_results[:n]
    if not games:
        return 0.0

    game_scores = []
    recency_weights = []

    for i, result in enumerate(games):
        pts_for     = int(result.get('points_for',     0))
        pts_against = int(result.get('points_against', 0))

        # Component 1: outcome
        if pts_for > pts_against:
            outcome = 1.0
        elif pts_for < pts_against:
            outcome = -1.0
        else:
            outcome = 0.0

        # Component 2: margin (normalised)
        raw_margin = float(pts_for - pts_against)
        c_margin = max(-1.0, min(1.0, raw_margin / margin_norm))

        # Component 3: scoring above/below league average (normalised)
        c_scoring = max(-1.0, min(1.0, (pts_for - league_avg_per_team) / scoring_norm))

        # Component 4: conceding below/above league average (normalised)
        # positive = conceded less than average (good)
        c_conceding = max(-1.0, min(1.0, (league_avg_per_team - pts_against) / conceding_norm))

        game_score = (
            w_outcome   * outcome    +
            w_margin    * c_margin   +
            w_scoring   * c_scoring  +
            w_conceding * c_conceding
        )
        game_scores.append(game_score)

        # Recency weight: game 0 (most recent) = n, game n-1 = 1; or flat
        rw = float(n - i) if recency_weighted else 1.0
        recency_weights.append(rw)

    total_weight = sum(recency_weights)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(s * w for s, w in zip(game_scores, recency_weights))
    form_score = weighted_sum / total_weight

    return max(-1.0, min(1.0, form_score))


def _form_delta_from_stored_rating(stats: dict, config: dict) -> float:
    """
    Fallback: convert a pre-stored recent_form_rating to a points delta.

    Used when actual last_n_results are not available (e.g. stats loaded
    from the database with a pre-computed recent_form_rating field).

    The stored rating must already be in [-1.0, 1.0].

    Returns:
        float — expected-points delta
    """
    form_weight = float(config.get('form_weight_points', 2.5))
    stored_rating = float(stats.get('recent_form_rating') or 0.0)
    stored_rating = max(-1.0, min(1.0, stored_rating))
    return stored_rating * form_weight


# =============================================================================
# Form interpretation rules
# =============================================================================

def compute_form_behavior_adjustment(
    last_n_results: list,
    raw_form_score: float,
    league_avg_per_team: float,
    config: dict,
) -> float:
    """
    Apply per-game behavioral rules A-D to produce a small form-score adjustment.

    A. BLOWOUT RULE
       Blowout win  (margin >= blowout_threshold) → slight negative: big wins can flatter.
       Blowout loss (|margin| >= blowout_threshold) → extra negative: reveals weakness.

    B. NARROW-LOSS RULE
       Narrow loss (|margin| < narrow_threshold) vs strong opponent,
       AND broader form is positive → mild bonus.
       Opponent strength proxy: pts_against > league_avg * strong_opp_factor.

    C. UGLY-WIN RULE
       Narrow win (margin < narrow_threshold) vs non-weak opponent:
         broadly winning → slight positive
         broadly struggling → slight negative
         neutral → no adjustment

    D. NARROW-WIN VS WEAK-TEAM RULE
       Narrow win vs weak opponent → explicitly neutral (no adjustment).
       Weak opponent proxy: pts_against < league_avg * weak_opp_factor.

    "Broader form" = raw_form_score relative to broader_form_threshold.

    Returns a float to add to the raw form score (before final clamp).
    Capped at ±form_behavior_max_adj.

    Args:
        last_n_results: list of result dicts ordered most-recent first
        raw_form_score: output of compute_recent_form() — used as broader form context
        league_avg_per_team: league average points per team per game
        config: tier1_baseline config dict

    Returns:
        float in [-form_behavior_max_adj, +form_behavior_max_adj]
    """
    n              = int(config.get('recent_form_games', 5))
    blowout_thresh = float(config.get('blowout_threshold', 20.0))
    narrow_thresh  = float(config.get('narrow_threshold', 8.0))
    strong_factor  = float(config.get('strong_opp_factor', 1.2))
    weak_factor    = float(config.get('weak_opp_factor', 0.8))
    form_thresh    = float(config.get('broader_form_threshold', 0.1))
    blow_win_damp  = float(config.get('blowout_win_dampener', 0.10))
    blow_loss_amp  = float(config.get('blowout_loss_amplifier', 0.15))
    nl_bonus       = float(config.get('narrow_loss_vs_strong_bonus', 0.10))
    uw_pos         = float(config.get('ugly_win_positive_bonus', 0.05))
    uw_neg         = float(config.get('ugly_win_negative_penalty', 0.05))
    max_adj        = float(config.get('form_behavior_max_adj', 0.25))

    broadly_positive = raw_form_score >  form_thresh
    broadly_negative = raw_form_score < -form_thresh

    games = last_n_results[:n]
    if not games:
        return 0.0

    total_adj = 0.0

    for result in games:
        pts_for     = int(result.get('points_for',     0))
        pts_against = int(result.get('points_against', 0))
        margin      = pts_for - pts_against
        won         = margin > 0
        lost        = margin < 0
        opp_strong  = pts_against > league_avg_per_team * strong_factor
        opp_weak    = pts_against < league_avg_per_team * weak_factor

        game_adj = 0.0

        if won and margin >= blowout_thresh:
            # A. Blowout win: dampen — big wins can flatter
            game_adj -= blow_win_damp

        elif lost and abs(margin) >= blowout_thresh:
            # A. Blowout loss: amplify — reveals weakness
            game_adj -= blow_loss_amp

        elif lost and abs(margin) < narrow_thresh:
            if opp_strong and broadly_positive:
                # B. Narrow loss to strong team, broader form supports it
                game_adj += nl_bonus
            # else: narrow loss is neutral

        elif won and margin < narrow_thresh:
            if opp_weak:
                # D. Narrow win vs weak team: explicitly neutral
                pass
            else:
                # C. Ugly win — context-dependent
                if broadly_positive:
                    game_adj += uw_pos
                elif broadly_negative:
                    game_adj -= uw_neg
                # else: neutral

        total_adj += game_adj

    avg_adj = total_adj / len(games)
    return max(-max_adj, min(max_adj, avg_adj))


def compute_form_quality_signals(
    stats: dict,
    league_avg_per_team: float,
    attack_rating: float,
    defence_rating: float,
    config: dict,
) -> float:
    """
    Apply season-level quality signals E-F to produce a small form-score adjustment.

    E. LOW-SCORING WINNING RULE
       Team is winning but attack is weak AND defence is not elite → mild warning.
       If defence IS elite, low scoring is acceptable — defence is carrying the wins.

    F. HIGH-SCORING BUT LEAKY RULE
       Team scores well above average but concedes well above average → slight warning.
       Attack is real, but leaky teams can flatter to deceive.

    Both rules can only produce negative adjustments (warnings), never positive.

    Returns a float in [-form_quality_max_adj, 0].

    Args:
        stats: team_stats dict (reads win_pct, games_played)
        league_avg_per_team: for context (not used directly — ratings are pre-computed)
        attack_rating: from compute_attack_rating() — positive = above average
        defence_rating: from compute_defence_rating() — positive = good defence
        config: tier1_baseline config dict

    Returns:
        float in [-form_quality_max_adj, 0]
    """
    win_pct      = float(stats.get('win_pct') or 0.5)
    games_played = int(stats.get('games_played') or 0)

    winning_thresh    = float(config.get('low_score_winning_threshold',  0.5))
    weak_atk_thresh   = float(config.get('low_score_attack_threshold',  -1.5))
    elite_def_thresh  = float(config.get('low_score_defence_threshold',  2.0))
    low_score_warning = float(config.get('low_score_warning_adj',       -0.10))
    leaky_def_thresh  = float(config.get('leaky_defence_threshold',     -2.0))
    leaky_atk_thresh  = float(config.get('leaky_attack_threshold',       2.0))
    leaky_warning     = float(config.get('leaky_warning_adj',           -0.08))
    max_adj           = float(config.get('form_quality_max_adj',         0.15))

    if games_played == 0:
        return 0.0

    total_adj = 0.0

    # E. Low-scoring winning rule
    is_winning      = win_pct > winning_thresh
    has_weak_attack = attack_rating < weak_atk_thresh
    has_elite_def   = defence_rating > elite_def_thresh

    if is_winning and has_weak_attack and not has_elite_def:
        total_adj += low_score_warning

    # F. High-scoring but leaky rule
    is_scoring_well = attack_rating > leaky_atk_thresh
    is_leaking      = defence_rating < leaky_def_thresh

    if is_scoring_well and is_leaking:
        total_adj += leaky_warning

    return max(-max_adj, min(0.0, total_adj))


# =============================================================================
# 3. Attack and defence ratings
# =============================================================================

def compute_attack_rating(
    stats: dict,
    league_avg_per_team: float,
    recent_avg_for: float = None,
    config: dict = None,
) -> float:
    """
    Compute how many points per game above/below league average this team scores.

    FORMULA:
        season_attack = avg_points_for - league_avg_per_team  (season-wide)

    When recent_avg_for is provided (derived from last N results):
        recent_attack = recent_avg_for - league_avg_per_team
        attack_rating = season_attack * season_weight + recent_attack * (1 - season_weight)
            (default: 70% season, 30% recent — season dominates, recent informs)

    Without recent data: pure season average (backward compatible).

    HOW THIS IS USED:
    Applied to the team's own scoring expectation in compute_expected_home/away_points.

    Args:
        stats: team_stats dict
        league_avg_per_team: league_avg_total / 2
        recent_avg_for: average points scored over last N games; None = season only
        config: tier1_baseline config dict (reads attack_season_weight)

    Returns:
        float — signed delta from league average, in points
    """
    if config is None:
        config = {}

    season_avg_for = float(stats.get('points_for_avg') or league_avg_per_team)
    season_attack  = season_avg_for - league_avg_per_team

    if recent_avg_for is not None:
        season_wt     = float(config.get('attack_season_weight', 0.7))
        recent_wt     = 1.0 - season_wt
        recent_attack = float(recent_avg_for) - league_avg_per_team
        return season_attack * season_wt + recent_attack * recent_wt

    return season_attack


def compute_defence_rating(
    stats: dict,
    league_avg_per_team: float,
    recent_avg_against: float = None,
    config: dict = None,
) -> float:
    """
    Compute how many fewer points per game than league average this team concedes.

    Positive = good defence (concedes less than average).
    Negative = poor defence (concedes more than average).

    FORMULA:
        season_defence = league_avg_per_team - avg_points_against  (season-wide)

    When recent_avg_against is provided (derived from last N results):
        recent_defence = league_avg_per_team - recent_avg_against
        defence_rating = season_defence * season_weight + recent_defence * (1 - season_weight)
            (default: 70% season, 30% recent)

    Without recent data: pure season average (backward compatible).

    HOW THIS IS USED:
    Applied to the OPPONENT's scoring expectation — better defence reduces what
    the opponent is expected to score.

    Args:
        stats: team_stats dict
        league_avg_per_team: league_avg_total / 2
        recent_avg_against: average points conceded over last N games; None = season only
        config: tier1_baseline config dict (reads defence_season_weight)

    Returns:
        float — signed delta (positive = better than average defence)
    """
    if config is None:
        config = {}

    season_avg_against = float(stats.get('points_against_avg') or league_avg_per_team)
    season_defence     = league_avg_per_team - season_avg_against

    if recent_avg_against is not None:
        season_wt      = float(config.get('defence_season_weight', 0.7))
        recent_wt      = 1.0 - season_wt
        recent_defence = league_avg_per_team - float(recent_avg_against)
        return season_defence * season_wt + recent_defence * recent_wt

    return season_defence


# =============================================================================
# 3b. Pythagorean Expectation — team quality signal
# =============================================================================

def compute_pythagorean_win_pct(pf: float, pa: float, exponent: float = 1.9) -> float:
    """
    Pythagorean win expectation calibrated for NRL (exponent = 1.9).

    FORMULA:
        pyth = pf^exp / (pf^exp + pa^exp)

    Normalises for blowouts and close games better than raw PF/PA.
    A team that wins close and loses big will show a lower pyth than
    their actual win% suggests — a regression signal.

    Returns 0.5 if both inputs are zero or invalid.

    Args:
        pf:       avg points scored per game
        pa:       avg points conceded per game
        exponent: NRL calibration (1.9)

    Returns:
        float in [0.0, 1.0] — expected win fraction
    """
    pf = max(pf, 0.0)
    pa = max(pa, 0.0)
    pf_e = pf ** exponent
    pa_e = pa ** exponent
    denom = pf_e + pa_e
    if denom == 0.0:
        return 0.5
    return pf_e / denom


def compute_pythagorean_margin_rating(pyth_win_pct: float, scale: float) -> float:
    """
    Convert a Pythagorean win% to a signed margin-point contribution.

    FORMULA:
        rating = (pyth_win_pct - 0.5) * scale

    A team at 0.600 pyth returns +5.0 at scale=50.
    A team at 0.400 pyth returns -5.0 at scale=50.
    A league-average team (0.500) returns 0.0.

    Args:
        pyth_win_pct: from compute_pythagorean_win_pct()
        scale:        from config pythagorean_scale

    Returns:
        float — signed quality contribution in expected-points units
    """
    return (pyth_win_pct - 0.5) * scale


# =============================================================================
# 4. Home advantage
# =============================================================================

def compute_league_home_advantage(config: dict) -> float:
    """
    Return the league-wide baseline home ground advantage in expected points.

    This is the structural NRL home advantage — the average additional
    expected points a team receives from playing at home vs a neutral venue,
    regardless of which team or which venue.

    Used as:
    - The default when a team has insufficient home game data.
    - The fallback inside compute_team_home_advantage().

    This is separate from:
        - Team-specific home advantages (compute_team_home_advantage below)
        - Venue fortress effects (handled in Tier 4)
        - Travel fatigue for away teams (Tier 4)

    Calibrate from historical data: typical NRL range is 2.5–5.0 points.

    Returns:
        float — points added to home team expected score
    """
    return float(config.get('home_advantage_points', 3.5))


def compute_team_home_advantage(stats: dict, config: dict) -> float:
    """
    Compute this specific team's home ground advantage in expected points.

    Different teams have very different home advantages. Some teams are
    significantly stronger at home (Penrith at BlueBet, South Sydney at
    Accor), others show little or no home uplift.

    FORMULA:
    The team home advantage is the average of two components:

        home_scoring_boost = home_points_for_avg - avg_points_for
            (how much MORE this team scores at home vs their season average)

        home_defence_boost = avg_points_against - home_points_against_avg
            (how much LESS this team concedes at home vs their season average)

        raw_team_ha = (home_scoring_boost + home_defence_boost) / 2

    BOUNDS:
    The result is bounded within [league_ha - max_delta, league_ha + max_delta]
    to prevent outlier data from distorting the model.

    DATA QUALITY BLEND:
    If a team has played few games, home/away split stats may be unreliable.
    Below `min_games_for_home_advantage`, the result is blended toward
    the league average home advantage:

        data_weight = min(1.0, games_played / min_games_for_home_advantage)
        team_ha = raw_team_ha * data_weight + league_ha * (1 - data_weight)

    This means:
    - 0 games: returns pure league average
    - min_games or more: returns the team-specific estimate

    WHAT THIS REPLACES:
    In compute_expected_home_points, this replaces the flat league home
    advantage from compute_league_home_advantage(). It is more accurate
    when sufficient data exists.

    WHAT THIS DOES NOT DO:
    - Does not adjust for venue (Tier 4 handles fortress/venue effects).
    - Does not adjust for opponent (who the home games were played against).
    - Does not consider crowd size, weather, or travel (Tiers 4 and 7).

    Future refinements:
    - Use actual home game count (not total games_played as proxy)
    - Opponent-adjusted home record
    - Split by recent home form vs full-season home form

    Args:
        stats: team_stats dict (needs home_points_for_avg, home_points_against_avg,
               avg_points_for, avg_points_against, games_played)
        config: tier1_baseline config dict

    Returns:
        float — expected points advantage from playing at home (this team specifically)
    """
    league_ha   = compute_league_home_advantage(config)
    min_games   = int(config.get('min_games_for_home_advantage', 4))
    max_delta   = float(config.get('team_ha_max_delta', 4.0))
    games_played = int(stats.get('games_played') or 0)

    # Check if home/away split data is available
    home_pts_for     = stats.get('home_points_for_avg')
    home_pts_against = stats.get('home_points_against_avg')
    season_pts_for   = stats.get('points_for_avg')
    season_pts_against = stats.get('points_against_avg')

    if (home_pts_for is None or home_pts_against is None or
            season_pts_for is None or season_pts_against is None):
        # No split data — use league average
        logger.debug("compute_team_home_advantage: no home/away split data, using league average %.1f", league_ha)
        return league_ha

    home_pts_for     = float(home_pts_for)
    home_pts_against = float(home_pts_against)
    season_pts_for   = float(season_pts_for)
    season_pts_against = float(season_pts_against)

    # Home scoring boost: how much more this team scores at home vs season average
    home_scoring_boost = home_pts_for - season_pts_for

    # Home defence boost: how much less this team concedes at home vs season average
    home_defence_boost = season_pts_against - home_pts_against

    # Average the two components into a single home advantage estimate
    raw_team_ha = (home_scoring_boost + home_defence_boost) / 2.0

    # Bound the raw estimate relative to the league average
    # Prevents extreme values from thin data distorting the model
    raw_team_ha = max(league_ha - max_delta, min(league_ha + max_delta, raw_team_ha))

    # Data quality blend: if games_played is low, lean toward league average
    # This uses total games as a proxy for home game count (roughly half)
    data_weight = min(1.0, games_played / max(min_games, 1))
    team_ha = raw_team_ha * data_weight + league_ha * (1.0 - data_weight)

    logger.debug(
        "compute_team_home_advantage: home_scoring_boost=%.2f home_defence_boost=%.2f "
        "raw=%.2f games=%d data_weight=%.2f -> %.2f (league avg %.1f)",
        home_scoring_boost, home_defence_boost,
        raw_team_ha, games_played, data_weight, team_ha, league_ha,
    )
    return team_ha


# =============================================================================
# 5. ELO — independent strength signal
# =============================================================================

def compute_elo_margin(
    home_stats: dict,
    away_stats: dict,
    config: dict,
    home_season_quality: float = 0.0,
    away_season_quality: float = 0.0,
) -> float:
    """
    Estimate expected margin from the ELO rating differential.

    ELO represents long-run team quality accumulated over many games.
    A higher ELO team is expected to win more often and by more points.

    FORMULA:
        elo_margin = (home_elo - away_elo) * points_per_elo_point
                   + league_home_advantage

    Note: league_home_advantage is included here because ELO ratings are
    neutral-venue measures. Two equal-ELO teams → the home team still has
    an advantage.

    ELO FALLBACK:
    If a team has no ELO rating stored (None or zero), we estimate it from
    their season_quality_rating via reverse-engineering:
        elo_proxy = default_elo + (season_quality / points_per_elo_point)

    This means teams with strong season stats get a temporarily higher ELO
    proxy, allowing early-season pricing before ELO has converged.

    CALIBRATION:
    points_per_elo_point should be calibrated from historical data.
    Starting estimate: 0.04 means a 100-point ELO gap → 4.0 points margin.

    Args:
        home_stats: team_stats dict for the home team
        away_stats: team_stats dict for the away team
        config: tier1_baseline config dict
        home_season_quality: from compute_season_quality_rating (ELO fallback)
        away_season_quality: from compute_season_quality_rating (ELO fallback)

    Returns:
        float — expected margin, positive = home team wins
    """
    default_elo    = float(config.get('default_elo', 1500.0))
    pts_per_elo    = float(config.get('points_per_elo_point', 0.04))
    league_ha      = compute_league_home_advantage(config)

    # Home ELO: use stored value, fall back to season quality proxy
    home_elo_stored = home_stats.get('elo_rating')
    if home_elo_stored:
        home_elo = float(home_elo_stored)
    else:
        # No ELO stored — estimate from season quality
        # season_quality (in points) → implied ELO offset
        home_elo = default_elo + (home_season_quality / pts_per_elo if pts_per_elo > 0 else 0.0)
        logger.debug("home ELO not stored — using season quality proxy: %.1f", home_elo)

    away_elo_stored = away_stats.get('elo_rating')
    if away_elo_stored:
        away_elo = float(away_elo_stored)
    else:
        away_elo = default_elo + (away_season_quality / pts_per_elo if pts_per_elo > 0 else 0.0)
        logger.debug("away ELO not stored — using season quality proxy: %.1f", away_elo)

    elo_diff = home_elo - away_elo

    # High-end ELO gap dampening.
    # Gaps beyond the threshold are compressed to prevent extreme spreads on
    # large mismatches while preserving the full signal for normal gaps.
    dampener_threshold = float(config.get('elo_gap_dampener_threshold', 150.0))
    dampener_factor    = float(config.get('elo_gap_dampener_factor', 1.0))
    abs_diff = abs(elo_diff)
    if abs_diff > dampener_threshold and dampener_factor < 1.0:
        sign = 1.0 if elo_diff >= 0 else -1.0
        effective_elo_diff = sign * (
            dampener_threshold + (abs_diff - dampener_threshold) * dampener_factor
        )
    else:
        effective_elo_diff = elo_diff

    elo_margin = effective_elo_diff * pts_per_elo + league_ha

    logger.debug(
        "ELO margin: home_elo=%.1f away_elo=%.1f diff=%.1f effective_diff=%.1f "
        "-> %.2f pts (incl. %.1f league home advantage)",
        home_elo, away_elo, elo_diff, effective_elo_diff, elo_margin, league_ha,
    )
    return elo_margin


# =============================================================================
# 6. Expected score functions
# =============================================================================

def compute_expected_home_points(
    league_avg_per_team: float,
    home_attack: float,
    away_defence: float,
    home_advantage: float,
    home_form_delta: float,
) -> float:
    """
    Compute expected home team score from its components.

    FORMULA:
        league_avg_per_team          — the shared baseline both teams start from
      + home_attack_rating           — home team scores above/below average
      - away_defence_rating          — away defence suppresses home scoring
      + home_advantage               — team-specific home ground benefit
      + home_form_delta              — bounded recent form adjustment

    WHY SUBTRACT away_defence?
    A positive away_defence_rating means the away team concedes fewer than
    average — this directly suppresses what the home team scores.
    Subtracting it is correct: better away defence = less home scoring.

    WHO PROVIDES home_advantage?
    In compute_baseline(), this receives the team-specific home advantage
    from compute_team_home_advantage(), not the flat league average.
    The function signature accepts a float — the caller determines specificity.

    EXAMPLE (all components):
        league_avg_per_team = 23.5
        home_attack         = +3.0   (good scoring team)
        away_defence        = +2.0   (good defensive away team)
        home_advantage      = +4.5   (strong home fortress)
        home_form_delta     = +1.0   (good recent form)
        → expected_home_points = 23.5 + 3.0 - 2.0 + 4.5 + 1.0 = 30.0

    Args:
        league_avg_per_team: L = league_avg_total / 2
        home_attack:       from compute_attack_rating(home_stats)
        away_defence:      from compute_defence_rating(away_stats)
        home_advantage:    from compute_team_home_advantage(home_stats, config)
        home_form_delta:   form_score * form_weight_points

    Returns:
        float — expected home team points
    """
    return league_avg_per_team + home_attack - away_defence + home_advantage + home_form_delta


def compute_expected_away_points(
    league_avg_per_team: float,
    away_attack: float,
    home_defence: float,
    away_form_delta: float,
) -> float:
    """
    Compute expected away team score from its components.

    FORMULA:
        league_avg_per_team          — the shared baseline both teams start from
      + away_attack_rating           — away team scores above/below average
      - home_defence_rating          — home defence suppresses away scoring
      + away_form_delta              — bounded recent form adjustment

    NOTE: no home advantage term. Home advantage applies only to the home
    team's expected score, not as a penalty subtracted from the away team.
    This avoids double-counting.

    EXAMPLE:
        league_avg_per_team = 23.5
        away_attack         = -1.5   (below-average attack)
        home_defence        = +2.5   (good home defence)
        away_form_delta     = -0.5   (poor recent form)
        → expected_away_points = 23.5 - 1.5 - 2.5 - 0.5 = 19.0

    Args:
        league_avg_per_team: L = league_avg_total / 2
        away_attack:      from compute_attack_rating(away_stats)
        home_defence:     from compute_defence_rating(home_stats)
        away_form_delta:  form_score * form_weight_points

    Returns:
        float — expected away team points
    """
    return league_avg_per_team + away_attack - home_defence + away_form_delta


# =============================================================================
# 7. Main orchestration
# =============================================================================

def compute_baseline(
    home_stats: dict,
    away_stats: dict,
    venue: dict,
    config: dict,
    home_last_n_results: list = None,
    away_last_n_results: list = None,
    home_prior_stats: dict = None,
    away_prior_stats: dict = None,
) -> dict:
    """
    Compute the Tier 1 baseline expected points for a match.

    This is the primary entry point for the pricing engine. Tiers 2–7 apply
    adjustments to the values returned here.

    FORM RESOLUTION:
    If home_last_n_results / away_last_n_results are provided, form is
    computed fresh from those game results via compute_recent_form().
    If not provided (default), the stored recent_form_rating in stats is
    used as a fallback via _form_delta_from_stored_rating().
    Pass actual results whenever possible for the most accurate form signal.

    HOME ADVANTAGE:
    The team-specific home advantage (compute_team_home_advantage) is used
    when sufficient home/away split data exists. When data is thin, it
    blends toward the league average.

    ELO BLEND:
    An ELO-based margin is computed independently and blended with the
    ratings-based margin at elo_weight (default 0.3).
    This guards against thin attack/defence data early in the season.
    The total (home + away) always comes from ratings; ELO only affects
    the margin split.

    AUDIT TRAIL:
    The _debug dict in the return value carries every intermediate
    calculation. This is written to model_adjustments by audit/model_logger.
    No information is discarded.

    Args:
        home_stats: team_stats dict for the home team
            Keys: games_played, points_for_avg, points_against_avg,
                  home_points_for_avg, home_points_against_avg,
                  away_points_for_avg, away_points_against_avg,
                  elo_rating, recent_form_rating
        away_stats: team_stats dict for the away team (same keys)
        venue: venue dict (passed through to engine; Tier 1 does not use it)
        config: tier1_baseline section of tiers.yaml
        home_last_n_results: optional list of last-N game result dicts for home team
            Each dict: {points_for: int, points_against: int, is_home: bool}
            Ordered most-recent first. If None, uses stored recent_form_rating.
        away_last_n_results: same for away team

    Returns:
        dict:
            baseline_home_points  float
            baseline_away_points  float
            baseline_margin       float  (positive = home favoured)
            baseline_total        float
            _debug                dict   (all intermediate values for audit log)
    """
    # --- Config ---
    league_avg_total    = float(config.get('league_avg_total', 47.0))
    league_avg_per_team = league_avg_total / 2.0
    elo_weight          = float(config.get('elo_weight', 0.3))
    form_weight_pts     = float(config.get('form_weight_points', 2.5))
    sq_weight           = float(config.get('season_quality_weight', 1.0))
    form_balance_wt     = float(config.get('form_balance_weight', 1.0))
    defence_bias        = float(config.get('defence_attack_bias', 0.05))
    totals_bias         = float(config.get('totals_conservative_bias', 0.5))
    class_lean_thresh   = max(0.01, float(config.get('close_call_class_lean_threshold', 6.0)))
    class_lean_max_pts  = float(config.get('close_call_class_lean_pts', 0.5))

    # ----------------------------------------------------------------
    # Season-long quality (used for ELO fallback and audit trail)
    # Primary driver: win_pct when available; scoring diff as secondary correction.
    # ----------------------------------------------------------------
    home_season_quality = compute_season_quality_rating(home_stats, league_avg_per_team, config)
    away_season_quality = compute_season_quality_rating(away_stats, league_avg_per_team, config)

    # ----------------------------------------------------------------
    # Recent form
    # Compute from actual results if available; otherwise use stored value.
    # ----------------------------------------------------------------
    if home_last_n_results is not None:
        home_form_score = compute_recent_form(home_last_n_results, config, league_avg_per_team)
        home_form_source = 'computed'
    else:
        stored = float(home_stats.get('recent_form_rating') or 0.0)
        home_form_score = max(-1.0, min(1.0, stored))
        home_form_source = 'stored'

    if away_last_n_results is not None:
        away_form_score = compute_recent_form(away_last_n_results, config, league_avg_per_team)
        away_form_source = 'computed'
    else:
        stored = float(away_stats.get('recent_form_rating') or 0.0)
        away_form_score = max(-1.0, min(1.0, stored))
        away_form_source = 'stored'

    # ----------------------------------------------------------------
    # Attack and defence ratings (season + recent blend)
    # Computed before form interpretation so quality signals (rules E-F)
    # can inspect attack and defence ratings.
    # ----------------------------------------------------------------
    n_form = int(config.get('recent_form_games', 5))

    home_recent_avg_for     = _recent_avg(home_last_n_results, n_form, 'points_for')
    home_recent_avg_against = _recent_avg(home_last_n_results, n_form, 'points_against')
    away_recent_avg_for     = _recent_avg(away_last_n_results, n_form, 'points_for')
    away_recent_avg_against = _recent_avg(away_last_n_results, n_form, 'points_against')

    home_attack  = compute_attack_rating(home_stats,  league_avg_per_team, home_recent_avg_for,     config)
    away_attack  = compute_attack_rating(away_stats,  league_avg_per_team, away_recent_avg_for,     config)
    home_defence = compute_defence_rating(home_stats, league_avg_per_team, home_recent_avg_against, config)
    away_defence = compute_defence_rating(away_stats, league_avg_per_team, away_recent_avg_against, config)

    # ----------------------------------------------------------------
    # Pythagorean Expectation — current season
    # Replaces attack/defence clash in the final ratings margin.
    # attack/defence above are retained for form quality signals (E-F).
    # ----------------------------------------------------------------
    pyth_exp   = float(config.get('pythagorean_exponent', 1.9))
    pyth_scale = float(config.get('pythagorean_scale', 50.0))

    home_pf_cur = float(home_stats.get('points_for_avg')  or league_avg_per_team)
    home_pa_cur = float(home_stats.get('points_against_avg') or league_avg_per_team)
    away_pf_cur = float(away_stats.get('points_for_avg')  or league_avg_per_team)
    away_pa_cur = float(away_stats.get('points_against_avg') or league_avg_per_team)

    home_pyth_cur = compute_pythagorean_win_pct(home_pf_cur, home_pa_cur, pyth_exp)
    away_pyth_cur = compute_pythagorean_win_pct(away_pf_cur, away_pa_cur, pyth_exp)
    home_pyth_rating_cur = compute_pythagorean_margin_rating(home_pyth_cur, pyth_scale)
    away_pyth_rating_cur = compute_pythagorean_margin_rating(away_pyth_cur, pyth_scale)

    # ----------------------------------------------------------------
    # Form interpretation adjustments
    # A-D: behavioral rules (blowout, narrow loss, ugly win, narrow win vs weak)
    # E-F: season quality signals (low-scoring winner, leaky scorer)
    # Both produce small form-score adjustments, averaged and capped.
    # ----------------------------------------------------------------
    if home_last_n_results is not None:
        home_behavior_adj = compute_form_behavior_adjustment(
            home_last_n_results, home_form_score, league_avg_per_team, config
        )
    else:
        home_behavior_adj = 0.0

    if away_last_n_results is not None:
        away_behavior_adj = compute_form_behavior_adjustment(
            away_last_n_results, away_form_score, league_avg_per_team, config
        )
    else:
        away_behavior_adj = 0.0

    home_quality_adj = compute_form_quality_signals(
        home_stats, league_avg_per_team, home_attack, home_defence, config
    )
    away_quality_adj = compute_form_quality_signals(
        away_stats, league_avg_per_team, away_attack, away_defence, config
    )

    # Combine all adjustments into a final form score, then convert to points delta
    home_form_score_final = max(-1.0, min(1.0, home_form_score + home_behavior_adj + home_quality_adj))
    away_form_score_final = max(-1.0, min(1.0, away_form_score + away_behavior_adj + away_quality_adj))
    home_form_delta = home_form_score_final * form_weight_pts
    away_form_delta = away_form_score_final * form_weight_pts

    # ----------------------------------------------------------------
    # Team-specific home advantage
    # ----------------------------------------------------------------
    home_team_ha = compute_team_home_advantage(home_stats, config)

    # ----------------------------------------------------------------
    # Early-season sample-size weights
    #
    # shrink(team) = min(1.0, games_played / pfpa_shrink_full_games)
    # This drives both the prior-season blend (below) and the dynamic
    # ELO weight.  At full games → current-season data trusted fully.
    # At 0 games  → fall back entirely on prior and ELO.
    # ----------------------------------------------------------------
    home_gp          = int(home_stats.get('games_played') or 0)
    away_gp          = int(away_stats.get('games_played') or 0)
    pfpa_full_games  = max(1.0, float(config.get('pfpa_shrink_full_games', 8.0)))
    home_pfpa_shrink = min(1.0, home_gp / pfpa_full_games)
    away_pfpa_shrink = min(1.0, away_gp / pfpa_full_games)

    # ----------------------------------------------------------------
    # Prior-season attack/defence priors
    #
    # Use the prior season's PF/PA as an informed prior, regressed toward
    # the league average by prior_season_weight (default 0.60).
    # This preserves elite teams' baseline early-season (e.g. Penrith's
    # defence should not look average in Round 3 just because only 3
    # current-season games have been played).
    #
    # Blend formula (per team):
    #   current_weight = home_pfpa_shrink (from above)
    #   prior_weight   = 1.0 - current_weight
    #   blended = current_attack * current_weight + prior_attack * prior_weight
    #
    # If no prior stats exist (new team or no prior season loaded),
    # prior_attack/defence default to 0.0 — equivalent to the old
    # shrink-toward-zero behaviour.
    # ----------------------------------------------------------------
    prior_wt = float(config.get('prior_season_weight', 0.60))

    def _prior_pyth_rating(prior_stats: dict | None) -> float:
        """
        Compute prior-season Pythagorean margin rating, regressed at prior_wt.
        Returns 0.0 if no prior stats (equivalent to league-average prior).
        """
        if not prior_stats:
            return 0.0
        pf = float(prior_stats.get('points_for_avg') or league_avg_per_team)
        pa = float(prior_stats.get('points_against_avg') or league_avg_per_team)
        pyth = compute_pythagorean_win_pct(pf, pa, pyth_exp)
        return compute_pythagorean_margin_rating(pyth, pyth_scale) * prior_wt

    prior_home_pyth = _prior_pyth_rating(home_prior_stats)
    prior_away_pyth = _prior_pyth_rating(away_prior_stats)

    # Prior PF/PA for prior attack/defence (kept for debug audit trail)
    def _prior_atk_def(prior_stats: dict | None) -> tuple[float, float]:
        if not prior_stats:
            return 0.0, 0.0
        pf = float(prior_stats.get('points_for_avg') or league_avg_per_team)
        pa = float(prior_stats.get('points_against_avg') or league_avg_per_team)
        return (pf - league_avg_per_team) * prior_wt, (league_avg_per_team - pa) * prior_wt

    prior_home_attack, prior_home_defence = _prior_atk_def(home_prior_stats)
    prior_away_attack, prior_away_defence = _prior_atk_def(away_prior_stats)

    # Blended Pythagorean ratings (current-season shrunk, prior fills the gap)
    blended_home_pyth = (home_pyth_rating_cur * home_pfpa_shrink
                         + prior_home_pyth * (1.0 - home_pfpa_shrink))
    blended_away_pyth = (away_pyth_rating_cur * away_pfpa_shrink
                         + prior_away_pyth * (1.0 - away_pfpa_shrink))

    # ----------------------------------------------------------------
    # Pythagorean floor / ceiling guard
    #
    # Prevents a small sample (< pyth_fc_gp_thresh games) from producing
    # a blended rating more than pyth_fc_max_dev Pythagorean win-pct
    # points away from the team's raw 2025 prior.
    # Guard is removed entirely once the team reaches the GP threshold.
    # Teams with no 2025 prior are anchored at 0.500 (league average).
    # ----------------------------------------------------------------
    pyth_fc_max_dev   = float(config.get('pyth_floor_ceiling_max_deviation', 0.25))
    pyth_fc_gp_thresh = int(config.get('pyth_floor_ceiling_gp_threshold', 8))

    def _raw_prior_pyth_win_pct(prior_stats: dict | None) -> float:
        """Raw 2025 prior Pythagorean win pct — no prior_wt scaling."""
        if not prior_stats:
            return 0.5
        pf = float(prior_stats.get('points_for_avg') or league_avg_per_team)
        pa = float(prior_stats.get('points_against_avg') or league_avg_per_team)
        return compute_pythagorean_win_pct(pf, pa, pyth_exp)

    home_prior_pyth_win_pct = _raw_prior_pyth_win_pct(home_prior_stats)
    away_prior_pyth_win_pct = _raw_prior_pyth_win_pct(away_prior_stats)

    def _apply_pyth_guard(blended_rating: float, prior_win_pct: float,
                          gp: int) -> tuple:
        """
        Clamp blended Pythagorean rating in win-pct space.
        Returns (clamped_rating, floor_applied, ceiling_applied, delta_pts).
        delta_pts is the correction applied (positive = floor lifted rating).
        """
        if gp >= pyth_fc_gp_thresh:
            return blended_rating, False, False, 0.0
        blended_win_pct = blended_rating / pyth_scale + 0.5
        floor_pct   = prior_win_pct - pyth_fc_max_dev
        ceiling_pct = prior_win_pct + pyth_fc_max_dev
        clamped_pct = max(floor_pct, min(ceiling_pct, blended_win_pct))
        floor_hit   = clamped_pct > blended_win_pct + 1e-9
        ceil_hit    = clamped_pct < blended_win_pct - 1e-9
        delta_pts   = (clamped_pct - blended_win_pct) * pyth_scale
        return (clamped_pct - 0.5) * pyth_scale, floor_hit, ceil_hit, delta_pts

    blended_home_pyth, home_floor_hit, home_ceil_hit, home_fc_delta = \
        _apply_pyth_guard(blended_home_pyth, home_prior_pyth_win_pct, home_gp)
    blended_away_pyth, away_floor_hit, away_ceil_hit, away_fc_delta = \
        _apply_pyth_guard(blended_away_pyth, away_prior_pyth_win_pct, away_gp)

    # Kept for form quality signals (E-F) and audit — not used in margin
    blended_home_attack  = home_attack  * home_pfpa_shrink + prior_home_attack  * (1.0 - home_pfpa_shrink)
    blended_home_defence = home_defence * home_pfpa_shrink + prior_home_defence * (1.0 - home_pfpa_shrink)
    blended_away_attack  = away_attack  * away_pfpa_shrink + prior_away_attack  * (1.0 - away_pfpa_shrink)
    blended_away_defence = away_defence * away_pfpa_shrink + prior_away_defence * (1.0 - away_pfpa_shrink)

    # ----------------------------------------------------------------
    # Tier 1 totals estimate
    # league_avg_total + both attack ratings - both defence ratings.
    # Attack above average → more scoring. Defence above average → less.
    # Margin logic is unchanged — this is totals only.
    # ----------------------------------------------------------------
    totals_T1 = (league_avg_total
                 + blended_home_attack + blended_away_attack
                 - blended_home_defence - blended_away_defence)

    # ----------------------------------------------------------------
    # Dynamic ELO weight
    #
    # ELO anchors heavily early season; PF/PA earns influence as games
    # accumulate.  Using the average shrink of both teams for the match.
    #
    #   avg_shrink   = (home_pfpa_shrink + away_pfpa_shrink) / 2
    #   pfpa_weight  = pfpa_max_weight * avg_shrink
    #   elo_weight   = 1.0 - pfpa_weight
    #
    # At 0 gp for both:        elo_weight = 1.00  (pure ELO)
    # At pfpa_shrink_full_games: elo_weight = 1.0 - pfpa_max_weight  (= 0.30 default)
    #
    # pfpa_max_weight defaults to 0.70 so the long-run ELO share = 0.30,
    # matching the original static elo_weight config value.
    # ----------------------------------------------------------------
    pfpa_max_weight  = float(config.get('pfpa_max_weight', 0.70))
    avg_match_shrink = (home_pfpa_shrink + away_pfpa_shrink) / 2.0
    dynamic_elo_weight = 1.0 - pfpa_max_weight * avg_match_shrink

    # ----------------------------------------------------------------
    # Pythagorean ratings-based margin
    # Net Pythagorean quality difference → margin contribution.
    # Home advantage and form are added on top.
    # sq_weight scales the class signal (configurable, default 1.0).
    # defence_attack_bias is absorbed into Pythagorean (not applicable
    # to a combined metric) — explicitly set to 0.0 for Pyth path.
    # ----------------------------------------------------------------
    pyth_class_margin = (blended_home_pyth - blended_away_pyth) * sq_weight
    form_margin       = (home_form_delta - away_form_delta) * form_balance_wt
    margin_from_ratings = pyth_class_margin + home_team_ha + form_margin

    # Reconstruct pts from ratings (for total anchor and audit)
    # total_from_ratings uses raw PF/PA averages (unchanged)
    home_pts_ratings = None   # not used in margin path — set for audit only
    away_pts_ratings = None

    # Contribution breakdown (audit)
    class_margin_contribution = pyth_class_margin
    form_margin_contribution  = form_margin

    # ----------------------------------------------------------------
    # Total anchor: average of the typical scoring environment in each
    # team's games, rather than the attack-defence clash sum.
    #
    # WHY: using home_pts_ratings + away_pts_ratings caused defence
    # ratings (which are 2× more dispersed than attack ratings) to
    # dominate the total. A team with elite defence (e.g. Penrith,
    # concedes 12.8/game) would suppress the total to ~38, even though
    # both teams might be high-scoring on their own. This approach uses
    # each team's own points_for_avg + points_against_avg as a proxy
    # for the typical total in their games, then averages the two.
    #
    # The margin remains unchanged — the attack-defence clash still
    # drives H2H and handicap. Only the total anchor shifts.
    # ----------------------------------------------------------------
    _h_pf = float(home_stats.get('points_for_avg')      or league_avg_per_team)
    _h_pa = float(home_stats.get('points_against_avg')  or league_avg_per_team)
    _a_pf = float(away_stats.get('points_for_avg')      or league_avg_per_team)
    _a_pa = float(away_stats.get('points_against_avg')  or league_avg_per_team)
    total_from_clash    = None   # not applicable in Pythagorean path
    total_from_ratings  = ((_h_pf + _h_pa) + (_a_pf + _a_pa)) / 2.0

    # ----------------------------------------------------------------
    # ELO-based expected margin (independent strength signal)
    # Blended into the final margin at dynamic_elo_weight.
    # ----------------------------------------------------------------
    margin_from_elo = compute_elo_margin(
        home_stats, away_stats, config,
        home_season_quality, away_season_quality,
    )

    # ----------------------------------------------------------------
    # Blend margin estimates using dynamic ELO weight.
    # dynamic_elo_weight = 1.0 at 0gp, falls to (1 - pfpa_max_weight)
    # at pfpa_shrink_full_games — so ELO anchors heavily early season.
    # ----------------------------------------------------------------
    blended_margin = (
        (1.0 - dynamic_elo_weight) * margin_from_ratings
        + dynamic_elo_weight * margin_from_elo
    )

    # ----------------------------------------------------------------
    # Close-call class lean
    # When the margin is small, nudge it slightly toward the better class team.
    # Strength is proportional to closeness: full at margin=0, zero at threshold.
    # "Better class" = higher season quality rating.
    # ----------------------------------------------------------------
    closeness = max(0.0, 1.0 - abs(blended_margin) / class_lean_thresh)
    class_diff = home_season_quality - away_season_quality
    class_sign = 1.0 if class_diff > 0 else (-1.0 if class_diff < 0 else 0.0)
    class_lean_delta = closeness * class_lean_max_pts * class_sign
    adjusted_margin = blended_margin + class_lean_delta

    # ----------------------------------------------------------------
    # Reconstruct expected home/away points from adjusted margin + total.
    # Total stays from ratings; ELO and class lean only affect the margin split.
    # ----------------------------------------------------------------
    pre_bias_home = (total_from_ratings + adjusted_margin) / 2.0
    pre_bias_away = (total_from_ratings - adjusted_margin) / 2.0

    # ----------------------------------------------------------------
    # Totals conservative bias
    # Subtract a small fixed amount from the total, split evenly.
    # Margin is unchanged; only the total (and individual expected scores) shifts.
    # ----------------------------------------------------------------
    baseline_home_points = pre_bias_home - totals_bias / 2.0
    baseline_away_points = pre_bias_away - totals_bias / 2.0
    baseline_margin      = baseline_home_points - baseline_away_points
    baseline_total       = baseline_home_points + baseline_away_points

    logger.debug(
        "Tier 1 baseline: home=%.2f away=%.2f margin=%.2f total=%.2f "
        "[ratings_margin=%.2f elo_margin=%.2f blend=%.2f]",
        baseline_home_points, baseline_away_points,
        baseline_margin, baseline_total,
        margin_from_ratings, margin_from_elo, blended_margin,
    )

    return {
        'baseline_home_points': round(baseline_home_points, 2),
        'baseline_away_points': round(baseline_away_points, 2),
        'baseline_margin':      round(baseline_margin, 2),
        'baseline_total':       round(baseline_total, 2),
        'totals_T1':            round(totals_T1, 2),
        # ---------------------------------------------------------------
        # _debug: every intermediate value.
        # Written verbatim to model_adjustments by audit/model_logger.
        # Not used in downstream pricing calculations.
        # ---------------------------------------------------------------
        '_debug': {
            'league_avg_per_team':        league_avg_per_team,

            # Season-long quality
            'home_season_quality':        round(home_season_quality, 3),
            'away_season_quality':        round(away_season_quality, 3),

            # Attack / defence — current season (raw, retained for form quality signals)
            'home_attack_rating':         round(home_attack, 3),
            'away_attack_rating':         round(away_attack, 3),
            'home_defence_rating':        round(home_defence, 3),
            'away_defence_rating':        round(away_defence, 3),
            # Pythagorean Expectation — current season
            'home_pyth_win_pct':          round(home_pyth_cur, 4),
            'away_pyth_win_pct':          round(away_pyth_cur, 4),
            'home_pyth_rating_cur':       round(home_pyth_rating_cur, 3),
            'away_pyth_rating_cur':       round(away_pyth_rating_cur, 3),
            'pythagorean_exponent':       pyth_exp,
            'pythagorean_scale':          pyth_scale,
            # Prior-season Pythagorean (regressed rating used in blend)
            'prior_home_pyth':            round(prior_home_pyth, 3),
            'prior_away_pyth':            round(prior_away_pyth, 3),
            'prior_season_weight':        prior_wt,
            # Raw 2025 prior win pct — anchor for floor/ceiling guard
            'home_prior_pyth_win_pct':    round(home_prior_pyth_win_pct, 4),
            'away_prior_pyth_win_pct':    round(away_prior_pyth_win_pct, 4),
            # Pythagorean floor / ceiling guard
            'pyth_fc_max_deviation':      pyth_fc_max_dev,
            'pyth_fc_gp_threshold':       pyth_fc_gp_thresh,
            'home_pyth_floor_hit':        home_floor_hit,
            'home_pyth_ceil_hit':         home_ceil_hit,
            'home_pyth_fc_delta_pts':     round(home_fc_delta, 3),
            'away_pyth_floor_hit':        away_floor_hit,
            'away_pyth_ceil_hit':         away_ceil_hit,
            'away_pyth_fc_delta_pts':     round(away_fc_delta, 3),
            # Blended Pythagorean ratings (drive margin_from_ratings; post-guard)
            'blended_home_pyth':          round(blended_home_pyth, 3),
            'blended_away_pyth':          round(blended_away_pyth, 3),
            'pyth_class_margin':          round(pyth_class_margin, 3),
            # Prior attack/defence (retained for audit, not used in margin)
            'prior_home_attack':          round(prior_home_attack, 3),
            'prior_home_defence':         round(prior_home_defence, 3),
            'prior_away_attack':          round(prior_away_attack, 3),
            'prior_away_defence':         round(prior_away_defence, 3),
            # Blended attack/defence (retained for audit/form signals, not in margin)
            'blended_home_attack':        round(blended_home_attack, 3),
            'blended_home_defence':       round(blended_home_defence, 3),
            'blended_away_attack':        round(blended_away_attack, 3),
            'blended_away_defence':       round(blended_away_defence, 3),
            # Sample-size shrink factors
            'home_pfpa_shrink':           round(home_pfpa_shrink, 3),
            'away_pfpa_shrink':           round(away_pfpa_shrink, 3),
            'pfpa_shrink_full_games':     pfpa_full_games,
            'home_gp':                    home_gp,
            'away_gp':                    away_gp,
            # Dynamic ELO weight
            'dynamic_elo_weight':         round(dynamic_elo_weight, 4),
            'avg_match_shrink':           round(avg_match_shrink, 4),
            'pfpa_max_weight':            pfpa_max_weight,
            'attack_season_weight':       float(config.get('attack_season_weight', 0.7)),
            'defence_season_weight':      float(config.get('defence_season_weight', 0.7)),
            'home_recent_avg_for':        round(home_recent_avg_for, 2) if home_recent_avg_for is not None else None,
            'home_recent_avg_against':    round(home_recent_avg_against, 2) if home_recent_avg_against is not None else None,
            'away_recent_avg_for':        round(away_recent_avg_for, 2) if away_recent_avg_for is not None else None,
            'away_recent_avg_against':    round(away_recent_avg_against, 2) if away_recent_avg_against is not None else None,

            # Home advantage
            'home_team_home_advantage':   round(home_team_ha, 3),
            'league_home_advantage':      compute_league_home_advantage(config),

            # Form
            'home_form_score':            round(home_form_score, 3),
            'home_form_source':           home_form_source,
            'home_form_delta_pts':        round(home_form_delta, 3),
            'away_form_score':            round(away_form_score, 3),
            'away_form_source':           away_form_source,
            'away_form_delta_pts':        round(away_form_delta, 3),
            'form_weight_points':         form_weight_pts,

            # Form interpretation adjustments (rules A-F)
            'home_behavior_adj':          round(home_behavior_adj, 3),
            'away_behavior_adj':          round(away_behavior_adj, 3),
            'home_quality_adj':           round(home_quality_adj, 3),
            'away_quality_adj':           round(away_quality_adj, 3),
            'home_form_score_final':      round(home_form_score_final, 3),
            'away_form_score_final':      round(away_form_score_final, 3),

            # Ratings-based scores (before ELO blend)
            'home_pts_from_ratings':      None,  # not used in Pythagorean path
            'away_pts_from_ratings':      None,  # not used in Pythagorean path
            'margin_from_ratings':        round(margin_from_ratings, 2),
            'total_from_clash':           None,  # not applicable in Pythagorean path
            'total_from_ratings':         round(total_from_ratings, 2),

            # Class vs form balance
            'season_quality_weight':      sq_weight,
            'form_balance_weight':        form_balance_wt,
            'class_margin_contribution':  round(class_margin_contribution, 3),
            'form_margin_contribution':   round(form_margin_contribution, 3),

            # ELO blend (dynamic weight; see dynamic_elo_weight above)
            'margin_from_elo':            round(margin_from_elo, 2),
            'elo_weight':                 elo_weight,          # static config value (long-run asymptote)
            'blended_margin':             round(blended_margin, 2),

            # Defence-over-attack lean
            'defence_attack_bias':        defence_bias,
            'effective_defence_scale':    None,  # not applicable in Pythagorean path

            # Close-call class lean
            'class_lean_threshold':       class_lean_thresh,
            'class_lean_max_pts':         class_lean_max_pts,
            'class_lean_closeness':       round(closeness, 3),
            'class_lean_delta':           round(class_lean_delta, 3),
            'adjusted_margin':            round(adjusted_margin, 3),

            # Totals conservative bias
            'totals_conservative_bias':   totals_bias,
        },
    }
