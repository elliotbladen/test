"""Bookmaker market snapshot ingestion.

Market snapshots are append-only by design. Every run records what the
bookmaker/source was showing at that moment so we can reconstruct line movement
later instead of overwriting history.
"""

from __future__ import annotations

from db.queries import get_or_create_bookmaker, insert_market_snapshot
from normalization.normalizers import (
    normalize_bookmaker_code,
    normalize_datetime,
    normalize_market_type,
    normalize_odds_decimal,
    normalize_selection_name,
)


def ingest_snapshot(conn, raw_snapshot: dict) -> int:
    """Normalize and append a bookmaker market snapshot.

    Required raw_snapshot keys:
        match_id, bookmaker, captured_at, market_type, selection, odds

    Optional keys:
        bookmaker_code, line, is_opening, is_closing, source_url, source_method

    Returns:
        snapshot_id
    """
    bookmaker_name = str(raw_snapshot["bookmaker"]).strip()
    bookmaker_code = raw_snapshot.get("bookmaker_code") or bookmaker_name
    bookmaker_code = normalize_bookmaker_code(bookmaker_code)
    bookmaker_id = get_or_create_bookmaker(conn, bookmaker_name, bookmaker_code)

    snapshot = {
        "match_id": int(raw_snapshot["match_id"]),
        "bookmaker_id": bookmaker_id,
        "captured_at": normalize_datetime(raw_snapshot["captured_at"]),
        "market_type": normalize_market_type(raw_snapshot["market_type"]),
        "selection_name": normalize_selection_name(raw_snapshot["selection"]),
        "line_value": _optional_float(raw_snapshot.get("line")),
        "odds_decimal": normalize_odds_decimal(raw_snapshot["odds"]),
        "is_opening": int(bool(raw_snapshot.get("is_opening", 0))),
        "is_closing": int(bool(raw_snapshot.get("is_closing", 0))),
        "source_url": raw_snapshot.get("source_url"),
        "source_method": raw_snapshot.get("source_method", "api"),
    }
    return insert_market_snapshot(conn, snapshot)


def ingest_snapshots_bulk(conn, raw_snapshots: list) -> list:
    """Ingest a list of raw snapshots and return their snapshot IDs."""
    snapshot_ids = []
    for raw_snapshot in raw_snapshots:
        snapshot_ids.append(ingest_snapshot(conn, raw_snapshot))
    return snapshot_ids


def _optional_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return float(value)
