"""
scripts/seed_team_ref_bucket_stats.py

Seed team_ref_bucket_stats using a 2026 PF-proxy approach.

Since no historical referee match data exists, we derive each team's affinity
for each referee bucket from their 2026 points-for average relative to the
league average.

Formula:
    league_avg = mean(all team pf_avgs for season)
    flow_heavy_edge    = clamp((pf_avg - league_avg) * 0.5, -5.0, +5.0)
    whistle_heavy_edge = clamp(-(pf_avg - league_avg) * 0.4, -4.0, +4.0)
    neutral_edge       = 0.0

Logic: high-scoring teams benefit more under free-flowing refs (flow_heavy)
and are hurt more under whistle-heavy refs. Low-scoring teams are the inverse.

Usage:
    python scripts/seed_team_ref_bucket_stats.py [--season 2026] [--dry-run]
"""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'data' / 'model.db'

BUCKETS = ('flow_heavy', 'whistle_heavy', 'neutral')


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def main():
    parser = argparse.ArgumentParser(description='Seed team_ref_bucket_stats via PF proxy')
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Fetch most-recent team stats for the season
    rows = conn.execute(
        """
        SELECT ts.team_id, t.team_name, ts.points_for_avg, ts.games_played
        FROM team_stats ts
        JOIN teams t ON t.team_id = ts.team_id
        WHERE ts.season = ?
          AND ts.team_stat_id IN (
              SELECT team_stat_id FROM team_stats ts2
              WHERE ts2.team_id = ts.team_id AND ts2.season = ts.season
              ORDER BY ts2.as_of_date DESC LIMIT 1
          )
        ORDER BY ts.points_for_avg DESC
        """,
        (args.season,),
    ).fetchall()

    if not rows:
        print(f'ERROR: no team_stats for season {args.season}')
        return

    league_avg = sum(r['points_for_avg'] for r in rows) / len(rows)
    print(f'Season {args.season} — {len(rows)} teams, league avg PF = {league_avg:.3f}')
    print()

    now = datetime.now(timezone.utc).isoformat()
    upserts = []
    for row in rows:
        tid = row['team_id']
        pf  = row['points_for_avg']
        delta = pf - league_avg

        flow_edge    = round(clamp(delta * 0.5, -5.0, 5.0), 3)
        whistle_edge = round(clamp(-delta * 0.4, -4.0, 4.0), 3)
        neutral_edge = 0.0

        edges = {
            'flow_heavy':    flow_edge,
            'whistle_heavy': whistle_edge,
            'neutral':       neutral_edge,
        }

        print(f'  {row["team_name"]} (PF={pf:.2f} Δ={delta:+.2f}): '
              f'flow={flow_edge:+.2f}  whistle={whistle_edge:+.2f}  neutral=0.00')

        for bucket, edge in edges.items():
            upserts.append((tid, bucket, args.season, edge, now))

    print()
    if args.dry_run:
        print('[dry-run] no changes written')
        conn.close()
        return

    conn.executemany(
        """
        INSERT INTO team_ref_bucket_stats (team_id, bucket, season, games, bucket_edge, created_at, updated_at)
        VALUES (?, ?, ?, 0, ?, ?, ?)
        ON CONFLICT(team_id, bucket, season) DO UPDATE SET
            bucket_edge = excluded.bucket_edge,
            updated_at  = excluded.updated_at
        """,
        [(tid, bucket, season, edge, now, now) for (tid, bucket, season, edge, now) in upserts],
    )
    conn.commit()
    print(f'Seeded {len(upserts)} rows into team_ref_bucket_stats.')
    conn.close()


if __name__ == '__main__':
    main()
