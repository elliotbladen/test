#!/usr/bin/env python3
"""
scripts/ingest_actuals.py
=========================
Enter actual match results after each round.
Inserts rows into the `results` table and updates actuals + error columns
in `ml_shadow_predictions` and `tier2_performance`.

USAGE
-----
Single game:
    python scripts/ingest_actuals.py \
        --season 2026 --round 10 \
        --home "Dolphins" --away "Melbourne Storm" \
        --home-score 29 --away-score 24

Batch from CSV (columns: home_team, away_team, home_score, away_score):
    python scripts/ingest_actuals.py \
        --season 2026 --round 10 \
        --from-csv data/import/results_r10_2026.csv

Show what is still missing for a round:
    python scripts/ingest_actuals.py --status --season 2026 --round 10
"""

import argparse
import csv
import os
import sqlite3
import sys
import yaml

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.yaml')


# =============================================================================
# DB helpers
# =============================================================================

def _get_conn(settings_path):
    with open(settings_path) as fh:
        settings = yaml.safe_load(fh)
    db_path = settings.get('database', {}).get('path', 'data/betting_model.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _find_match(conn, season, round_number, home_team, away_team):
    """Look up match_id by season/round and fuzzy team name."""
    row = conn.execute("""
        SELECT m.match_id, ht.team_name AS home, at.team_name AS away
        FROM matches m
        JOIN teams ht ON ht.team_id = m.home_team_id
        JOIN teams at ON at.team_id = m.away_team_id
        WHERE m.season = ? AND m.round_number = ?
          AND (
              ht.team_name LIKE ? OR ht.team_name LIKE ?
          )
          AND (
              at.team_name LIKE ? OR at.team_name LIKE ?
          )
    """, (season, round_number,
          f'%{home_team}%', f'{home_team}%',
          f'%{away_team}%', f'{away_team}%')).fetchone()
    return row


def _insert_result(conn, match_id, home_score, away_score):
    """Insert into results table. Returns (result_id, was_inserted)."""
    margin = home_score - away_score
    total  = home_score + away_score
    try:
        cur = conn.execute("""
            INSERT INTO results
                (match_id, home_score, away_score, total_score, margin, result_status)
            VALUES (?, ?, ?, ?, ?, 'final')
        """, (match_id, home_score, away_score, total, margin))
        conn.commit()
        return cur.lastrowid, True
    except sqlite3.IntegrityError:
        # Already exists — update it
        conn.execute("""
            UPDATE results
            SET home_score = ?, away_score = ?, total_score = ?, margin = ?
            WHERE match_id = ?
        """, (home_score, away_score, total, margin, match_id))
        conn.commit()
        row = conn.execute('SELECT result_id FROM results WHERE match_id = ?', (match_id,)).fetchone()
        return row['result_id'], False


def _update_ml_shadow(conn, match_id, home_score, away_score):
    """Fill actuals and compute error columns in ml_shadow_predictions."""
    actual_margin   = home_score - away_score
    actual_total    = home_score + away_score
    actual_home_win = 1 if actual_margin > 0 else 0

    row = conn.execute("""
        SELECT prediction_id, ml_adj_margin, ml_adj_total, ml_adj_h2h_prob,
               rules_margin, rules_total, rules_h2h_prob
        FROM ml_shadow_predictions WHERE match_id = ?
    """, (match_id,)).fetchone()

    if row is None:
        return False  # No ML shadow record for this match

    ml_margin_error   = round(float(row['ml_adj_margin'] or 0) - actual_margin, 2)
    ml_total_error    = round(float(row['ml_adj_total']  or 0) - actual_total,  2)
    ml_h2h_correct    = 1 if ((row['ml_adj_h2h_prob'] or 0.5) >= 0.5) == (actual_margin >= 0) else 0

    rules_margin_error = round(float(row['rules_margin'] or 0) - actual_margin, 2)
    rules_total_error  = round(float(row['rules_total']  or 0) - actual_total,  2)
    rules_h2h_correct  = 1 if ((row['rules_h2h_prob'] or 0.5) >= 0.5) == (actual_margin >= 0) else 0

    conn.execute("""
        UPDATE ml_shadow_predictions SET
            actual_margin      = ?,
            actual_total       = ?,
            actual_home_win    = ?,
            ml_margin_error    = ?,
            ml_total_error     = ?,
            ml_h2h_correct     = ?,
            rules_margin_error = ?,
            rules_total_error  = ?,
            rules_h2h_correct  = ?
        WHERE match_id = ?
    """, (actual_margin, actual_total, actual_home_win,
          ml_margin_error, ml_total_error, ml_h2h_correct,
          rules_margin_error, rules_total_error, rules_h2h_correct,
          match_id))
    conn.commit()
    return True


def _update_tier2(conn, match_id, home_score, away_score):
    """Fill actual columns in tier2_performance."""
    actual_margin   = home_score - away_score
    actual_home_win = 1 if actual_margin > 0 else 0

    row = conn.execute(
        'SELECT run_id FROM tier2_performance WHERE match_id = ?', (match_id,)
    ).fetchone()

    if row is None:
        return False

    conn.execute("""
        UPDATE tier2_performance SET
            actual_margin    = ?,
            actual_home_score = ?,
            actual_away_score = ?,
            actual_winner    = ?
        WHERE match_id = ?
    """, (actual_margin, home_score, away_score, actual_home_win, match_id))
    conn.commit()
    return True


# =============================================================================
# Status report
# =============================================================================

def cmd_status(conn, season, round_number):
    rows = conn.execute("""
        SELECT m.match_id,
               ht.team_name AS home,
               at.team_name AS away,
               r.home_score, r.away_score,
               ml.actual_margin AS ml_filled
        FROM matches m
        JOIN teams ht ON ht.team_id = m.home_team_id
        JOIN teams at ON at.team_id = m.away_team_id
        LEFT JOIN results r ON r.match_id = m.match_id
        LEFT JOIN ml_shadow_predictions ml ON ml.match_id = m.match_id
        WHERE m.season = ? AND m.round_number = ?
        ORDER BY m.match_date, m.kickoff_datetime
    """, (season, round_number)).fetchall()

    if not rows:
        print(f'No matches found for S{season} R{round_number}')
        return

    print(f'\nActuals status — S{season} R{round_number}')
    print(f'  {"MATCH":<45} {"RESULT":<15} {"ML_FILLED":<10}')
    print('  ' + '-' * 70)
    for r in rows:
        match_str  = f'{r["home"]} v {r["away"]}'
        result_str = f'{r["home_score"]}-{r["away_score"]}' if r['home_score'] is not None else 'pending'
        ml_str     = 'yes' if r['ml_filled'] is not None else 'no'
        print(f'  {match_str:<45} {result_str:<15} {ml_str:<10}')


# =============================================================================
# Ingest one game
# =============================================================================

def ingest_one(conn, season, round_number, home_team, away_team, home_score, away_score, verbose=True):
    match = _find_match(conn, season, round_number, home_team, away_team)
    if match is None:
        print(f'  WARNING: match not found — {home_team} v {away_team} S{season} R{round_number}',
              file=sys.stderr)
        return False

    match_id = match['match_id']
    label    = f'{match["home"]} v {match["away"]}'

    result_id, inserted = _insert_result(conn, match_id, home_score, away_score)
    ml_updated   = _update_ml_shadow(conn, match_id, home_score, away_score)
    t2_updated   = _update_tier2(conn, match_id, home_score, away_score)

    if verbose:
        margin = home_score - away_score
        total  = home_score + away_score
        action = 'inserted' if inserted else 'updated'
        print(f'  {label}')
        print(f'    Result: {home_score}-{away_score}  (margin {margin:+d}, total {total})  [{action}]')
        print(f'    ML shadow updated: {ml_updated}  |  tier2_performance updated: {t2_updated}')

    return True


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Ingest actual match results')
    parser.add_argument('--settings', default=SETTINGS_PATH)
    parser.add_argument('--season',   required=True, type=int)
    parser.add_argument('--round',    required=True, type=int, dest='round_number')

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--status', action='store_true',
                      help='Show what is missing for this round')
    mode.add_argument('--home', help='Home team name (single-game mode)')
    mode.add_argument('--from-csv', dest='from_csv',
                      help='Path to CSV with columns: home_team,away_team,home_score,away_score')

    parser.add_argument('--away',       default=None, help='Away team name')
    parser.add_argument('--home-score', default=None, type=int, dest='home_score')
    parser.add_argument('--away-score', default=None, type=int, dest='away_score')

    args = parser.parse_args()
    conn = _get_conn(args.settings)

    if args.status:
        cmd_status(conn, args.season, args.round_number)
        conn.close()
        return

    print(f'\nIngesting actuals — S{args.season} R{args.round_number}')

    if args.home:
        if args.away is None or args.home_score is None or args.away_score is None:
            parser.error('--home requires --away, --home-score and --away-score')
        ingest_one(conn, args.season, args.round_number,
                   args.home, args.away, args.home_score, args.away_score)

    elif args.from_csv:
        if not os.path.exists(args.from_csv):
            print(f'ERROR: CSV not found: {args.from_csv}', file=sys.stderr)
            sys.exit(1)
        with open(args.from_csv, newline='', encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                ingest_one(conn, args.season, args.round_number,
                           row['home_team'], row['away_team'],
                           int(row['home_score']), int(row['away_score']))

    conn.close()
    print('\nDone.')


if __name__ == '__main__':
    main()
