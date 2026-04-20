# db/queries.py
# Reusable query helpers.
# All writes that could overwrite existing data must go through append-safe methods.
#
# get_or_create_* functions are used by the ingestion layer.
# They look up a record by its natural key and insert it if missing.
# All return the integer primary key of the found or created row.

import sqlite3
from typing import Optional


# =============================================================================
# get_or_create helpers
# =============================================================================

def get_or_create_team(conn: sqlite3.Connection, team_name: str, league: str = 'NRL') -> int:
    """
    Look up a team by name. Insert it if not found.
    Returns team_id.
    """
    row = conn.execute(
        "SELECT team_id FROM teams WHERE team_name = ?", (team_name,)
    ).fetchone()
    if row:
        return row['team_id']

    cursor = conn.execute(
        "INSERT INTO teams (team_name, league) VALUES (?, ?)",
        (team_name, league)
    )
    conn.commit()
    return cursor.lastrowid


def get_or_create_venue(conn: sqlite3.Connection, venue_name: str) -> int:
    """
    Look up a venue by name. Insert it if not found.
    Returns venue_id.
    """
    row = conn.execute(
        "SELECT venue_id FROM venues WHERE venue_name = ?", (venue_name,)
    ).fetchone()
    if row:
        return row['venue_id']

    cursor = conn.execute(
        "INSERT INTO venues (venue_name) VALUES (?)", (venue_name,)
    )
    conn.commit()
    return cursor.lastrowid


def get_or_create_referee(conn: sqlite3.Connection, referee_name: str) -> int:
    """
    Look up a referee by name. Insert if not found.
    Returns referee_id.
    """
    row = conn.execute(
        "SELECT referee_id FROM referees WHERE referee_name = ?", (referee_name,)
    ).fetchone()
    if row:
        return row['referee_id']

    cursor = conn.execute(
        "INSERT INTO referees (referee_name) VALUES (?)", (referee_name,)
    )
    conn.commit()
    return cursor.lastrowid


def get_or_create_bookmaker(
    conn: sqlite3.Connection,
    bookmaker_name: str,
    bookmaker_code: str
) -> int:
    """
    Look up a bookmaker by code. Insert if not found.
    bookmaker_code is the stable internal key (e.g. "pinnacle", "bet365").
    Returns bookmaker_id.
    """
    row = conn.execute(
        "SELECT bookmaker_id FROM bookmakers WHERE bookmaker_code = ?", (bookmaker_code,)
    ).fetchone()
    if row:
        return row['bookmaker_id']

    cursor = conn.execute(
        "INSERT INTO bookmakers (bookmaker_name, bookmaker_code) VALUES (?, ?)",
        (bookmaker_name, bookmaker_code)
    )
    conn.commit()
    return cursor.lastrowid


def get_or_create_match(conn: sqlite3.Connection, match: dict) -> int:
    """
    Look up a match, creating it if not found.

    Lookup order:
      1. source_match_key (if provided) — fastest and most precise.
      2. Composite key: season + round_number + home_team_id + away_team_id.

    match dict keys:
        sport, competition, season, round_number,
        match_date, kickoff_datetime,
        home_team_id, away_team_id, venue_id,
        status (default 'completed'),
        referee_id (optional),
        source_match_key (optional)

    Returns match_id.
    """
    # Try source_match_key first
    if match.get('source_match_key'):
        row = conn.execute(
            "SELECT match_id FROM matches WHERE source_match_key = ?",
            (match['source_match_key'],)
        ).fetchone()
        if row:
            return row['match_id']

    # Fall back to composite key
    row = conn.execute(
        """SELECT match_id FROM matches
           WHERE season = ? AND round_number = ?
             AND home_team_id = ? AND away_team_id = ?""",
        (match['season'], match.get('round_number'),
         match['home_team_id'], match['away_team_id'])
    ).fetchone()
    if row:
        return row['match_id']

    # Insert new match
    cursor = conn.execute(
        """INSERT INTO matches
               (sport, competition, season, round_number,
                match_date, kickoff_datetime,
                home_team_id, away_team_id, venue_id,
                status, referee_id, source_match_key)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            match['sport'], match['competition'],
            match['season'], match.get('round_number'),
            match['match_date'], match['kickoff_datetime'],
            match['home_team_id'], match['away_team_id'],
            match['venue_id'],
            match.get('status', 'completed'),
            match.get('referee_id'),
            match.get('source_match_key'),
        )
    )
    conn.commit()
    return cursor.lastrowid


def find_match(
    conn: sqlite3.Connection,
    season: int,
    round_number: int,
    home_team_id: int,
    away_team_id: int
) -> Optional[int]:
    """
    Find an existing match by season/round/teams.
    Returns match_id, or None if not found.
    Used by the odds importer which expects matches to already exist.
    """
    row = conn.execute(
        """SELECT match_id FROM matches
           WHERE season = ? AND round_number = ?
             AND home_team_id = ? AND away_team_id = ?""",
        (season, round_number, home_team_id, away_team_id)
    ).fetchone()
    return row['match_id'] if row else None


# =============================================================================
# insert helpers
# =============================================================================

def insert_result(conn: sqlite3.Connection, result: dict) -> tuple:
    """
    Insert a match result. Skips silently if a result for this match already exists
    (results.match_id is UNIQUE).

    result dict keys:
        match_id, home_score, away_score, total_score, margin,
        winning_team_id (optional), result_status (default 'final'),
        captured_at (optional)

    Returns:
        (result_id: int, was_inserted: bool)
    """
    existing = conn.execute(
        "SELECT result_id FROM results WHERE match_id = ?", (result['match_id'],)
    ).fetchone()
    if existing:
        return existing['result_id'], False

    cursor = conn.execute(
        """INSERT INTO results
               (match_id, home_score, away_score, total_score, margin,
                winning_team_id, result_status, captured_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            result['match_id'],
            result['home_score'],
            result['away_score'],
            result['total_score'],
            result['margin'],
            result.get('winning_team_id'),
            result.get('result_status', 'final'),
            result.get('captured_at'),
        )
    )
    conn.commit()
    return cursor.lastrowid, True


