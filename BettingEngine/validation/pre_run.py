# validation/pre_run.py
# =============================================================================
# Pre-run data validation
# =============================================================================
#
# Validates that all data required to price a match is present and sane
# before the pricing engine runs. Designed to be called once per match,
# before any tier function is invoked.
#
# DESIGN PHILOSOPHY
# -----------------
# - Returns a RunValidation rather than raising exceptions.
#   The caller decides whether to abort or proceed with degraded data.
# - Distinguishes errors (hard blockers — pricing cannot run safely) from
#   warnings (soft issues — pricing can run but output should be flagged).
# - Every check produces a single, human-readable message.
# - No pricing logic here. No DB writes. Read-only.
#
# USAGE
# -----
#   from validation.pre_run import validate_run_inputs
#
#   validation = validate_run_inputs(
#       conn, match_id, home_stats, away_stats, snapshots, config
#   )
#   if not validation.can_proceed:
#       logger.error("Cannot price match %d: %s", match_id, validation.errors)
#       return
#   for w in validation.warnings:
#       logger.warning("[%s] %s", w['flag'], w['message'])
#
# =============================================================================

import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum allowed age of team stats before a STALE_STATS warning fires.
_STALE_STATS_DAYS = 14

# Maximum allowed age of a market snapshot before a STALE_SNAPSHOT warning fires.
_STALE_SNAPSHOT_HOURS = 48

# Hard bounds for sanity-checking final pricing outputs.
_ABSURD_TOTAL_LOW  = 20.0
_ABSURD_TOTAL_HIGH = 100.0
_ABSURD_MARGIN_ABS = 40.0

# Minimum games played before THIN_DATA warning fires.
_THIN_DATA_GAMES = 4

# Fields that Tier 1 baseline requires to function (not just degrade).
_TIER1_REQUIRED_FIELDS = {'points_for_avg', 'points_against_avg'}

# Fields that are important but whose absence is a warning, not an error.
_TIER1_IMPORTANT_FIELDS = {
    'win_pct', 'games_played', 'elo_rating',
    'home_points_for_avg', 'home_points_against_avg',
    'away_points_for_avg', 'away_points_against_avg',
}

# Tier 2 yardage fields — all nullable; absence is flagged but not an error.
_TIER2_YARDAGE_FIELDS = {
    'run_metres_pg', 'post_contact_metres_pg',
    'completion_rate', 'errors_pg', 'penalties_pg',
    'kick_metres_pg', 'ruck_speed_score',
}


# =============================================================================
# Return type
# =============================================================================

class RunValidation:
    """
    Result of a pre-run validation check.

    Attributes:
        can_proceed  bool  — True if pricing can run (no hard errors).
        errors       list  — Blocking issues. Each item is a dict:
                             {'flag': str, 'message': str}
        warnings     list  — Non-blocking issues. Same shape as errors.
    """

    def __init__(self):
        self.can_proceed: bool = True
        self.errors:   list = []
        self.warnings: list = []

    def add_error(self, flag: str, message: str) -> None:
        self.errors.append({'flag': flag, 'message': message})
        self.can_proceed = False

    def add_warning(self, flag: str, message: str) -> None:
        self.warnings.append({'flag': flag, 'message': message})

    def __repr__(self) -> str:
        return (
            f"RunValidation(can_proceed={self.can_proceed}, "
            f"errors={len(self.errors)}, warnings={len(self.warnings)})"
        )


# =============================================================================
# Public API
# =============================================================================

def validate_run_inputs(
    conn,
    match_id: int,
    home_stats: Optional[dict],
    away_stats: Optional[dict],
    snapshots: list,
    config: dict,
    match_date: Optional[str] = None,
) -> RunValidation:
    """
    Validate all inputs required to price a match.

    Call this before invoking any tier function. If can_proceed is False,
    do not run the pricing engine — the output would be unreliable.

    Args:
        conn:        active database connection (used only for context check)
        match_id:    canonical match identifier
        home_stats:  dict from get_team_stats() for the home team, or None
        away_stats:  dict from get_team_stats() for the away team, or None
        snapshots:   list from get_latest_snapshots_for_match() (may be empty)
        config:      tier1_baseline section of tiers.yaml
        match_date:  ISO date string of the match (used for staleness checks).
                     If None, staleness checks are skipped.

    Returns:
        RunValidation with can_proceed, errors, and warnings populated.
    """
    v = RunValidation()

    _check_match_exists(v, conn, match_id)
    _check_team_stats(v, home_stats, 'home', config)
    _check_team_stats(v, away_stats, 'away', config)
    _check_stats_staleness(v, home_stats, 'home', match_date)
    _check_stats_staleness(v, away_stats, 'away', match_date)
    _check_snapshots(v, snapshots, match_date)
    _check_match_context(v, conn, match_id)

    return v


