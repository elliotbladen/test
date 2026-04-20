# ingestion/spreadsheet_importer.py
# =============================================================================
# Historical NRL Spreadsheet Importer
# =============================================================================
#
# Imports historical results and bookmaker odds from Excel or CSV files
# into the local SQLite database.
#
# HOW TO RUN
# ----------
# From the project root:
#
#   python -m ingestion.spreadsheet_importer \
#       --results  data/imports/results.csv \
#       --odds     data/imports/odds.csv \
#       --settings config/settings.yaml
#
# Run --results before --odds. The odds importer looks up matches that must
# already exist in the database.
#
# You can run either flag alone:
#   python -m ingestion.spreadsheet_importer --results data/imports/results.csv
#   python -m ingestion.spreadsheet_importer --odds    data/imports/odds.csv
#
# FILES ACCEPTED
# --------------
# .csv  — standard comma-separated
# .xlsx — Excel workbook (first sheet is used)
# .xls  — legacy Excel
#
# =============================================================================
# RESULTS FILE FORMAT
# =============================================================================
#
# Required columns (exact header names, case-insensitive):
#
#   season       — integer year, e.g. 2024
#   round        — integer round number, e.g. 1
#   match_date   — any standard date format, e.g. "2024-03-07" or "7/3/2024"
#   home_team    — team name (see alias table in normalizers.py)
#   away_team    — team name
#   venue        — venue name, e.g. "Accor Stadium"
#   home_score   — integer
#   away_score   — integer
#
# Optional columns:
#
#   kickoff_time     — time string, e.g. "19:30". Defaults to "19:00" if absent.
#   referee          — referee name. Skipped if absent or blank.
#   source_match_key — your external identifier for idempotent re-imports.
#
# Example rows:
#   season,round,match_date,home_team,away_team,venue,home_score,away_score
#   2024,1,2024-03-07,Penrith Panthers,Brisbane Broncos,BlueBet Stadium,20,16
#   2024,1,2024-03-08,Sydney Roosters,Rabbitohs,Allianz Stadium,24,18
#
# =============================================================================
# ODDS FILE FORMAT
# =============================================================================
#
# Required columns:
#
#   season       — integer year
#   round        — integer round number
#   match_date   — date (used to identify the match)
#   home_team    — team name (must match a team already in the database)
#   away_team    — team name
#   bookmaker    — bookmaker name, e.g. "Bet365" or "Pinnacle"
#   market_type  — h2h | handicap | total (or common aliases, see normalizers.py)
#   selection    — home | away | over | under (or common aliases)
#   odds         — decimal odds, e.g. 1.85
#
# Optional columns:
#
#   line         — handicap or total line value (leave blank for h2h)
#   captured_at  — datetime of the price capture. Defaults to match_date + "00:00:00"
#   is_opening   — 1 if opening price, 0 otherwise. Defaults to 0.
#   is_closing   — 1 if closing price, 0 otherwise. Defaults to 0.
#   source_url   — URL the price was captured from.
#
# Example rows:
#   season,round,match_date,home_team,away_team,bookmaker,market_type,selection,odds
#   2024,1,2024-03-07,Penrith Panthers,Brisbane Broncos,Pinnacle,h2h,home,1.62
#   2024,1,2024-03-07,Penrith Panthers,Brisbane Broncos,Pinnacle,h2h,away,2.38
#   2024,1,2024-03-07,Penrith Panthers,Brisbane Broncos,Bet365,handicap,home,1.90
#
# Note: running the odds import twice on the same file will create duplicate
# snapshot rows. market_snapshots is append-only by design. Re-run only if
# the file contains genuinely new price captures.
#
# =============================================================================
# TEAM STATS FILE FORMAT
# =============================================================================
#
# Required columns:
#
#   team         — team name (see alias table in normalizers.py)
#   season       — integer year, e.g. 2024
#   as_of_date   — ISO date, e.g. "2024-05-01" (the date these stats are current)
#
# Optional columns (all map directly to team_stats fields; NULL if absent):
#
#   Core season:
#     games_played     — integer games played to date
#     wins             — integer wins to date
#     losses           — integer losses to date
#     win_pct          — float, e.g. 0.625 (wins / games_played)
#     ladder_position  — integer 1–16 (1 = top of ladder)
#
#   Scoring averages:
#     points_for_avg            — season avg points scored per game
#     points_against_avg        — season avg points conceded per game
#     home_points_for_avg       — home games only, avg points scored
#     home_points_against_avg   — home games only, avg points conceded
#     away_points_for_avg       — away games only, avg points scored
#     away_points_against_avg   — away games only, avg points conceded
#
#   Tier 1 model ratings (pre-computed; can be NULL if derived at runtime):
#     elo_rating, attack_rating, defence_rating, recent_form_rating
#
#   Tier 2 yardage bucket fields:
#     run_metres_pg           — avg run metres per game
#     post_contact_metres_pg  — avg post-contact metres per game (optional)
#     completion_rate         — set completion rate, e.g. 0.75 for 75%
#     errors_pg               — unforced errors per game
#     penalties_pg            — penalties conceded per game
#     kick_metres_pg          — avg kick metres per game
#     ruck_speed_score        — ruck speed composite (leave blank; not yet sourced)
#
# The team stats import is an upsert: re-running the same file is safe and
# will overwrite any previously imported stats for the same (team, season, date).
#
# NULL-overwrite protection:
# If a column is absent from the import sheet (or blank), its value is treated
# as "not provided" — the importer will PRESERVE any existing non-NULL value in
# the database rather than silently overwriting it with NULL.
# A warning is logged for each preserved field so you can see what was retained.
# To intentionally overwrite a field to NULL, include the column in your sheet
# and leave the cell blank — this is treated the same as absent (NULL is preserved).
# To overwrite an existing value, include the column in your sheet with the new
# value populated.
#
# Example rows:
#   team,season,as_of_date,games_played,win_pct,run_metres_pg,completion_rate
#   Penrith Panthers,2024,2024-05-01,10,0.8,1680.4,0.77
#   Brisbane Broncos,2024,2024-05-01,10,0.6,1590.1,0.74
#
# =============================================================================