def insert_market_snapshot(conn: sqlite3.Connection, snapshot: dict) -> int:
    """
    Append a market snapshot. Always inserts — never updates or deduplicates.
    This is intentional: market_snapshots is an append-only price history table.

    snapshot dict keys:
        match_id, bookmaker_id, captured_at, market_type, selection_name,
        odds_decimal, source_method,
        line_value (optional), is_opening (optional), is_closing (optional),
        source_url (optional)

    Returns:
        snapshot_id
    """
    cursor = conn.execute(
        """INSERT INTO market_snapshots
               (match_id, bookmaker_id, captured_at,
                market_type, selection_name,
                line_value, odds_decimal,
                is_opening, is_closing,
                source_url, source_method)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            snapshot['match_id'],
            snapshot['bookmaker_id'],
            snapshot['captured_at'],
            snapshot['market_type'],
            snapshot['selection_name'],
            snapshot.get('line_value'),
            snapshot['odds_decimal'],
            int(snapshot.get('is_opening', 0)),
            int(snapshot.get('is_closing', 0)),
            snapshot.get('source_url'),
            snapshot.get('source_method', 'manual'),
        )
    )
    conn.commit()
    return cursor.lastrowid


# =============================================================================
# Stubs — not yet implemented
# =============================================================================

def insert_team(conn, team: dict) -> int:
    """Insert a team record. Returns team_id."""
    raise NotImplementedError


def insert_venue(conn, venue: dict) -> int:
    raise NotImplementedError


def insert_referee(conn, referee: dict) -> int:
    raise NotImplementedError


def insert_match(conn, match: dict) -> int:
    raise NotImplementedError


def insert_bookmaker(conn, bookmaker: dict) -> int:
    raise NotImplementedError


def insert_team_stats(conn: sqlite3.Connection, stats: dict) -> int:
    """
    Insert or update a team_stats snapshot.

    If a row already exists for (team_id, season, as_of_date), all fields
    are updated with the new values. This is intentional: team stats are
    refreshed during the season and the latest values should always overwrite.

    Required keys in stats:
        team_id, season, as_of_date

    All other keys are optional. Missing keys are stored as NULL.
    Unknown keys are silently ignored.

    Args:
        conn:  active database connection
        stats: dict containing team stats fields (see team_stats schema)

    Returns:
        team_stat_id of the inserted or updated row
    """
    cursor = conn.execute(
        """
        INSERT INTO team_stats (
            team_id, season, as_of_date,
            games_played, wins, losses, win_pct, ladder_position,
            points_for_avg, points_against_avg,
            home_points_for_avg, home_points_against_avg,
            away_points_for_avg, away_points_against_avg,
            elo_rating, attack_rating, defence_rating, recent_form_rating,
            run_metres_pg, post_contact_metres_pg,
            completion_rate, errors_pg, penalties_pg,
            kick_metres_pg, ruck_speed_score
        ) VALUES (
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?
        )
        ON CONFLICT(team_id, season, as_of_date) DO UPDATE SET
            games_played            = excluded.games_played,
            wins                    = excluded.wins,
            losses                  = excluded.losses,
            win_pct                 = excluded.win_pct,
            ladder_position         = excluded.ladder_position,
            points_for_avg          = excluded.points_for_avg,
            points_against_avg      = excluded.points_against_avg,
            home_points_for_avg     = excluded.home_points_for_avg,
            home_points_against_avg = excluded.home_points_against_avg,
            away_points_for_avg     = excluded.away_points_for_avg,
            away_points_against_avg = excluded.away_points_against_avg,
            elo_rating              = excluded.elo_rating,
            attack_rating           = excluded.attack_rating,
            defence_rating          = excluded.defence_rating,
            recent_form_rating      = excluded.recent_form_rating,
            run_metres_pg           = excluded.run_metres_pg,
            post_contact_metres_pg  = excluded.post_contact_metres_pg,
            completion_rate         = excluded.completion_rate,
            errors_pg               = excluded.errors_pg,
            penalties_pg            = excluded.penalties_pg,
            kick_metres_pg          = excluded.kick_metres_pg,
            ruck_speed_score        = excluded.ruck_speed_score
        """,
        (
            stats['team_id'],
            stats['season'],
            stats['as_of_date'],
            stats.get('games_played'),
            stats.get('wins'),
            stats.get('losses'),
            stats.get('win_pct'),
            stats.get('ladder_position'),
            stats.get('points_for_avg'),
            stats.get('points_against_avg'),
            stats.get('home_points_for_avg'),
            stats.get('home_points_against_avg'),
            stats.get('away_points_for_avg'),
            stats.get('away_points_against_avg'),
            stats.get('elo_rating'),
            stats.get('attack_rating'),
            stats.get('defence_rating'),
            stats.get('recent_form_rating'),
            stats.get('run_metres_pg'),
            stats.get('post_contact_metres_pg'),
            stats.get('completion_rate'),
            stats.get('errors_pg'),
            stats.get('penalties_pg'),
            stats.get('kick_metres_pg'),
            stats.get('ruck_speed_score'),
        )
    )
    conn.commit()
    return cursor.lastrowid


def insert_team_style_stats(conn: sqlite3.Connection, stats: dict) -> int:
    """
    Insert or update a team_style_stats row.

    Upserts on (team_id, season, as_of_date). NULL values in the incoming
    dict do NOT overwrite existing non-NULL values in the database
    (null-overwrite protection via COALESCE in the ON CONFLICT clause).

    Required keys: team_id, season, as_of_date
    Optional keys (Family B): lb_pg, tb_pg, mt_pg, lbc_pg
    Optional keys (Family A): completion_rate, kick_metres_pg, errors_pg, penalties_pg
    Optional keys: source_note

    Returns:
        style_stat_id of the inserted or updated row
    """
    cursor = conn.execute(
        """
        INSERT INTO team_style_stats (
            team_id, season, as_of_date,
            lb_pg, tb_pg, mt_pg, lbc_pg,
            completion_rate, kick_metres_pg, errors_pg, penalties_pg,
            run_metres_pg,
            fdo_pg, krm_pg,
            source_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(team_id, season, as_of_date) DO UPDATE SET
            lb_pg           = COALESCE(excluded.lb_pg,           lb_pg),
            tb_pg           = COALESCE(excluded.tb_pg,           tb_pg),
            mt_pg           = COALESCE(excluded.mt_pg,           mt_pg),
            lbc_pg          = COALESCE(excluded.lbc_pg,          lbc_pg),
            completion_rate = COALESCE(excluded.completion_rate, completion_rate),
            kick_metres_pg  = COALESCE(excluded.kick_metres_pg,  kick_metres_pg),
            errors_pg       = COALESCE(excluded.errors_pg,       errors_pg),
            penalties_pg    = COALESCE(excluded.penalties_pg,    penalties_pg),
            run_metres_pg   = COALESCE(excluded.run_metres_pg,   run_metres_pg),
            fdo_pg          = COALESCE(excluded.fdo_pg,          fdo_pg),
            krm_pg          = COALESCE(excluded.krm_pg,          krm_pg),
            source_note     = COALESCE(excluded.source_note,     source_note)
        """,
        (
            stats['team_id'],
            stats['season'],
            stats['as_of_date'],
            stats.get('lb_pg'),
            stats.get('tb_pg'),
            stats.get('mt_pg'),
            stats.get('lbc_pg'),
            stats.get('completion_rate'),
            stats.get('kick_metres_pg'),
            stats.get('errors_pg'),
            stats.get('penalties_pg'),
            stats.get('run_metres_pg'),
            stats.get('fdo_pg'),
            stats.get('krm_pg'),
            stats.get('source_note'),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_team_style_stats(
    conn: sqlite3.Connection,
    team_id: int,
    season: int,
    match_date: str,
) -> dict | None:
    """
    Return the most recent team_style_stats snapshot for a team
    on or before match_date (same point-in-time pattern as get_team_stats).

    Returns None if no snapshot exists.
    """
    row = conn.execute(
        """
        SELECT lb_pg, tb_pg, mt_pg, lbc_pg,
               completion_rate, kick_metres_pg, errors_pg, penalties_pg,
               run_metres_pg,
               fdo_pg, krm_pg,
               source_note, as_of_date
        FROM   team_style_stats
        WHERE  team_id = ? AND season = ? AND as_of_date <= ?
        ORDER  BY as_of_date DESC
        LIMIT  1
        """,
        (team_id, season, match_date),
    ).fetchone()
    return dict(row) if row else None


def get_style_league_norms(
    conn: sqlite3.Connection,
    season: int,
    as_of_date: str,
) -> dict:
    """
    Compute league-wide average and population std dev for all style stats.

    Covers Family B (lb_pg, tb_pg, mt_pg, lbc_pg),
    Family A (completion_rate, kick_metres_pg, errors_pg, penalties_pg), and
    Family C (run_metres_pg).

    Uses the most recent snapshot per team as of as_of_date.

    Returns:
        dict of {stat_name: (avg, std)}.
        If fewer than 2 teams have data for a stat, returns (0.0, 1.0) as
        a safe fallback that keeps normalized values at 0.0.
    """
    import math
    rows = conn.execute(
        """
        SELECT s.lb_pg, s.tb_pg, s.mt_pg, s.lbc_pg,
               s.completion_rate, s.kick_metres_pg, s.errors_pg, s.penalties_pg,
               s.run_metres_pg,
               s.fdo_pg, s.krm_pg
        FROM   team_style_stats s
        INNER  JOIN (
            SELECT team_id, MAX(as_of_date) AS max_date
            FROM   team_style_stats
            WHERE  season = ? AND as_of_date <= ?
            GROUP  BY team_id
        ) latest ON s.team_id = latest.team_id
                AND s.as_of_date = latest.max_date
        WHERE  s.season = ?
        """,
        (season, as_of_date, season),
    ).fetchall()

    norms = {}
    for col in ('lb_pg', 'tb_pg', 'mt_pg', 'lbc_pg',
                'completion_rate', 'kick_metres_pg', 'errors_pg', 'penalties_pg',
                'run_metres_pg',
                'fdo_pg', 'krm_pg'):
        vals = [row[col] for row in rows if row[col] is not None]
        if len(vals) >= 2:
            avg = sum(vals) / len(vals)
            std = math.sqrt(sum((v - avg) ** 2 for v in vals) / len(vals))
            norms[col] = (avg, max(std, 1e-6))   # guard against zero std
        else:
            norms[col] = (0.0, 1.0)
    return norms


def insert_match_context(conn, context: dict) -> int:
    raise NotImplementedError


def insert_injury_report(conn, report: dict) -> int:
    raise NotImplementedError


def insert_model_run(conn: sqlite3.Connection, model_run: dict) -> int:
    """
    Insert a model run record. Returns model_run_id.

    Required keys:
        match_id, run_timestamp, model_version,
        baseline_home_points, baseline_away_points, baseline_margin, baseline_total,
        final_home_points, final_away_points, final_margin, final_total,
        home_win_probability, away_win_probability,
        fair_home_odds, fair_away_odds,
        fair_handicap_line, fair_total_line,
        run_status  ('success' | 'failed' | 'partial')

    Optional keys:
        notes
    """
    cursor = conn.execute(
        """
        INSERT INTO model_runs (
            match_id, run_timestamp, model_version,
            baseline_home_points, baseline_away_points, baseline_margin, baseline_total,
            final_home_points, final_away_points, final_margin, final_total,
            home_win_probability, away_win_probability,
            fair_home_odds, fair_away_odds,
            fair_handicap_line, fair_total_line,
            run_status, notes
        ) VALUES (
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?
        )
        """,
        (
            model_run['match_id'],
            model_run['run_timestamp'],
            model_run['model_version'],
            model_run['baseline_home_points'],
            model_run['baseline_away_points'],
            model_run['baseline_margin'],
            model_run['baseline_total'],
            model_run['final_home_points'],
            model_run['final_away_points'],
            model_run['final_margin'],
            model_run['final_total'],
            model_run['home_win_probability'],
            model_run['away_win_probability'],
            model_run['fair_home_odds'],
            model_run['fair_away_odds'],
            model_run['fair_handicap_line'],
            model_run['fair_total_line'],
            model_run['run_status'],
            model_run.get('notes'),
        )
    )
    conn.commit()
    return cursor.lastrowid


def insert_model_adjustment(conn: sqlite3.Connection, adjustment: dict) -> int:
    """
    Insert one tier adjustment row for a model run. Returns adjustment_id.

    Required keys:
        model_run_id, tier_number (1–7), tier_name,
        adjustment_code, adjustment_description

    Optional keys (default to 0 / 1):
        home_points_delta, away_points_delta, margin_delta, total_delta,
        applied_flag
    """
    cursor = conn.execute(
        """
        INSERT INTO model_adjustments (
            model_run_id, tier_number, tier_name,
            adjustment_code, adjustment_description,
            home_points_delta, away_points_delta,
            margin_delta, total_delta,
            applied_flag
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            adjustment['model_run_id'],
            adjustment['tier_number'],
            adjustment['tier_name'],
            adjustment['adjustment_code'],
            adjustment['adjustment_description'],
            float(adjustment.get('home_points_delta', 0.0)),
            float(adjustment.get('away_points_delta', 0.0)),
            float(adjustment.get('margin_delta',      0.0)),
            float(adjustment.get('total_delta',       0.0)),
            int(adjustment.get('applied_flag', 1)),
        )
    )
    conn.commit()
    return cursor.lastrowid


def insert_signal(conn: sqlite3.Connection, signal: dict) -> int:
    """
    Insert one signal row. Returns signal_id.

    The caller (audit/model_logger.log_signal) is responsible for resolving
    bookmaker_id from bookmaker_code before calling this function.

    Required keys (DB column names):
        model_run_id, match_id, snapshot_id, bookmaker_id,
        market_type, selection_name,
        market_odds, model_probability,
        ev_value, ev_percent,
        raw_kelly_fraction, applied_kelly_fraction,
        capped_stake_fraction, recommended_stake_amount,
        confidence_level, signal_label

    Optional keys:
        line_value, model_odds,
        veto_flag (default 0), veto_reason
    """
    cursor = conn.execute(
        """
        INSERT INTO signals (
            model_run_id, match_id, snapshot_id, bookmaker_id,
            market_type, selection_name, line_value,
            market_odds, model_odds, model_probability,
            ev_value, ev_percent,
            raw_kelly_fraction, applied_kelly_fraction,
            capped_stake_fraction, recommended_stake_amount,
            confidence_level, signal_label,
            veto_flag, veto_reason
        ) VALUES (
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?
        )
        """,
        (
            signal['model_run_id'],
            signal['match_id'],
            signal['snapshot_id'],
            signal['bookmaker_id'],
            signal['market_type'],
            signal['selection_name'],
            signal.get('line_value'),
            signal['market_odds'],
            signal.get('model_odds'),
            signal['model_probability'],
            signal['ev_value'],
            signal['ev_percent'],
            signal['raw_kelly_fraction'],
            signal['applied_kelly_fraction'],
            signal['capped_stake_fraction'],
            signal['recommended_stake_amount'],
            signal['confidence_level'],
            signal['signal_label'],
            int(signal.get('veto_flag', 0)),
            signal.get('veto_reason'),
        )
    )
    conn.commit()
    return cursor.lastrowid


def insert_bet(conn, bet: dict) -> int:
    raise NotImplementedError


def insert_bankroll_log(conn: sqlite3.Connection, entry: dict) -> int:
    """
    Append a bankroll state entry. Returns bankroll_log_id.

    bankroll_log is append-only — rows are never updated.

    Required keys:
        log_timestamp, starting_bankroll, ending_bankroll

    Optional keys (default to 0):
        open_exposure, closed_pnl, notes
    """
    cursor = conn.execute(
        """
        INSERT INTO bankroll_log (
            log_timestamp, starting_bankroll, ending_bankroll,
            open_exposure, closed_pnl, notes
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            entry['log_timestamp'],
            entry['starting_bankroll'],
            entry['ending_bankroll'],
            float(entry.get('open_exposure', 0.0)),
            float(entry.get('closed_pnl',    0.0)),
            entry.get('notes'),
        )
    )
    conn.commit()
    return cursor.lastrowid


def get_match_by_id(
    conn: sqlite3.Connection,
    match_id: int,
) -> Optional[dict]:
    """
    Fetch a match row by match_id, with team names, venue, and referee resolved.

    Joins home_team, away_team, venue, and referee (LEFT JOIN — referee may be NULL).
    Returns a flat dict so the pricing engine can access all fields without
    further lookups.

    Returned keys include all match columns plus:
        home_team_name       str
        home_team_short_name str | None
        away_team_name       str
        away_team_short_name str | None
        venue_name           str
        venue_city           str | None
        referee_name         str | None   (None if not yet assigned)

    Args:
        conn:     active database connection
        match_id: canonical match identifier

    Returns:
        dict of match fields, or None if no match with that id exists.
    """
    row = conn.execute(
        """
        SELECT
            m.*,
            ht.team_name       AS home_team_name,
            ht.team_short_name AS home_team_short_name,
            at.team_name       AS away_team_name,
            at.team_short_name AS away_team_short_name,
            v.venue_name,
            v.city             AS venue_city,
            r.referee_name
        FROM matches m
        JOIN  teams   ht ON ht.team_id   = m.home_team_id
        JOIN  teams   at ON at.team_id   = m.away_team_id
        JOIN  venues  v  ON v.venue_id   = m.venue_id
        LEFT JOIN referees r ON r.referee_id = m.referee_id
        WHERE m.match_id = ?
        """,
        (match_id,),
    ).fetchone()

    return dict(row) if row else None


def get_latest_snapshots_for_match(
    conn: sqlite3.Connection,
    match_id: int,
) -> list:
    """
    Return the most recent market snapshot per (bookmaker, market_type, selection)
    combination for a given match.

    market_snapshots is an append-only table — multiple snapshots may exist for
    the same bookmaker/market/selection captured at different times. This function
    returns only the latest one for each combination, which is what the decision
    engine should price against.

    Returned list is ordered by bookmaker_id, market_type, selection_name for
    consistent, deterministic output.

    Each dict in the returned list contains all market_snapshots columns plus:
        bookmaker_name  str   (joined from bookmakers table)
        bookmaker_code  str   (stable internal code, e.g. "pinnacle")

    Args:
        conn:     active database connection
        match_id: canonical match identifier

    Returns:
        list of snapshot dicts (may be empty if no snapshots exist yet).
        Each dict represents the most recent price for one bookmaker/market/selection.
    """
    rows = conn.execute(
        """
        SELECT s.*, b.bookmaker_name, b.bookmaker_code
        FROM market_snapshots s
        JOIN bookmakers b ON b.bookmaker_id = s.bookmaker_id
        JOIN (
            SELECT   bookmaker_id,
                     market_type,
                     selection_name,
                     MAX(captured_at) AS latest_captured_at
            FROM     market_snapshots
            WHERE    match_id = ?
            GROUP BY bookmaker_id, market_type, selection_name
        ) latest
          ON  s.bookmaker_id   = latest.bookmaker_id
          AND s.market_type    = latest.market_type
          AND s.selection_name = latest.selection_name
          AND s.captured_at    = latest.latest_captured_at
        WHERE s.match_id = ?
        ORDER BY s.bookmaker_id, s.market_type, s.selection_name
        """,
        (match_id, match_id),
    ).fetchall()

    return [dict(row) for row in rows]


def get_team_stats(
    conn: sqlite3.Connection,
    team_id: int,
    season: int,
    as_of_date: Optional[str] = None,
) -> Optional[dict]:
    """
    Fetch the most recent team_stats snapshot for a team in a given season,
    on or before as_of_date.

    WHY AS_OF_DATE
    --------------
    team_stats rows are point-in-time snapshots. Multiple rows may exist for
    the same team and season (one per stats update, e.g. after each round).
    This function always returns the snapshot that was most recently valid
    at the requested date — so pricing a round-10 match uses round-9 stats,
    not round-15 stats that hadn't happened yet.

    If as_of_date is None, returns the most recent snapshot for the season
    regardless of date. This is useful for interactive use and testing.

    RETURN SHAPE
    ------------
    Returns a plain dict (not a sqlite3.Row) so callers can use .get() safely.
    All nullable columns are present in the dict with value None if not set.
    This matches the interface expected by tier1_baseline.compute_baseline()
    and tier2_matchup.compute_yardage_bucket().

    The returned dict contains all team_stats columns:
        Core identity:     team_stat_id, team_id, season, as_of_date
        Season record:     games_played, wins, losses, win_pct, ladder_position
        Scoring averages:  points_for_avg, points_against_avg,
                           home_points_for_avg, home_points_against_avg,
                           away_points_for_avg, away_points_against_avg
        T1 ratings:        elo_rating, attack_rating, defence_rating,
                           recent_form_rating
        T2 yardage:        run_metres_pg, post_contact_metres_pg,
                           completion_rate, errors_pg, penalties_pg,
                           kick_metres_pg, ruck_speed_score

    Args:
        conn:        active database connection
        team_id:     canonical team identifier
        season:      season year (e.g. 2024)
        as_of_date:  ISO date string (e.g. "2024-05-01"), or None for latest

    Returns:
        dict of team stats, or None if no stats exist for this team/season.
    """
    if as_of_date is not None:
        row = conn.execute(
            """
            SELECT *
            FROM   team_stats
            WHERE  team_id = ?
              AND  season  = ?
              AND  as_of_date <= ?
            ORDER  BY as_of_date DESC
            LIMIT  1
            """,
            (team_id, season, as_of_date),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT *
            FROM   team_stats
            WHERE  team_id = ?
              AND  season  = ?
            ORDER  BY as_of_date DESC
            LIMIT  1
            """,
            (team_id, season),
        ).fetchone()

    return dict(row) if row else None


def get_prior_season_stats(
    conn: sqlite3.Connection,
    team_id: int,
    current_season: int,
) -> Optional[dict]:
    """
    Fetch the most recent end-of-season stats for a team from the most recent
    prior season (i.e. the highest season < current_season).

    Used to provide prior-season attack/defence priors in Tier 1 when the
    current season's sample size is small.

    Args:
        conn:           active database connection
        team_id:        canonical team identifier
        current_season: the season being priced (e.g. 2026)

    Returns:
        dict of team stats from the most recent prior season, or None if no
        prior season data exists for this team.
    """
    row = conn.execute(
        """
        SELECT *
        FROM   team_stats
        WHERE  team_id = ?
          AND  season  < ?
        ORDER  BY season DESC, as_of_date DESC
        LIMIT  1
        """,
        (team_id, current_season),
    ).fetchone()

    return dict(row) if row else None


def get_match_context(
    conn: sqlite3.Connection,
    match_id: int,
) -> Optional[dict]:
    """
    Fetch the match_context row for a given match.

    match_context holds all contextual variables consumed by Tiers 3–7:
        Tier 3 (situational):  home_rest_days, away_rest_days,
                               home_off_bye, away_off_bye
        Tier 4 (venue):        home_travel_km, away_travel_km,
                               venue_fortress_flag_home
        Tier 5 (injury):       home_key_injuries_count, away_key_injuries_count,
                               home_spine_injuries_count, away_spine_injuries_count
        Tier 7A (weather):     weather_rain_flag, weather_wind_kph,
                               weather_temp_c, weather_humidity_pct,
                               weather_summary
        Tier 7B (lunar):       full_moon_flag, new_moon_flag,
                               moon_window_plus_minus_one_day

    There is at most one match_context row per match (UNIQUE on match_id).
    If no context has been ingested yet, returns None. Tier modules must
    handle None context gracefully (treat all contextual signals as neutral).

    Args:
        conn:     active database connection
        match_id: canonical match identifier

    Returns:
        dict of context fields, or None if no context row exists for this match.
    """
    row = conn.execute(
        "SELECT * FROM match_context WHERE match_id = ?",
        (match_id,),
    ).fetchone()

    return dict(row) if row else None


# =============================================================================
# Tier 3 situational context derivation
# =============================================================================

def get_situational_context(
    conn: sqlite3.Connection,
    match_id: int,
    home_team_id: int,
    away_team_id: int,
    venue_id: int,
    match_date: str,
    season: int,
) -> dict:
    """
    Derive Tier 3 situational context for a match on the fly from the DB.

    Computes:
        home_rest_days   int | None   days since home team's last game this season
        away_rest_days   int | None   days since away team's last game this season
        home_travel_km   float | None haversine(home_base, venue)
        away_travel_km   float | None haversine(away_base, venue)

    None is returned when data is unavailable (first game of the season,
    or geo coords not populated). Tier 3 treats None as neutral (0.0 delta).

    Args:
        conn:         active database connection
        match_id:     current match (excluded when searching for prior games)
        home_team_id: home team
        away_team_id: away team
        venue_id:     venue for travel calculation
        match_date:   ISO date string (e.g. "2026-04-10")
        season:       season year (only searches within the same season)

    Returns:
        flat dict with home_rest_days, away_rest_days, home_travel_km,
        away_travel_km.
    """
    import math as _math

    # --- Rest days ---
    def _last_game_date(team_id: int) -> Optional[str]:
        row = conn.execute(
            """
            SELECT MAX(match_date) AS last_date
            FROM   matches
            WHERE  season = ?
              AND  match_id != ?
              AND  match_date < ?
              AND  (home_team_id = ? OR away_team_id = ?)
            """,
            (season, match_id, match_date, team_id, team_id),
        ).fetchone()
        return row['last_date'] if row else None

    def _days_between(earlier: Optional[str], later: str) -> Optional[int]:
        if earlier is None:
            return None
        from datetime import date
        d1 = date.fromisoformat(earlier)
        d2 = date.fromisoformat(later)
        return (d2 - d1).days

    home_last = _last_game_date(home_team_id)
    away_last = _last_game_date(away_team_id)
    home_rest_days = _days_between(home_last, match_date)
    away_rest_days = _days_between(away_last, match_date)

    # --- Travel distances ---
    def _haversine(lat1, lng1, lat2, lng2) -> float:
        R = 6371.0
        dlat = _math.radians(lat2 - lat1)
        dlng = _math.radians(lng2 - lng1)
        a = (_math.sin(dlat / 2) ** 2
             + _math.cos(_math.radians(lat1)) * _math.cos(_math.radians(lat2))
             * _math.sin(dlng / 2) ** 2)
        return R * 2 * _math.asin(_math.sqrt(a))

    venue_row = conn.execute(
        "SELECT lat, lng FROM venues WHERE venue_id = ?", (venue_id,)
    ).fetchone()
    venue_lat = venue_row['lat'] if venue_row else None
    venue_lng = venue_row['lng'] if venue_row else None

    def _team_travel_km(team_id: int) -> Optional[float]:
        if venue_lat is None or venue_lng is None:
            return None
        hb = conn.execute(
            "SELECT lat, lng FROM team_home_bases WHERE team_id = ?", (team_id,)
        ).fetchone()
        if hb is None or hb['lat'] is None or hb['lng'] is None:
            return None
        return _haversine(hb['lat'], hb['lng'], venue_lat, venue_lng)

    home_travel_km = _team_travel_km(home_team_id)
    away_travel_km = _team_travel_km(away_team_id)

    return {
        'home_rest_days':  home_rest_days,
        'away_rest_days':  away_rest_days,
        'home_travel_km':  round(home_travel_km, 1) if home_travel_km is not None else None,
        'away_travel_km':  round(away_travel_km, 1) if away_travel_km is not None else None,
    }


# =============================================================================
# Tier 2 performance tracking
# =============================================================================

def insert_tier2_performance(conn: sqlite3.Connection, record: dict) -> int:
    """
    Insert or update a tier2_performance row for a single match.

    Called at pricing time (before the result is known).
    Result/error fields are left NULL and filled later by update_tier2_results().

    Expected keys in record:
        match_id, model_version, season, round_number, match_date,
        home_team_id, away_team_id,
        t1_home_pts, t1_away_pts, t1_margin,
        t2a_home_delta, t2b_home_delta, t2c_home_delta,
        t2_raw_total, t2_capped_total, t2_scale_applied (or None),
        t2a_label_h, t2a_label_a, t2b_label_h, t2b_label_a,
        t2c_label_h, t2c_label_a,
        fired_families,
        final_margin, final_home_pts, final_away_pts

    Returns perf_id.
    """
    from datetime import datetime, timezone
    recorded_at = datetime.now(timezone.utc).isoformat()

    conn.execute("""
        INSERT INTO tier2_performance (
            match_id, model_version, recorded_at,
            season, round_number, match_date, home_team_id, away_team_id,
            t1_home_pts, t1_away_pts, t1_margin,
            t2a_home_delta, t2b_home_delta, t2c_home_delta,
            t2_raw_total, t2_capped_total, t2_scale_applied,
            t2a_label_h, t2a_label_a,
            t2b_label_h, t2b_label_a,
            t2c_label_h, t2c_label_a,
            fired_families,
            final_margin, final_home_pts, final_away_pts,
            totals_T1, totals_T2, totals_T3, totals_T4, totals_T5, totals_T6, totals_T7,
            final_total, pred_home_score, pred_away_score,
            t3_home_delta, t3_away_delta,
            t4_handicap_delta, t4_venue_name,
            t5_handicap_delta, t5_home_injury_pts, t5_away_injury_pts,
            t6_handicap_delta, t6_bucket, t6_referee_name,
            fair_home_odds, fair_away_odds, home_win_probability,
            fair_handicap_line, fair_total_line,
            t3_3a_delta, t3_3b_delta, t3_3c_home_delta, t3_3c_away_delta,
            t3_home_rest_days, t3_away_rest_days,
            t3_home_travel_km, t3_away_travel_km,
            t7_condition_type, t7_dew_risk
        ) VALUES (
            :match_id, :model_version, :recorded_at,
            :season, :round_number, :match_date, :home_team_id, :away_team_id,
            :t1_home_pts, :t1_away_pts, :t1_margin,
            :t2a_home_delta, :t2b_home_delta, :t2c_home_delta,
            :t2_raw_total, :t2_capped_total, :t2_scale_applied,
            :t2a_label_h, :t2a_label_a,
            :t2b_label_h, :t2b_label_a,
            :t2c_label_h, :t2c_label_a,
            :fired_families,
            :final_margin, :final_home_pts, :final_away_pts,
            :totals_T1, :totals_T2, :totals_T3, :totals_T4, :totals_T5, :totals_T6, :totals_T7,
            :final_total, :pred_home_score, :pred_away_score,
            :_t3_home_delta, :_t3_away_delta,
            :t4_handicap_delta, :t4_venue_name,
            :t5_handicap_delta, :t5_home_injury_pts, :t5_away_injury_pts,
            :t6_handicap_delta, :t6_bucket, :t6_referee_name,
            :fair_home_odds, :fair_away_odds, :home_win_probability,
            :fair_handicap_line, :fair_total_line,
            :_t3_3a, :_t3_3b, :_t3_3c_home, :_t3_3c_away,
            :_t3_home_rest, :_t3_away_rest,
            :_t3_home_km, :_t3_away_km,
            :t7_condition_type, :t7_dew_risk
        )
        ON CONFLICT(match_id, model_version) DO UPDATE SET
            recorded_at           = excluded.recorded_at,
            t1_home_pts           = excluded.t1_home_pts,
            t1_away_pts           = excluded.t1_away_pts,
            t1_margin             = excluded.t1_margin,
            t2a_home_delta        = excluded.t2a_home_delta,
            t2b_home_delta        = excluded.t2b_home_delta,
            t2c_home_delta        = excluded.t2c_home_delta,
            t2_raw_total          = excluded.t2_raw_total,
            t2_capped_total       = excluded.t2_capped_total,
            t2_scale_applied      = excluded.t2_scale_applied,
            t2a_label_h           = excluded.t2a_label_h,
            t2a_label_a           = excluded.t2a_label_a,
            t2b_label_h           = excluded.t2b_label_h,
            t2b_label_a           = excluded.t2b_label_a,
            t2c_label_h           = excluded.t2c_label_h,
            t2c_label_a           = excluded.t2c_label_a,
            fired_families        = excluded.fired_families,
            final_margin          = excluded.final_margin,
            final_home_pts        = excluded.final_home_pts,
            final_away_pts        = excluded.final_away_pts,
            totals_T1             = excluded.totals_T1,
            totals_T2             = excluded.totals_T2,
            totals_T3             = excluded.totals_T3,
            totals_T4             = excluded.totals_T4,
            totals_T5             = excluded.totals_T5,
            totals_T6             = excluded.totals_T6,
            totals_T7             = excluded.totals_T7,
            final_total           = excluded.final_total,
            pred_home_score       = excluded.pred_home_score,
            pred_away_score       = excluded.pred_away_score,
            t3_home_delta         = excluded.t3_home_delta,
            t3_away_delta         = excluded.t3_away_delta,
            t4_handicap_delta     = excluded.t4_handicap_delta,
            t4_venue_name         = excluded.t4_venue_name,
            t5_handicap_delta     = excluded.t5_handicap_delta,
            t5_home_injury_pts    = excluded.t5_home_injury_pts,
            t5_away_injury_pts    = excluded.t5_away_injury_pts,
            t6_handicap_delta     = excluded.t6_handicap_delta,
            t6_bucket             = excluded.t6_bucket,
            t6_referee_name       = excluded.t6_referee_name,
            fair_home_odds        = excluded.fair_home_odds,
            fair_away_odds        = excluded.fair_away_odds,
            home_win_probability  = excluded.home_win_probability,
            fair_handicap_line    = excluded.fair_handicap_line,
            fair_total_line       = excluded.fair_total_line,
            t3_3a_delta           = excluded.t3_3a_delta,
            t3_3b_delta           = excluded.t3_3b_delta,
            t3_3c_home_delta      = excluded.t3_3c_home_delta,
            t3_3c_away_delta      = excluded.t3_3c_away_delta,
            t3_home_rest_days     = excluded.t3_home_rest_days,
            t3_away_rest_days     = excluded.t3_away_rest_days,
            t3_home_travel_km     = excluded.t3_home_travel_km,
            t3_away_travel_km     = excluded.t3_away_travel_km,
            t7_condition_type     = excluded.t7_condition_type,
            t7_dew_risk           = excluded.t7_dew_risk
    """, {**record, 'recorded_at': recorded_at})
    conn.commit()

    row = conn.execute(
        "SELECT perf_id FROM tier2_performance WHERE match_id=? AND model_version=?",
        (record['match_id'], record['model_version']),
    ).fetchone()
    return row['perf_id']


def update_tier2_results(conn: sqlite3.Connection, season: int, model_version: str) -> int:
    """
    Fill in actual result and compute error metrics for all tier2_performance
    rows in a given season that have a result in the results table but have
    not yet had their error metrics computed (actual_margin IS NULL).

    Safe to re-run: only updates rows where actual_margin IS NULL.

    Returns count of rows updated.
    """
    pending = conn.execute("""
        SELECT tp.perf_id, tp.t1_margin, tp.final_margin,
               r.home_score, r.away_score, r.margin as actual_margin
        FROM tier2_performance tp
        JOIN results r ON tp.match_id = r.match_id
        WHERE tp.season = ?
          AND tp.model_version = ?
          AND tp.actual_margin IS NULL
    """, (season, model_version)).fetchall()

    updated = 0
    for row in pending:
        actual_margin  = float(row['actual_margin'])
        t1_margin      = float(row['t1_margin'])
        final_margin   = float(row['final_margin'])
        home_score     = int(row['home_score'])
        away_score     = int(row['away_score'])

        actual_winner = 'home' if actual_margin > 0 else ('away' if actual_margin < 0 else 'draw')

        t1_abs_error  = abs(t1_margin - actual_margin)
        t12_abs_error = abs(final_margin - actual_margin)
        abs_improvement = round(t1_abs_error - t12_abs_error, 4)

        # Did Tier 2 move the prediction toward the actual result?
        t2_delta = final_margin - t1_margin
        if t2_delta == 0.0:
            direction_correct = None  # neutral
        else:
            direction_correct = 1 if abs_improvement > 0 else 0

        t1_winner_correct    = 1 if (t1_margin > 0) == (actual_margin > 0) else 0
        final_winner_correct = 1 if (final_margin > 0) == (actual_margin > 0) else 0

        conn.execute("""
            UPDATE tier2_performance SET
                actual_margin        = ?,
                actual_home_score    = ?,
                actual_away_score    = ?,
                actual_winner        = ?,
                t1_abs_error         = ?,
                t12_abs_error        = ?,
                abs_improvement      = ?,
                t2_direction_correct = ?,
                t1_winner_correct    = ?,
                final_winner_correct = ?
            WHERE perf_id = ?
        """, (
            actual_margin, home_score, away_score, actual_winner,
            round(t1_abs_error, 4), round(t12_abs_error, 4), abs_improvement,
            direction_correct, t1_winner_correct, final_winner_correct,
            row['perf_id'],
        ))
        updated += 1

    conn.commit()
    return updated


# =============================================================================
# Tier 6 referee query helpers
# =============================================================================

def get_ref_assignment(conn: sqlite3.Connection, match_id: int) -> Optional[dict]:
    """
    Return the weekly referee assignment for a match.

    Joins weekly_ref_assignments to referees to resolve referee_name.

    Args:
        conn:     active database connection
        match_id: canonical match identifier

    Returns:
        dict with {'referee_id': int, 'referee_name': str}
        or None if no assignment exists for this match.
    """
    row = conn.execute(
        """
        SELECT wra.referee_id, r.referee_name
        FROM   weekly_ref_assignments wra
        JOIN   referees r ON r.referee_id = wra.referee_id
        WHERE  wra.match_id = ?
        """,
        (match_id,),
    ).fetchone()
    return dict(row) if row else None


def get_referee_profile(conn: sqlite3.Connection, referee_id: int) -> Optional[dict]:
    """
    Return the referee profile for a given referee_id.

    Args:
        conn:        active database connection
        referee_id:  canonical referee identifier

    Returns:
        dict with {'referee_id': int, 'referee_name': str, 'bucket': str}
        or None if no profile exists.
    """
    row = conn.execute(
        """
        SELECT rp.referee_id, r.referee_name, rp.bucket, rp.games_in_sample, rp.notes
        FROM   referee_profiles rp
        JOIN   referees r ON r.referee_id = rp.referee_id
        WHERE  rp.referee_id = ?
        """,
        (referee_id,),
    ).fetchone()
    return dict(row) if row else None


def get_team_ref_bucket_edge(
    conn: sqlite3.Connection,
    team_id: int,
    bucket: str,
    season: int,
) -> float:
    """
    Return the team's bucket_edge for a (team, bucket, season) combination.

    bucket_edge is the average signed margin from the team's perspective
    in games officiated by referees in the named bucket.

    Returns 0.0 if:
        - no row exists for this (team, bucket, season)
        - the stored games count is below the minimum threshold (stored as 0.0)

    Args:
        conn:    active database connection
        team_id: canonical team identifier
        bucket:  referee bucket name ('whistle_heavy' | 'flow_heavy' | 'neutral')
        season:  season year (e.g. 2025)

    Returns:
        float bucket_edge (may be 0.0 if insufficient data)
    """
    row = conn.execute(
        """
        SELECT bucket_edge
        FROM   team_ref_bucket_stats
        WHERE  team_id = ? AND bucket = ? AND season = ?
        """,
        (team_id, bucket, season),
    ).fetchone()
    return float(row['bucket_edge']) if row else 0.0


# =============================================================================
# Tier 4 venue query helpers
# =============================================================================

def get_team_venue_edge(conn: sqlite3.Connection, team_id: int, venue_id: int) -> float:
    """Returns venue_edge for a team at a venue, or 0.0 if not found."""
    row = conn.execute(
        "SELECT venue_edge FROM team_venue_stats WHERE team_id = ? AND venue_id = ?",
        (team_id, venue_id)
    ).fetchone()
    return float(row['venue_edge']) if row else 0.0


def get_venue_total_edge(conn: sqlite3.Connection, venue_id: int) -> float:
    """Returns total_edge for a venue, or 0.0 if not found."""
    row = conn.execute(
        "SELECT total_edge FROM venue_profiles WHERE venue_id = ?",
        (venue_id,)
    ).fetchone()
    return float(row['total_edge']) if row else 0.0


def get_venue_name(conn: sqlite3.Connection, venue_id: int) -> str:
    """Returns venue name for display."""
    row = conn.execute(
        "SELECT venue_name FROM venues WHERE venue_id = ?",
        (venue_id,)
    ).fetchone()
    return row['venue_name'] if row else f'venue_{venue_id}'


# =============================================================================
# Tier 5 injury query helpers
# =============================================================================

# Points awarded per importance_tier for status='out'.
# Doubtful players count at half weight.
_INJURY_PTS_BY_TIER = {
    'elite':    3.0,
    'key':      1.5,
    'rotation': 0.5,
}


def get_team_injury_pts(conn: sqlite3.Connection, match_id: int, team_id: int) -> float:
    """
    Return total injury burden for a team in a given match.

    Resolution order:
      1. team_injury_totals — pre-aggregated totals (e.g. loaded from spreadsheet)
      2. injury_reports    — individual player records summed on the fly

    Points per player (used only when falling back to injury_reports):
        elite:    3.0  (out) / 1.5  (doubtful)
        key:      1.5  (out) / 0.75 (doubtful)
        rotation: 0.5  (out) / 0.25 (doubtful)

    Returns 0.0 if no records found in either table.
    """
    # --- priority 1: pre-aggregated total ---
    agg = conn.execute(
        "SELECT total_injury_pts FROM team_injury_totals WHERE match_id = ? AND team_id = ?",
        (match_id, team_id),
    ).fetchone()
    if agg is not None:
        return round(agg['total_injury_pts'], 3)

    # --- priority 2: individual records ---
    rows = conn.execute(
        """
        SELECT importance_tier, status
        FROM   injury_reports
        WHERE  match_id = ? AND team_id = ?
          AND  status IN ('out', 'doubtful')
        """,
        (match_id, team_id),
    ).fetchall()

    total = 0.0
    for row in rows:
        base = _INJURY_PTS_BY_TIER.get(row['importance_tier'] or '', 0.0)
        weight = 1.0 if row['status'] == 'out' else 0.5
        total += base * weight
    return round(total, 3)


# =============================================================================
# Tier 7 — Weather
# =============================================================================

def get_weather_conditions(conn: sqlite3.Connection, match_id: int) -> Optional[dict]:
    """
    Return the weather_conditions row for match_id, or None if not fetched.
    """
    row = conn.execute(
        "SELECT * FROM weather_conditions WHERE match_id = ?",
        (match_id,),
    ).fetchone()
    return dict(row) if row else None