def validate_pricing_output(
    baseline_home: float,
    baseline_away: float,
    final_home: float,
    final_away: float,
) -> RunValidation:
    """
    Sanity-check the outputs of the pricing engine after all tiers have run.

    Call this after derive_final_prices(). Does not abort anything — returns
    a RunValidation that the caller can inspect and attach to the model run.

    Args:
        baseline_home: baseline_home_points from compute_baseline()
        baseline_away: baseline_away_points from compute_baseline()
        final_home:    final expected home points (after all tier adjustments)
        final_away:    final expected away points (after all tier adjustments)

    Returns:
        RunValidation — will have no errors, only warnings.
    """
    v = RunValidation()

    final_total  = final_home + final_away
    final_margin = final_home - final_away
    tier_delta   = abs((final_home - baseline_home) + (final_away - baseline_away))

    if final_total < _ABSURD_TOTAL_LOW:
        v.add_warning(
            'ABSURD_TOTAL',
            f"final_total={final_total:.1f} is below {_ABSURD_TOTAL_LOW} — "
            "check tier adjustments and config weights."
        )
    elif final_total > _ABSURD_TOTAL_HIGH:
        v.add_warning(
            'ABSURD_TOTAL',
            f"final_total={final_total:.1f} exceeds {_ABSURD_TOTAL_HIGH} — "
            "check team stats (avg_points_for) and config weights."
        )

    if abs(final_margin) > _ABSURD_MARGIN_ABS:
        v.add_warning(
            'ABSURD_MARGIN',
            f"abs(final_margin)={abs(final_margin):.1f} exceeds {_ABSURD_MARGIN_ABS} — "
            "a margin this large is implausible for NRL. Investigate tier adjustments."
        )

    if tier_delta > 10.0:
        v.add_warning(
            'LARGE_TIER_ADJUSTMENT',
            f"Total tier adjustments shifted the combined score by {tier_delta:.1f} pts "
            f"from baseline — unusually large. Check tier weights and input data."
        )

    return v


# =============================================================================
# Internal checks
# =============================================================================

def _check_match_exists(v: RunValidation, conn, match_id: int) -> None:
    """Error if the match does not exist in the database."""
    row = conn.execute(
        "SELECT match_id FROM matches WHERE match_id = ?", (match_id,)
    ).fetchone()
    if row is None:
        v.add_error(
            'MATCH_NOT_FOUND',
            f"match_id={match_id} does not exist in the matches table. "
            "Run fixture ingestion first."
        )


def _check_team_stats(
    v: RunValidation,
    stats: Optional[dict],
    side: str,
    config: dict,
) -> None:
    """
    Check that team stats are present and contain the fields the model needs.

    Adds an error if stats are entirely missing.
    Adds an error if any Tier 1 required fields are NULL.
    Adds warnings for important-but-optional fields and yardage fields.
    """
    if stats is None:
        v.add_error(
            'MISSING_TEAM_STATS',
            f"{side} team stats not found in database. "
            "Import a team stats sheet for this team and season before pricing."
        )
        return

    # Hard requirement: need at least scoring averages for a meaningful baseline
    null_required = [f for f in _TIER1_REQUIRED_FIELDS if stats.get(f) is None]
    if null_required:
        v.add_error(
            'PARTIAL_TEAM_STATS',
            f"{side} team stats exist but required fields are NULL: {null_required}. "
            "Re-import a complete stats sheet that includes these columns."
        )

    # Important fields: degraded but not broken
    null_important = [f for f in _TIER1_IMPORTANT_FIELDS if stats.get(f) is None]
    if null_important:
        v.add_warning(
            'PARTIAL_TEAM_STATS',
            f"{side} team stats are missing fields that improve accuracy: "
            f"{null_important}. Model will use defaults for these."
        )

    # Thin data gate
    games_played = stats.get('games_played') or 0
    min_sample = int(config.get('min_games_for_home_advantage', 4))
    if games_played < _THIN_DATA_GAMES:
        v.add_warning(
            'THIN_DATA',
            f"{side} team has only {games_played} game(s) in stats. "
            f"Signals are unreliable below {_THIN_DATA_GAMES} games — "
            "treat pricing output with caution."
        )
    elif games_played < min_sample:
        v.add_warning(
            'THIN_DATA',
            f"{side} team has {games_played} game(s) — below "
            f"min_games_for_home_advantage ({min_sample}). "
            "Home advantage will default to league average."
        )

    # ELO fallback flag
    if stats.get('elo_rating') is None:
        v.add_warning(
            'ELO_FALLBACK',
            f"{side} team has no ELO rating stored. "
            "ELO margin will be estimated from season quality (less reliable early season)."
        )

    # Yardage fields — all nullable, but worth surfacing
    null_yardage = [f for f in _TIER2_YARDAGE_FIELDS if stats.get(f) is None]
    if null_yardage:
        v.add_warning(
            'NULL_YARDAGE_FIELDS',
            f"{side} team is missing Tier 2 yardage fields: {null_yardage}. "
            "Yardage signals will be suppressed or partially computed."
        )


