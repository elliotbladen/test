#!/usr/bin/env python3
"""
scripts/bootstrap_elo_2023.py

Bootstrap 2023 ELO ratings from historical match results and write them
into the team_stats table so the pricing engine can use real ELO values
instead of the season-quality fallback.

FORMULA
-------
Standard ELO, binary win/loss:

    E_home = 1 / (1 + 10 ^ ((R_away - R_home) / 400))
    E_away = 1 - E_home

    new_R_home = R_home + K * (S_home - E_home)
    new_R_away = R_away + K * (S_away - E_away)

    S = 1.0 (win), 0.5 (draw), 0.0 (loss)

ASSUMPTIONS
-----------
1. All teams start at STARTING_ELO = 1500 (matches default_elo in tiers.yaml).
2. K_FACTOR = 32. Produces ~150-200 point spread over a full NRL season at this K.
3. No home advantage adjustment in the ELO update step. The ELO rating is a
   neutral-venue strength measure. compute_elo_margin() in tier1_baseline.py
   adds league_ha separately when converting ELO diff to expected margin points.
   Including HFA here would double-count it at price time.
4. Margin of victory is not included. Binary W/L only. MOV-adjusted ELO
   requires a calibrated multiplier; omitting it is the correct V1 default.
5. Games are processed in chronological order (match_date ASC, match_id ASC).
6. Only games with match_date < CUTOFF_DATE are used. Cutoff = '2023-08-31'
   (day Round 27 begins). This matches the existing team_stats as_of_date of
   '2023-08-30', so the stored ELO reflects pre-Round-27 team strength.
7. Finals games (rounds 28-31) are excluded by the cutoff date.

OUTPUT
------
Updates elo_rating in team_stats WHERE season=2023 AND as_of_date='2023-08-30'.
Prints a full audit trail of every game and rating change before writing.

USAGE
-----
    cd /path/to/Betting_model
    python scripts/bootstrap_elo_2023.py [--dry-run]
"""

import argparse
import sqlite3
import sys
import yaml
from pathlib import Path

STARTING_ELO  = 1500.0
K_FACTOR      = 32.0
CUTOFF_DATE   = '2023-08-31'   # games strictly before this date are used
SEASON        = 2023
AS_OF_DATE    = '2023-08-30'   # must match as_of_date in team_stats


def expected_score(r_a: float, r_b: float) -> float:
    """ELO expected score for team A vs team B at a neutral venue."""
    return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 400.0))


def load_matches(conn: sqlite3.Connection) -> list:
    """
    Load all 2023 matches with results, in chronological order,
    up to (not including) the cutoff date.
    Returns list of dicts with match_id, match_date, round_number,
    home_team_id, away_team_id, home_score, away_score.
    """
    rows = conn.execute(
        """
        SELECT
            m.match_id,
            m.match_date,
            m.round_number,
            m.home_team_id,
            m.away_team_id,
            r.home_score,
            r.away_score,
            th.team_name AS home_team,
            ta.team_name AS away_team
        FROM   matches m
        JOIN   results r  ON r.match_id    = m.match_id
        JOIN   teams   th ON th.team_id    = m.home_team_id
        JOIN   teams   ta ON ta.team_id    = m.away_team_id
        WHERE  m.season     = ?
          AND  m.match_date < ?
        ORDER  BY m.match_date ASC, m.match_id ASC
        """,
        (SEASON, CUTOFF_DATE),
    ).fetchall()
    return [dict(r) for r in rows]