import logging
import os
from typing import Optional

import pandas as pd

from db.queries import (
    get_or_create_team,
    get_or_create_venue,
    get_or_create_referee,
    get_or_create_bookmaker,
    get_or_create_match,
    find_match,
    insert_result,
    insert_market_snapshot,
)
from normalization.normalizers import (
    normalize_team_name,
    normalize_venue_name,
    normalize_market_type,
    normalize_selection_name,
    normalize_bookmaker_code,
    normalize_date,
    normalize_datetime,
    normalize_odds_decimal,
)
from normalization.validators import (
    validate_result,
    validate_market_snapshot,
    validate_results_dataframe,
    validate_odds_dataframe,
    format_validation_report,
)

logger = logging.getLogger(__name__)

# Column names are lowercased and stripped before lookup
_RESULTS_REQUIRED_COLS = {'season', 'round', 'match_date', 'home_team', 'away_team',
                           'venue', 'home_score', 'away_score'}
_ODDS_REQUIRED_COLS    = {'season', 'round', 'match_date', 'home_team', 'away_team',
                           'bookmaker', 'market_type', 'selection', 'odds'}
_TEAM_STATS_REQUIRED_COLS       = {'team', 'season', 'as_of_date'}
_TEAM_STYLE_STATS_REQUIRED_COLS = {'team', 'season', 'as_of_date'}
_TEAM_STYLE_STATS_OPTIONAL_COLS = ['lb_pg', 'tb_pg', 'mt_pg', 'lbc_pg']

