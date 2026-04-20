# ingestion/team_stats.py
# =============================================================================
# Team statistics ingestion
# =============================================================================
#
# Writes team-level stat snapshots to the team_stats table.
# Called by the spreadsheet importer (and later by any automated ingestion path).
#
# DESIGN
# ------
# ingest_team_stats() is the single write path for team stats.
# It performs an upsert: if a row already exists for (team_id, season, as_of_date),
# all fields are overwritten with the new values.
#
# This means the importer can be re-run as stats are refreshed mid-season
# without creating duplicate rows or requiring manual deduplication.
#
# FIELDS
# ------
# Core season stats:
#   games_played, wins, losses, win_pct, ladder_position
#
# Scoring averages (Tier 1):
#   points_for_avg, points_against_avg
#   home_points_for_avg, home_points_against_avg
#   away_points_for_avg, away_points_against_avg
#
# Tier 1 model ratings:
#   elo_rating, attack_rating, defence_rating, recent_form_rating
#
# Tier 2 yardage bucket fields:
#   run_metres_pg, post_contact_metres_pg   (Signal 1)
#   completion_rate, errors_pg, penalties_pg (Signal 2)
#   kick_metres_pg                           (Signal 3)
#   ruck_speed_score                         (Signal 4 — placeholder)
#
# All fields except the identity triple (team_id, season, as_of_date) are
# nullable. The Tier 2 signals return 0.0 (neutral) for any NULL field.
#
# =============================================================================

import logging

from db.queries import insert_team_stats

logger = logging.getLogger(__name__)

# Integer fields — stored as int (or None) rather than float.
_INT_FIELDS = {'games_played', 'wins', 'losses', 'ladder_position'}


def ingest_team_stats(
    conn,
    team_id: int,
    season: int,
    as_of_date: str,
    raw_stats: dict,
) -> int:
    """
    Write a team stats snapshot to the team_stats table.

    Performs an upsert against (team_id, season, as_of_date):
      - New combination → INSERT.
      - Existing combination → UPDATE all fields with the new values.

    All numeric fields in raw_stats are accepted. Fields absent from raw_stats
    or explicitly set to None are stored as NULL in the database.
    Unknown keys in raw_stats are silently ignored.

    Args:
        conn:       active database connection
        team_id:    canonical team identifier (must already exist in teams table)
        season:     season year (e.g. 2024)
        as_of_date: ISO date string representing when these stats are current,
                    e.g. "2024-05-01". Typically the date before the next round.
        raw_stats:  dict of stat field values. All keys are optional.

                    Accepted keys:
                        Core season: games_played, wins, losses, win_pct,
                                     ladder_position
                        Scoring:     points_for_avg, points_against_avg,
                                     home_points_for_avg, home_points_against_avg,
                                     away_points_for_avg, away_points_against_avg
                        T1 ratings:  elo_rating, attack_rating, defence_rating,
                                     recent_form_rating
                        T2 yardage:  run_metres_pg, post_contact_metres_pg,
                                     completion_rate, errors_pg, penalties_pg,
                                     kick_metres_pg, ruck_speed_score

    Returns:
        team_stat_id of the inserted or updated row
    """
    stats = {
        'team_id':    team_id,
        'season':     season,
        'as_of_date': as_of_date,
    }

    # All accepted stat fields, with their database column names.
    all_fields = [
        # Core season
        'games_played', 'wins', 'losses', 'win_pct', 'ladder_position',
        # Scoring averages
        'points_for_avg', 'points_against_avg',
        'home_points_for_avg', 'home_points_against_avg',
        'away_points_for_avg', 'away_points_against_avg',
        # Tier 1 ratings
        'elo_rating', 'attack_rating', 'defence_rating', 'recent_form_rating',
        # Tier 2 yardage bucket
        'run_metres_pg', 'post_contact_metres_pg',
        'completion_rate', 'errors_pg', 'penalties_pg',
        'kick_metres_pg', 'ruck_speed_score',
    ]

    for field in all_fields:
        value = raw_stats.get(field)
        if value is None:
            stats[field] = None
        elif field in _INT_FIELDS:
            try:
                stats[field] = int(float(value))
            except (TypeError, ValueError):
                logger.warning(
                    "team_id=%d season=%d: cannot convert '%s' to int for field '%s' — storing NULL",
                    team_id, season, value, field,
                )
                stats[field] = None
        else:
            try:
                stats[field] = float(value)
            except (TypeError, ValueError):
                logger.warning(
                    "team_id=%d season=%d: cannot convert '%s' to float for field '%s' — storing NULL",
                    team_id, season, value, field,
                )
                stats[field] = None

    logger.debug(
        "ingest_team_stats: team_id=%d season=%d as_of_date=%s "
        "fields_present=%d",
        team_id, season, as_of_date,
        sum(1 for k, v in stats.items() if k not in ('team_id', 'season', 'as_of_date') and v is not None),
    )

    return insert_team_stats(conn, stats)
