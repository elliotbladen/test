# ingestion/fixtures.py
# Fixture and results ingestion.
# Responsible for importing match schedules and final scores into the database.


def ingest_fixture(conn, raw_fixture: dict) -> int:
    """
    Normalise a raw fixture record and write to the matches table.

    Args:
        conn: database connection
        raw_fixture: raw data dict from external source

    Returns:
        match_id of the inserted or matched record
    """
    raise NotImplementedError


def ingest_result(conn, match_id: int, raw_result: dict) -> int:
    """
    Write a final match result to the results table.

    Args:
        conn: database connection
        match_id: canonical match identifier
        raw_result: raw result data dict

    Returns:
        result_id
    """
    raise NotImplementedError