# All optional numeric stat columns. Any column in this list that is absent
# from the source spreadsheet is stored as NULL — never raises an error.
# Integer fields (games_played, wins, losses, ladder_position) are handled
# by ingest_team_stats; they are listed here as strings for column lookup only.
_TEAM_STATS_OPTIONAL_COLS = [
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


# =============================================================================
# Public API
# =============================================================================

def import_historical_results(conn, filepath: str) -> dict:
    """
    Import historical match results from a CSV or Excel file.

    Reads the file row by row. For each row:
      - normalises team names, venue, and date
      - gets or creates team, venue, referee, and match records
      - inserts the result (skips if a result for this match already exists)

    Runs a pre-flight validation report before importing. Problems are logged
    with row numbers and field names. Rows with errors are skipped; rows with
    only warnings are still imported.

    Args:
        conn: active database connection
        filepath: path to .csv, .xlsx, or .xls file

    Returns:
        summary dict with keys: imported, skipped, errors, error_detail, validation
    """
    df = _read_file(filepath)
    df = _normalise_columns(df)
    _assert_required_columns(df, _RESULTS_REQUIRED_COLS, filepath)

    # --- Pre-flight validation ---
    validation = validate_results_dataframe(df)
    report_str = format_validation_report(validation, filepath)
    if validation['error_count'] > 0 or validation['warning_count'] > 0:
        for line in report_str.splitlines():
            logger.warning(line) if 'ERROR' in line or validation['error_count'] > 0 else logger.info(line)
    else:
        logger.info("Pre-flight validation passed: no issues found in %s", filepath)

    summary = {'imported': 0, 'skipped': 0, 'errors': 0, 'error_detail': [],
               'validation': validation}

    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-based + header row
        try:
            result_id, was_inserted = _process_result_row(conn, row)
            if was_inserted:
                summary['imported'] += 1
                logger.debug("Row %d: imported result_id=%d", row_num, result_id)
            else:
                summary['skipped'] += 1
                logger.debug("Row %d: result already exists, skipped", row_num)
        except Exception as exc:
            summary['errors'] += 1
            summary['error_detail'].append({'row': row_num, 'error': str(exc)})
            logger.warning("Row %d: error — %s", row_num, exc)

    _log_summary('Results', filepath, summary)
    return summary


def import_historical_odds(conn, filepath: str) -> dict:
    """
    Import historical bookmaker odds from a CSV or Excel file.

    Reads the file row by row. For each row:
      - normalises team names, bookmaker, market type, selection, and odds
      - looks up the existing match (match must already exist — run results import first)
      - gets or creates the bookmaker record
      - appends the market snapshot (always inserts, never deduplicates)

    Runs a pre-flight validation report before importing.

    Args:
        conn: active database connection
        filepath: path to .csv, .xlsx, or .xls file

    Returns:
        summary dict with keys: imported, skipped, errors, error_detail, validation
    """
    df = _read_file(filepath)
    df = _normalise_columns(df)
    _assert_required_columns(df, _ODDS_REQUIRED_COLS, filepath)

    # --- Pre-flight validation ---
    validation = validate_odds_dataframe(df)
    report_str = format_validation_report(validation, filepath)
    if validation['error_count'] > 0 or validation['warning_count'] > 0:
        for line in report_str.splitlines():
            logger.warning(line) if 'ERROR' in line or validation['error_count'] > 0 else logger.info(line)
    else:
        logger.info("Pre-flight validation passed: no issues found in %s", filepath)

    summary = {'imported': 0, 'skipped': 0, 'errors': 0, 'error_detail': [],
               'validation': validation}

    for idx, row in df.iterrows():
        row_num = idx + 2
        try:
            snapshot_id = _process_odds_row(conn, row)
            summary['imported'] += 1
            logger.debug("Row %d: imported snapshot_id=%d", row_num, snapshot_id)
        except Exception as exc:
            summary['errors'] += 1
            summary['error_detail'].append({'row': row_num, 'error': str(exc)})
            logger.warning("Row %d: error — %s", row_num, exc)

    _log_summary('Odds', filepath, summary)
    return summary


def import_historical_team_stats(conn, filepath: str) -> dict:
    """
    Import team stats from a CSV or Excel spreadsheet into team_stats.

    Each row represents one team's stats as of a specific date. Re-running
    the same file is safe — rows are upserted, not duplicated.

    NULL-overwrite protection: fields absent from the sheet that already have
    a non-NULL value in the database are silently preserved. A warning is logged
    for each preserved field. This prevents a partial sheet (e.g. yardage-only)
    from wiping out scoring averages imported from an earlier complete sheet.

    Required columns: team, season, as_of_date
    Optional columns: see file format docs at the top of this module.

    Args:
        conn:     active database connection
        filepath: path to .csv, .xlsx, or .xls file

    Returns:
        summary dict with keys: imported, skipped, errors, error_detail, preserved_fields
        where preserved_fields is the total count of fields that were retained from
        existing DB values rather than overwritten with NULL.
    """
    df = _read_file(filepath)
    df = _normalise_columns(df)
    _assert_required_columns(df, _TEAM_STATS_REQUIRED_COLS, filepath)

    summary = {'imported': 0, 'skipped': 0, 'errors': 0, 'error_detail': [],
               'preserved_fields': 0}

    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-based + header row
        try:
            team_stat_id, preserved_count = _process_team_stats_row(conn, row)
            summary['imported'] += 1
            summary['preserved_fields'] += preserved_count
            logger.debug("Row %d: upserted team_stat_id=%d (preserved %d field(s))",
                         row_num, team_stat_id, preserved_count)
        except Exception as exc:
            summary['errors'] += 1
            summary['error_detail'].append({'row': row_num, 'error': str(exc)})
            logger.warning("Row %d: error — %s", row_num, exc)

    _log_summary('Team stats', filepath, summary)
    return summary


def import_historical_team_style_stats(conn, filepath: str) -> dict:
    """
    Import Tier 2 style stats from a CSV or Excel file into team_style_stats.

    Each row is one team's style snapshot as of a specific date.
    Re-running the same file is safe — rows are upserted, not duplicated.

    Null-overwrite protection: stat columns absent from the sheet (or blank)
    do NOT overwrite existing non-NULL values in the database. This is handled
    in the SQL upsert via COALESCE, so no Python-level pre-check is needed.

    Required columns: team, season, as_of_date
    Optional stat columns: lb_pg, tb_pg, mt_pg, lbc_pg
    Optional audit column: source_note

    Args:
        conn:     active database connection
        filepath: path to .csv, .xlsx, or .xls file

    Returns:
        summary dict with keys: imported, skipped, errors, error_detail
    """
    df = _read_file(filepath)
    df = _normalise_columns(df)
    _assert_required_columns(df, _TEAM_STYLE_STATS_REQUIRED_COLS, filepath)

    summary = {'imported': 0, 'skipped': 0, 'errors': 0, 'error_detail': []}

    for idx, row in df.iterrows():
        row_num = idx + 2
        try:
            _process_team_style_stats_row(conn, row)
            summary['imported'] += 1
        except Exception as exc:
            summary['errors'] += 1
            summary['error_detail'].append({'row': row_num, 'error': str(exc)})
            logger.warning("Row %d: error — %s", row_num, exc)

    _log_summary('Team style stats', filepath, summary)
    return summary


# =============================================================================
# Row processors
# =============================================================================

def _process_result_row(conn, row) -> tuple:
    """
    Process one row from the results spreadsheet.
    Returns (result_id, was_inserted).
    """
    # Normalise team and venue names
    home_name  = normalize_team_name(_str(row, 'home_team'))
    away_name  = normalize_team_name(_str(row, 'away_team'))
    venue_name = normalize_venue_name(_str(row, 'venue'))

    _warn_if_unknown_team(home_name, _str(row, 'home_team'))
    _warn_if_unknown_team(away_name, _str(row, 'away_team'))
    _warn_if_unknown_venue(venue_name, _str(row, 'venue'))

    # Normalise date and build kickoff datetime
    match_date = normalize_date(_str(row, 'match_date'))
    kickoff_time = _str(row, 'kickoff_time') if 'kickoff_time' in row.index else '19:00'
    if not kickoff_time or str(kickoff_time).strip().lower() in ('', 'nan'):
        kickoff_time = '19:00'
    kickoff_datetime = normalize_datetime(f"{match_date} {kickoff_time}")

    season = int(row['season'])
    round_number = int(row['round'])

    # Resolve/create reference records
    home_team_id = get_or_create_team(conn, home_name)
    away_team_id = get_or_create_team(conn, away_name)
    venue_id = get_or_create_venue(conn, venue_name)

    referee_id: Optional[int] = None
    referee_raw = _str(row, 'referee') if 'referee' in row.index else ''
    if referee_raw and referee_raw.lower() != 'nan':
        referee_id = get_or_create_referee(conn, referee_raw.strip())

    source_key_raw = _str(row, 'source_match_key') if 'source_match_key' in row.index else ''
    source_key = source_key_raw.strip() if source_key_raw and source_key_raw.lower() != 'nan' else None

    # Get or create the match
    match_id = get_or_create_match(conn, {
        'sport':            'NRL',
        'competition':      'NRL',
        'season':           season,
        'round_number':     round_number,
        'match_date':       match_date,
        'kickoff_datetime': kickoff_datetime,
        'home_team_id':     home_team_id,
        'away_team_id':     away_team_id,
        'venue_id':         venue_id,
        'status':           'completed',
        'referee_id':       referee_id,
        'source_match_key': source_key,
    })

    # Build result dict
    home_score = int(row['home_score'])
    away_score = int(row['away_score'])
    total_score = home_score + away_score
    margin = home_score - away_score

    if margin > 0:
        winning_team_id = home_team_id
    elif margin < 0:
        winning_team_id = away_team_id
    else:
        winning_team_id = None  # draw (rare in NRL but handled)

    result = {
        'match_id':       match_id,
        'home_score':     home_score,
        'away_score':     away_score,
        'total_score':    total_score,
        'margin':         margin,
        'winning_team_id': winning_team_id,
        'result_status':  'final',
    }

    is_valid, errors = validate_result(result)
    if not is_valid:
        raise ValueError(f"Result validation failed: {errors}")

    return insert_result(conn, result)


def _process_odds_row(conn, row) -> int:
    """
    Process one row from the odds spreadsheet.
    Returns snapshot_id.
    """
    home_name = normalize_team_name(_str(row, 'home_team'))
    away_name = normalize_team_name(_str(row, 'away_team'))

    _warn_if_unknown_team(home_name, _str(row, 'home_team'))
    _warn_if_unknown_team(away_name, _str(row, 'away_team'))

    season = int(row['season'])
    round_number = int(row['round'])

    home_team_id = get_or_create_team(conn, home_name)
    away_team_id = get_or_create_team(conn, away_name)

    # Match must already exist (run results import first)
    match_id = find_match(conn, season, round_number, home_team_id, away_team_id)
    if match_id is None:
        raise ValueError(
            f"Match not found in database: season={season} round={round_number} "
            f"home='{home_name}' away='{away_name}'. "
            "Run the results import first."
        )

    bookmaker_raw = _str(row, 'bookmaker')
    bookmaker_code = normalize_bookmaker_code(bookmaker_raw)
    bookmaker_id = get_or_create_bookmaker(conn, bookmaker_raw.strip(), bookmaker_code)

    market_type    = normalize_market_type(_str(row, 'market_type'))
    selection_name = normalize_selection_name(_str(row, 'selection'))
    odds_decimal   = normalize_odds_decimal(row['odds'])

    # Optional fields
    line_raw = row.get('line') if 'line' in row.index else None
    line_value = float(line_raw) if _is_present(line_raw) else None

    match_date = normalize_date(_str(row, 'match_date'))
    captured_at_raw = row.get('captured_at') if 'captured_at' in row.index else None
    if _is_present(captured_at_raw):
        captured_at = normalize_datetime(str(captured_at_raw))
    else:
        captured_at = f"{match_date} 00:00:00"

    is_opening = int(row['is_opening']) if 'is_opening' in row.index and _is_present(row.get('is_opening')) else 0
    is_closing  = int(row['is_closing'])  if 'is_closing'  in row.index and _is_present(row.get('is_closing'))  else 0

    source_url_raw = row.get('source_url') if 'source_url' in row.index else None
    source_url = str(source_url_raw).strip() if _is_present(source_url_raw) else None

    snapshot = {
        'match_id':       match_id,
        'bookmaker_id':   bookmaker_id,
        'captured_at':    captured_at,
        'market_type':    market_type,
        'selection_name': selection_name,
        'line_value':     line_value,
        'odds_decimal':   odds_decimal,
        'is_opening':     is_opening,
        'is_closing':     is_closing,
        'source_url':     source_url,
        'source_method':  'manual',
    }

    is_valid, errors = validate_market_snapshot(snapshot)
    if not is_valid:
        raise ValueError(f"Snapshot validation failed: {errors}")

    return insert_market_snapshot(conn, snapshot)


def _process_team_stats_row(conn, row) -> tuple:
    """
    Process one row from the team stats spreadsheet.

    Normalises the team name, resolves the team_id, extracts all optional
    stat fields, applies NULL-overwrite protection, and calls ingest_team_stats
    to upsert the row.

    NULL-overwrite protection:
    If a field is absent from this row (raw_stats value is None) but the
    database already has a non-NULL value for that field on the same
    (team_id, season, as_of_date) key, the existing value is preserved.
    A warning is logged listing all preserved fields.

    Returns:
        (team_stat_id, preserved_count)
        where preserved_count is the number of fields kept from the existing DB row.
    """
    from ingestion.team_stats import ingest_team_stats

    team_name = normalize_team_name(_str(row, 'team'))
    _warn_if_unknown_team(team_name, _str(row, 'team'))

    season     = int(row['season'])
    as_of_date = normalize_date(_str(row, 'as_of_date'))
    team_id    = get_or_create_team(conn, team_name)

    # Extract optional numeric fields. Any absent, blank, or non-numeric
    # value becomes None — will be checked against existing DB values below.
    raw_stats = {}
    for col in _TEAM_STATS_OPTIONAL_COLS:
        if col in row.index and _is_present(row.get(col)):
            try:
                raw_stats[col] = float(row[col])
            except (ValueError, TypeError):
                logger.warning(
                    "Column '%s' value '%s' is not numeric — storing NULL",
                    col, row.get(col),
                )
                raw_stats[col] = None
        else:
            raw_stats[col] = None

    # NULL-overwrite protection:
    # Look up any existing row for this exact (team_id, season, as_of_date).
    # For each field that is None in this import but non-NULL in the DB,
    # retain the existing value rather than silently overwriting with NULL.
    preserved_count = 0
    existing_row = conn.execute(
        "SELECT * FROM team_stats WHERE team_id = ? AND season = ? AND as_of_date = ?",
        (team_id, season, as_of_date),
    ).fetchone()

    if existing_row is not None:
        existing = dict(existing_row)
        preserved_fields = []
        for field in _TEAM_STATS_OPTIONAL_COLS:
            if raw_stats.get(field) is None and existing.get(field) is not None:
                raw_stats[field] = existing[field]
                preserved_fields.append(field)
        preserved_count = len(preserved_fields)
        if preserved_fields:
            logger.warning(
                "team='%s' season=%d as_of_date=%s: %d field(s) absent from import sheet "
                "but have existing non-NULL values — preserving existing data: %s. "
                "Include these columns in your sheet to overwrite them.",
                team_name, season, as_of_date, preserved_count, preserved_fields,
            )

    team_stat_id = ingest_team_stats(conn, team_id, season, as_of_date, raw_stats)
    return team_stat_id, preserved_count


def _process_team_style_stats_row(conn, row) -> int:
    """
    Process one row from the team style stats spreadsheet.

    Normalises the team name, resolves team_id, extracts optional stat
    columns, and upserts via insert_team_style_stats().

    Null-overwrite protection is handled in the SQL upsert (COALESCE):
    absent or blank columns stay NULL in Python and are not written over
    existing DB values.

    Returns:
        style_stat_id of the inserted/updated row
    """
    from db.queries import insert_team_style_stats

    team_name  = normalize_team_name(_str(row, 'team'))
    _warn_if_unknown_team(team_name, _str(row, 'team'))

    season     = int(row['season'])
    as_of_date = normalize_date(_str(row, 'as_of_date'))
    team_id    = get_or_create_team(conn, team_name)

    stats = {
        'team_id':    team_id,
        'season':     season,
        'as_of_date': as_of_date,
    }

    for col in _TEAM_STYLE_STATS_OPTIONAL_COLS:
        if col in row.index and _is_present(row.get(col)):
            try:
                stats[col] = float(row[col])
            except (ValueError, TypeError):
                logger.warning("Column '%s' value '%s' not numeric — storing NULL", col, row.get(col))
                stats[col] = None
        else:
            stats[col] = None

    # source_note is a plain string — no numeric conversion
    raw_note = row.get('source_note') if 'source_note' in row.index else None
    stats['source_note'] = str(raw_note).strip() if _is_present(raw_note) else None

    return insert_team_style_stats(conn, stats)


# =============================================================================
# Internal helpers
# =============================================================================

def _read_file(filepath: str) -> pd.DataFrame:
    """Read a CSV or Excel file into a DataFrame."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Import file not found: {filepath}")
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.csv':
        return pd.read_csv(filepath, dtype=str)
    elif ext in ('.xlsx', '.xls'):
        return pd.read_excel(filepath, dtype=str)
    else:
        raise ValueError(f"Unsupported file type '{ext}'. Use .csv, .xlsx, or .xls")


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase and strip all column headers."""
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def _assert_required_columns(df: pd.DataFrame, required: set, filepath: str) -> None:
    """Raise ValueError if any required columns are missing."""
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"File '{filepath}' is missing required columns: {sorted(missing)}. "
            f"Found columns: {list(df.columns)}"
        )