def compute_elo(matches: list) -> dict:
    """
    Run ELO calculation over the match list.

    Returns dict of {team_id: final_elo_rating}.
    Also prints a full audit trail of every game.
    """
    # Collect all team IDs and initialise at starting ELO
    team_ids = set()
    for m in matches:
        team_ids.add(m['home_team_id'])
        team_ids.add(m['away_team_id'])
    ratings = {tid: STARTING_ELO for tid in team_ids}

    # Also collect team names for readable output
    team_names = {}
    for m in matches:
        team_names[m['home_team_id']] = m['home_team']
        team_names[m['away_team_id']] = m['away_team']

    print(f"ELO bootstrap — season {SEASON}, cutoff {CUTOFF_DATE}")
    print(f"K={K_FACTOR}  starting_elo={STARTING_ELO}  games={len(matches)}")
    print(f"\n{'Rd':>3}  {'Date':>10}  {'Home':>35}  {'Away':>35}  "
          f"{'Score':>7}  {'ΔHome':>7}  {'ΔAway':>7}")
    print("-" * 110)

    prev_round = None

    for m in matches:
        hid  = m['home_team_id']
        aid  = m['away_team_id']
        r_h  = ratings[hid]
        r_a  = ratings[aid]
        hs   = m['home_score']
        aws  = m['away_score']
        rn   = m['round_number']

        # Print round separator
        if rn != prev_round:
            if prev_round is not None:
                print()
            prev_round = rn

        # Expected scores (neutral venue — no HFA in ELO step)
        e_h = expected_score(r_h, r_a)
        e_a = 1.0 - e_h

        # Actual scores
        if hs > aws:
            s_h, s_a = 1.0, 0.0
        elif hs < aws:
            s_h, s_a = 0.0, 1.0
        else:
            s_h, s_a = 0.5, 0.5

        # ELO update
        delta_h = K_FACTOR * (s_h - e_h)
        delta_a = K_FACTOR * (s_a - e_a)

        ratings[hid] = r_h + delta_h
        ratings[aid] = r_a + delta_a

        print(
            f"{rn:>3}  {m['match_date']:>10}  "
            f"{m['home_team']:>35}  {m['away_team']:>35}  "
            f"{hs:>3}-{aws:<3}  {delta_h:>+7.2f}  {delta_a:>+7.2f}"
        )

    return ratings, team_names


def print_final_table(ratings: dict, team_names: dict) -> None:
    """Print final ELO table sorted by rating descending."""
    print(f"\n\n{'='*60}")
    print(f"Final ELO ratings entering Round 27 (as of {AS_OF_DATE})")
    print(f"{'='*60}")
    print(f"  {'Team':>35}  {'ELO':>8}  {'Δ from start':>13}")
    print(f"  {'-'*35}  {'-'*8}  {'-'*13}")
    for tid, elo in sorted(ratings.items(), key=lambda x: -x[1]):
        name  = team_names.get(tid, f"team_id={tid}")
        delta = elo - STARTING_ELO
        print(f"  {name:>35}  {elo:>8.1f}  {delta:>+13.1f}")


def write_elo_to_db(conn: sqlite3.Connection, ratings: dict, dry_run: bool) -> None:
    """
    UPDATE elo_rating in team_stats for each team.
    Only updates rows WHERE season=SEASON AND as_of_date=AS_OF_DATE.
    Raises if no matching row is found for a team.
    """
    print(f"\n\n{'='*60}")
    if dry_run:
        print("DRY RUN — no writes to database")
    else:
        print(f"Writing ELO ratings to team_stats (as_of_date={AS_OF_DATE})")
    print(f"{'='*60}")

    for team_id, elo in sorted(ratings.items(), key=lambda x: -x[1]):
        # Check the row exists before updating
        row = conn.execute(
            "SELECT team_stat_id FROM team_stats WHERE team_id=? AND season=? AND as_of_date=?",
            (team_id, SEASON, AS_OF_DATE),
        ).fetchone()

        if row is None:
            print(f"  WARNING: no team_stats row for team_id={team_id} "
                  f"season={SEASON} as_of_date={AS_OF_DATE} — skipping")
            continue

        if not dry_run:
            conn.execute(
                "UPDATE team_stats SET elo_rating=? WHERE team_stat_id=?",
                (round(elo, 2), row[0]),
            )

        marker = "(dry-run)" if dry_run else "written"
        print(f"  team_id={team_id:>2}  elo={elo:>8.2f}  stat_id={row[0]}  {marker}")

    if not dry_run:
        conn.commit()
        print("\nCommitted.")


def main():
    parser = argparse.ArgumentParser(
        description='Bootstrap 2023 ELO ratings from historical results'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print audit trail but do not write to the database'
    )
    parser.add_argument(
        '--settings', default='config/settings.yaml',
        help='Path to settings.yaml (default: config/settings.yaml)'
    )
    args = parser.parse_args()

    settings_path = Path(args.settings)
    if not settings_path.exists():
        print(f"ERROR: settings file not found: {settings_path}", file=sys.stderr)
        sys.exit(1)

    with open(settings_path) as f:
        settings = yaml.safe_load(f)

    db_path = settings.get('database', {}).get('path', 'data/model.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    matches = load_matches(conn)
    if not matches:
        print(f"ERROR: no matches found for season {SEASON} before {CUTOFF_DATE}", file=sys.stderr)
        sys.exit(1)

    ratings, team_names = compute_elo(matches)
    print_final_table(ratings, team_names)
    write_elo_to_db(conn, ratings, dry_run=args.dry_run)

    conn.close()


if __name__ == '__main__':
    main()
