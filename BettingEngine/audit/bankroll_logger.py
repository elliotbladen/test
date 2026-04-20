# audit/bankroll_logger.py
# =============================================================================
# Bankroll state tracking.
# Records bankroll snapshots after bet placement and settlement.
#
# bankroll_log is append-only. Rows are never updated or deleted.
# Each row represents a point-in-time bankroll state.
# =============================================================================

import logging
from datetime import datetime

from db.queries import insert_bankroll_log

logger = logging.getLogger(__name__)


def log_bankroll_state(conn, entry: dict) -> int:
    """
    Append a bankroll state entry to the bankroll_log table.

    bankroll_log is append-only — call this after every bet placement
    or settlement event, not to update an existing row.

    If 'log_timestamp' is absent, the current UTC time is used.

    Args:
        conn:  active database connection
        entry: dict with keys:
                   starting_bankroll  float  — bankroll at the start of this period
                   ending_bankroll    float  — bankroll at the end of this period
                   open_exposure      float  — total stake in unsettled bets (default 0)
                   closed_pnl         float  — realised PnL this period (default 0)
                   notes              str    — optional human note
                   log_timestamp      str    — ISO datetime (default: now)

    Returns:
        bankroll_log_id
    """
    row = dict(entry)
    if not row.get('log_timestamp'):
        row['log_timestamp'] = datetime.utcnow().isoformat()

    bankroll_log_id = insert_bankroll_log(conn, row)

    logger.info(
        "bankroll logged: id=%d start=%.2f end=%.2f exposure=%.2f pnl=%.2f",
        bankroll_log_id,
        row['starting_bankroll'],
        row['ending_bankroll'],
        row.get('open_exposure', 0.0),
        row.get('closed_pnl', 0.0),
    )
    return bankroll_log_id


def get_current_bankroll(conn) -> float:
    """
    Return the most recent ending_bankroll from bankroll_log.

    Queries by log_timestamp DESC to find the most recently recorded
    bankroll state.

    Returns:
        float — the most recent ending_bankroll, or 0.0 if no rows exist.
    """
    row = conn.execute(
        """
        SELECT ending_bankroll
        FROM   bankroll_log
        ORDER  BY log_timestamp DESC
        LIMIT  1
        """
    ).fetchone()

    if row is None:
        logger.warning(
            "get_current_bankroll: no bankroll_log rows found — returning 0.0"
        )
        return 0.0

    return float(row['ending_bankroll'])