def _check_stats_staleness(
    v: RunValidation,
    stats: Optional[dict],
    side: str,
    match_date: Optional[str],
) -> None:
    """Warn if the stats snapshot is older than _STALE_STATS_DAYS before the match."""
    if stats is None or match_date is None:
        return

    as_of_date_str = stats.get('as_of_date')
    if as_of_date_str is None:
        return

    try:
        as_of = date.fromisoformat(str(as_of_date_str))
        match = date.fromisoformat(str(match_date))
    except ValueError:
        return

    gap_days = (match - as_of).days
    if gap_days > _STALE_STATS_DAYS:
        v.add_warning(
            'STALE_STATS',
            f"{side} team stats as_of_date={as_of_date_str} is {gap_days} day(s) "
            f"before match_date={match_date} (threshold: {_STALE_STATS_DAYS} days). "
            "Stats may not reflect the team's current form."
        )


def _check_snapshots(
    v: RunValidation,
    snapshots: list,
    match_date: Optional[str],
) -> None:
    """Warn if no snapshots exist or if all snapshots are stale."""
    if not snapshots:
        v.add_warning(
            'NO_SNAPSHOTS',
            "No market snapshots found for this match. "
            "EV calculation cannot run — import odds before pricing."
        )
        return

    if match_date is None:
        return

    try:
        match_dt = datetime.fromisoformat(f"{match_date} 00:00:00")
    except ValueError:
        return

    stale_threshold = timedelta(hours=_STALE_SNAPSHOT_HOURS)
    stale_count = 0
    freshest_age_hours = None

    for snap in snapshots:
        captured_at_str = snap.get('captured_at')
        if captured_at_str is None:
            continue
        try:
            # Handle both "YYYY-MM-DD HH:MM:SS" and "YYYY-MM-DDTHH:MM:SS"
            captured_at = datetime.fromisoformat(str(captured_at_str).replace('T', ' '))
        except ValueError:
            continue

        age = match_dt - captured_at
        age_hours = age.total_seconds() / 3600.0
        if freshest_age_hours is None or age_hours < freshest_age_hours:
            freshest_age_hours = age_hours
        if age > stale_threshold:
            stale_count += 1

    if stale_count == len(snapshots) and freshest_age_hours is not None:
        v.add_warning(
            'STALE_SNAPSHOT',
            f"All {len(snapshots)} snapshot(s) are more than {_STALE_SNAPSHOT_HOURS}h "
            f"before match time (freshest is {freshest_age_hours:.0f}h old). "
            "Odds may have moved significantly — re-capture before acting on signals."
        )


def _check_match_context(v: RunValidation, conn, match_id: int) -> None:
    """Warn if match_context is missing — Tier 3 situational signals cannot run."""
    # Only run this check if the matches table exists (guards against bare DBs)
    row = conn.execute(
        "SELECT match_id FROM match_context WHERE match_id = ?", (match_id,)
    ).fetchone()
    if row is None:
        v.add_warning(
            'NO_MATCH_CONTEXT',
            f"No match_context record for match_id={match_id}. "
            "Tier 3 situational signals (bye, turnaround, etc.) cannot run."
        )
