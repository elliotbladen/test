# ingestion/market_snapshots.py
# Bookmaker market snapshot ingestion.
# Appends price snapshots for H2H, handicap, and total markets.
# Never overwrites existing snapshots.


def ingest_snapshot(conn, raw_snapshot: dict) -> int:
    """
    Normalise and append a bookmaker market snapshot.

    Args:
        conn: database connection
        raw_snapshot: raw odds data dict (bookmaker, market_type, odds, line, etc.)

    Returns:
        snapshot_id
    """
    raise NotImplementedError


def ingest_snapshots_bulk(conn, raw_snapshots: list) -> list:
    """
    Ingest a list of raw snapshots. Returns list of snapshot_ids.
    """
    raise NotImplementedError