def _str(row, col: str) -> str:
    """Extract a string value from a row, stripping whitespace. Returns '' if missing or NaN."""
    val = row.get(col, '')
    if val is None or (isinstance(val, float) and str(val) == 'nan'):
        return ''
    return str(val).strip()


def _is_present(value) -> bool:
    """Return True if a value is non-null and non-empty."""
    if value is None:
        return False
    s = str(value).strip().lower()
    return s not in ('', 'nan', 'none')


def _warn_if_unknown_team(canonical: str, original: str) -> None:
    """Log a warning if the team name was not found in the alias table."""
    if canonical == original.strip():
        logger.warning(
            "Team name '%s' was not found in the alias table. "
            "It will be inserted as-is. Check normalizers._NRL_TEAM_ALIASES.",
            original
        )


def _warn_if_unknown_venue(canonical: str, original: str) -> None:
    """Log a warning if the venue name was not found in the alias table."""
    if canonical == original.strip():
        logger.warning(
            "Venue name '%s' was not found in the alias table. "
            "It will be inserted as-is. Check normalizers._NRL_VENUE_ALIASES.",
            original
        )


def _log_summary(label: str, filepath: str, summary: dict) -> None:
    preserved = summary.get('preserved_fields', 0)
    preserved_str = f" | preserved_fields: {preserved}" if preserved else ""
    logger.info(
        "%s import complete — file: %s | imported: %d | skipped: %d | errors: %d%s",
        label, filepath,
        summary['imported'], summary['skipped'], summary['errors'], preserved_str,
    )
    if summary['error_detail']:
        logger.warning("%s import had %d row errors:", label, summary['errors'])
        for item in summary['error_detail']:
            logger.warning("  Row %d: %s", item['row'], item['error'])


