# audit/model_logger.py
# =============================================================================
# Model run and signal logging.
#
# Bridges the decision layer (pure dicts from generate_signals) to the DB
# write functions in db/queries.py.  All field-name mapping and bookmaker_id
# resolution happens here so db/queries.py stays schema-level only.
#
# Public API:
#   log_model_run(conn, model_run)   -> model_run_id
#   log_adjustments(conn, model_run_id, adjustments) -> None
#   log_signal(conn, signal)         -> signal_id  (or None if signal is unloggable)
# =============================================================================

import logging
from datetime import datetime

from db.queries import (
    get_or_create_bookmaker,
    insert_model_run,
    insert_model_adjustment,
    insert_signal,
)

logger = logging.getLogger(__name__)


def log_model_run(conn, model_run: dict) -> int:
    """
    Persist a completed model run to the model_runs table.

    Expects the model_run dict to contain all required schema fields.
    If 'run_timestamp' is absent, the current UTC time is used.
    If 'run_status' is absent, defaults to 'success'.

    Args:
        conn:      active database connection
        model_run: dict with all model_run fields (see insert_model_run docstring)

    Returns:
        model_run_id
    """
    # Apply defaults for optional fields the caller may omit
    row = dict(model_run)
    if not row.get('run_timestamp'):
        row['run_timestamp'] = datetime.utcnow().isoformat()
    if not row.get('run_status'):
        row['run_status'] = 'success'

    model_run_id = insert_model_run(conn, row)

    logger.info(
        "model_run logged: id=%d match_id=%s version=%s status=%s "
        "final=%.1f/%.1f (home/away)",
        model_run_id,
        row.get('match_id'),
        row.get('model_version'),
        row.get('run_status'),
        row.get('final_home_points', 0),
        row.get('final_away_points', 0),
    )
    return model_run_id


def log_adjustments(conn, model_run_id: int, adjustments: list) -> None:
    """
    Persist all tier adjustments for a model run to model_adjustments table.

    Each adjustment dict must contain:
        tier_number, tier_name, adjustment_code, adjustment_description

    Optional fields default to 0 / 1:
        home_points_delta, away_points_delta, margin_delta, total_delta,
        applied_flag

    'model_run_id' is injected into each adjustment row here — callers do
    not need to set it on each dict.

    Args:
        conn:         active database connection
        model_run_id: the model_run_id that owns these adjustments
        adjustments:  list of adjustment dicts (may be empty)
    """
    if not adjustments:
        return

    for adj in adjustments:
        row = dict(adj)
        row['model_run_id'] = model_run_id
        insert_model_adjustment(conn, row)

    logger.debug(
        "logged %d adjustment(s) for model_run_id=%d",
        len(adjustments), model_run_id,
    )


def log_signal(conn, signal: dict) -> int:
    """
    Persist a generated signal to the signals table.

    Translates field names from the generate_signals() output format to the
    schema column names expected by insert_signal().  Resolves bookmaker_id
    from bookmaker_code using get_or_create_bookmaker.

    Field mapping (generate_signals key → signals table column):
        ev                  → ev_value
        ev_percent          → ev_percent
        raw_kelly           → raw_kelly_fraction
        applied_kelly       → applied_kelly_fraction
        confidence          → confidence_level
        veto                → veto_flag
        recommended_stake   → recommended_stake_amount

    Unloggable signals (returns None with a warning instead of raising):
        - model_run_id is None  (run was not persisted before signals)
        - snapshot_id is None   (signal not linked to a specific snapshot)
        - model_probability is None  (EV calculation failed)

    Args:
        conn:   active database connection
        signal: dict from generate_signals()

    Returns:
        signal_id, or None if the signal could not be logged
    """
    # Guard: required linkage fields
    if signal.get('model_run_id') is None:
        logger.warning(
            "log_signal: model_run_id is None for %s/%s — "
            "signal not persisted (log the model run first)",
            signal.get('market_type'), signal.get('selection_name'),
        )
        return None

    if signal.get('snapshot_id') is None:
        logger.warning(
            "log_signal: snapshot_id is None for %s/%s — "
            "signal not persisted (schema requires snapshot linkage)",
            signal.get('market_type'), signal.get('selection_name'),
        )
        return None

    if signal.get('model_probability') is None:
        logger.warning(
            "log_signal: model_probability is None for %s/%s — "
            "EV calculation failed; signal not persisted",
            signal.get('market_type'), signal.get('selection_name'),
        )
        return None

    # Resolve bookmaker_id
    bookmaker_code = signal.get('bookmaker_code') or ''
    bookmaker_name = signal.get('bookmaker_name') or bookmaker_code
    if not bookmaker_code:
        logger.warning(
            "log_signal: bookmaker_code is missing for %s/%s — signal not persisted",
            signal.get('market_type'), signal.get('selection_name'),
        )
        return None
    bookmaker_id = get_or_create_bookmaker(conn, bookmaker_name, bookmaker_code)

    # Build the DB-ready dict (schema column names)
    db_signal = {
        'model_run_id':            signal['model_run_id'],
        'match_id':                signal.get('match_id'),
        'snapshot_id':             signal['snapshot_id'],
        'bookmaker_id':            bookmaker_id,
        'market_type':             signal.get('market_type'),
        'selection_name':          signal.get('selection_name'),
        'line_value':              signal.get('line_value'),
        'market_odds':             signal.get('market_odds'),
        'model_odds':              signal.get('model_odds'),
        'model_probability':       signal['model_probability'],
        'ev_value':                signal.get('ev', 0.0),
        'ev_percent':              signal.get('ev_percent', 0.0),
        'raw_kelly_fraction':      signal.get('raw_kelly', 0.0),
        'applied_kelly_fraction':  signal.get('applied_kelly', 0.0),
        'capped_stake_fraction':   signal.get('capped_stake_fraction', 0.0),
        'recommended_stake_amount': signal.get('recommended_stake', 0.0),
        'confidence_level':        signal.get('confidence', 'medium'),
        'signal_label':            signal.get('signal_label', 'no_bet'),
        'veto_flag':               int(bool(signal.get('veto', False))),
        'veto_reason':             signal.get('veto_reason'),
    }

    # Replace any remaining None for NOT NULL numeric fields with 0.0
    _numeric_not_null = (
        'ev_value', 'ev_percent',
        'raw_kelly_fraction', 'applied_kelly_fraction',
        'capped_stake_fraction', 'recommended_stake_amount',
    )
    for key in _numeric_not_null:
        if db_signal[key] is None:
            db_signal[key] = 0.0

    signal_id = insert_signal(conn, db_signal)

    logger.debug(
        "signal logged: id=%d run=%d %s %s %s ev=%.1f%% label=%s veto=%s",
        signal_id,
        signal['model_run_id'],
        signal.get('bookmaker_code', ''),
        signal.get('market_type', ''),
        signal.get('selection_name', ''),
        signal.get('ev_percent') or 0.0,
        signal.get('signal_label', ''),
        'YES' if signal.get('veto') else 'no',
    )
    return signal_id
