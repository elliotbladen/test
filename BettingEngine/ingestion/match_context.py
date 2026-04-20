# ingestion/match_context.py
# Match context ingestion.
# Populates contextual variables for Tiers 3-7:
#   - rest days, bye status
#   - travel
#   - weather
#   - moon phase flags
#   - injury counts


def ingest_match_context(conn, match_id: int, raw_context: dict) -> int:
    """
    Write contextual match data to the match_context table.

    Args:
        conn: database connection
        match_id: canonical match identifier
        raw_context: dict of contextual fields

    Returns:
        context_id
    """
    raise NotImplementedError


def ingest_injury_report(conn, match_id: int, team_id: int, raw_report: dict) -> int:
    """
    Write a single injury report entry.

    Args:
        conn: database connection
        match_id: canonical match identifier
        team_id: canonical team identifier
        raw_report: dict with player, role, status, notes

    Returns:
        injury_report_id
    """
    raise NotImplementedError