# =============================================================================
# CLI entry point
# =============================================================================

if __name__ == '__main__':
    import argparse
    import yaml
    from db.connection import get_connection, init_schema

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s  %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    parser = argparse.ArgumentParser(description='NRL Historical Spreadsheet Importer')
    parser.add_argument('--results',          help='Path to results spreadsheet (.csv/.xlsx)')
    parser.add_argument('--odds',             help='Path to odds spreadsheet (.csv/.xlsx)')
    parser.add_argument('--team-stats',       help='Path to team stats spreadsheet (.csv/.xlsx)')
    parser.add_argument('--team-style-stats', help='Path to Tier 2 style stats spreadsheet (.csv/.xlsx)')
    parser.add_argument('--settings',         default='config/settings.yaml',
                        help='Path to settings.yaml (default: config/settings.yaml)')
    parser.add_argument('--validate-only', action='store_true',
                        help='Run pre-flight validation only. Do not write to the database.')
    args = parser.parse_args()

    if not args.results and not args.odds and not args.team_stats and not args.team_style_stats:
        parser.error("Provide at least one of --results, --odds, --team-stats, or --team-style-stats")

    if args.validate_only:
        # Validation only — no DB connection needed.
        # Team stats validation: just check required columns are present.
        import pandas as pd
        from normalization.validators import (
            validate_results_dataframe, validate_odds_dataframe, format_validation_report
        )
        if args.results:
            df = pd.read_csv(args.results, dtype=str) if args.results.endswith('.csv') \
                 else pd.read_excel(args.results, dtype=str)
            df.columns = [c.strip().lower() for c in df.columns]
            report = validate_results_dataframe(df)
            print(format_validation_report(report, args.results))
        if args.odds:
            df = pd.read_csv(args.odds, dtype=str) if args.odds.endswith('.csv') \
                 else pd.read_excel(args.odds, dtype=str)
            df.columns = [c.strip().lower() for c in df.columns]
            report = validate_odds_dataframe(df)
            print(format_validation_report(report, args.odds))
        if args.team_stats:
            df = pd.read_csv(args.team_stats, dtype=str) if args.team_stats.endswith('.csv') \
                 else pd.read_excel(args.team_stats, dtype=str)
            df.columns = [c.strip().lower() for c in df.columns]
            missing = _TEAM_STATS_REQUIRED_COLS - set(df.columns)
            if missing:
                print(f"VALIDATION ERROR: Missing required columns: {sorted(missing)}")
            else:
                present = [c for c in _TEAM_STATS_OPTIONAL_COLS if c in df.columns]
                print(f"Team stats file OK — required columns present.")
                print(f"Optional columns found: {present}")
                absent = [c for c in _TEAM_STATS_OPTIONAL_COLS if c not in df.columns]
                if absent:
                    print(f"Optional columns absent (will store NULL): {absent}")
        if args.team_style_stats:
            df = pd.read_csv(args.team_style_stats, dtype=str) if args.team_style_stats.endswith('.csv') \
                 else pd.read_excel(args.team_style_stats, dtype=str)
            df.columns = [c.strip().lower() for c in df.columns]
            missing = _TEAM_STYLE_STATS_REQUIRED_COLS - set(df.columns)
            if missing:
                print(f"VALIDATION ERROR: Missing required columns: {sorted(missing)}")
            else:
                present = [c for c in _TEAM_STYLE_STATS_OPTIONAL_COLS if c in df.columns]
                print(f"Team style stats file OK — required columns present.")
                print(f"Optional columns found: {present}")
                absent = [c for c in _TEAM_STYLE_STATS_OPTIONAL_COLS if c not in df.columns]
                if absent:
                    print(f"Optional columns absent (will store NULL): {absent}")
    else:
        with open(args.settings, 'r') as f:
            settings = yaml.safe_load(f)

        conn = get_connection(settings)
        init_schema(conn)

        if args.results:
            summary = import_historical_results(conn, args.results)
            print(
                f"\nResults import: {summary['imported']} imported, "
                f"{summary['skipped']} skipped, {summary['errors']} errors"
            )
            v = summary['validation']
            print(
                f"Pre-flight:     {v['error_count']} errors, "
                f"{v['warning_count']} warnings, {v['duplicate_count']} duplicates"
            )

        if args.odds:
            summary = import_historical_odds(conn, args.odds)
            print(
                f"\nOdds import: {summary['imported']} imported, "
                f"{summary['skipped']} skipped, {summary['errors']} errors"
            )
            v = summary['validation']
            print(
                f"Pre-flight:  {v['error_count']} errors, "
                f"{v['warning_count']} warnings, {v['duplicate_count']} duplicates"
            )

        if args.team_stats:
            summary = import_historical_team_stats(conn, args.team_stats)
            preserved = summary.get('preserved_fields', 0)
            preserved_str = f", {preserved} field(s) preserved from existing data" if preserved else ""
            print(
                f"\nTeam stats import: {summary['imported']} imported, "
                f"{summary['skipped']} skipped, {summary['errors']} errors{preserved_str}"
            )

        if args.team_style_stats:
            summary = import_historical_team_style_stats(conn, args.team_style_stats)
            print(
                f"\nTeam style stats import: {summary['imported']} imported, "
                f"{summary['skipped']} skipped, {summary['errors']} errors"
            )

        conn.close()
