#!/usr/bin/env python3
"""
ml/features/referee_features.py

Session 7 — Add referee features to the game log.

Joins RLP match data + referee assignments + penalty counts.
Computes rolling pre-game referee stats (no look-ahead):
  - ref_total_diff      average total in ref's games vs league avg that season
  - ref_penalty_rate    average total penalties per game
  - ref_home_bias       home penalty rate minus away penalty rate
  - ref_home_win_pct    home win % in ref's games
  - ref_sample          number of prior games we have on this referee

Requires MIN_SAMPLE prior games before populating (else blank).

USAGE
-----
    python ml/features/referee_features.py \
        --game-log  ml/results/game_log_weather.csv \
        --rlp-matches ml/data/rlp_match_data.csv \
        --rlp-refs    ml/data/rlp_ref_data.csv \
        --rlp-ref-matches ml/data/rlp_ref_match_data.csv \
        --out       ml/results/game_log_referee.csv
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

MIN_SAMPLE = 10   # minimum prior games before trusting ref stats

# Map RLP team names → our canonical names
RLP_NAME_MAP = {
    'Manly Warringah Sea Eagles':       'Manly-Warringah Sea Eagles',
    'Canterbury Bulldogs':              'Canterbury-Bankstown Bulldogs',
    'Cronulla Sutherland Sharks':       'Cronulla-Sutherland Sharks',
    'Cronulla-Sutherland Sharks':       'Cronulla-Sutherland Sharks',
    'North Queensland Cowboys':         'North Queensland Cowboys',
    'St George Illawarra Dragons':      'St. George Illawarra Dragons',
    'St. George Illawarra Dragons':     'St. George Illawarra Dragons',
    'Brisbane Broncos':                 'Brisbane Broncos',
    'Canberra Raiders':                 'Canberra Raiders',
    'Gold Coast Titans':                'Gold Coast Titans',
    'Melbourne Storm':                  'Melbourne Storm',
    'Newcastle Knights':                'Newcastle Knights',
    'New Zealand Warriors':             'New Zealand Warriors',
    'Parramatta Eels':                  'Parramatta Eels',
    'Penrith Panthers':                 'Penrith Panthers',
    'South Sydney Rabbitohs':           'South Sydney Rabbitohs',
    'Sydney Roosters':                  'Sydney Roosters',
    'Wests Tigers':                     'Wests Tigers',
    'Dolphins':                         'Dolphins',
    'Gold Coast Chargers':              'Gold Coast Chargers',
    'Northern Eagles':                  'Northern Eagles',
    # Older name variations
    'Manly Sea Eagles':                 'Manly-Warringah Sea Eagles',
    'Canterbury-Bankstown Bulldogs':    'Canterbury-Bankstown Bulldogs',
    'North QLD Cowboys':                'North Queensland Cowboys',
    'NZ Warriors':                      'New Zealand Warriors',
    'Warriors':                         'New Zealand Warriors',
    'Brisbane':                         'Brisbane Broncos',
    'Canberra':                         'Canberra Raiders',
    'Gold Coast':                       'Gold Coast Titans',
    'Melbourne':                        'Melbourne Storm',
    'Newcastle':                        'Newcastle Knights',
    'Parramatta':                       'Parramatta Eels',
    'Penrith':                          'Penrith Panthers',
    'South Sydney':                     'South Sydney Rabbitohs',
}

def canon_rlp(name: str) -> str:
    s = str(name).strip()
    return RLP_NAME_MAP.get(s, s)

def safe_int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default

def safe_float(v, default=None):
    try:
        f = float(v)
        return f if f == f else default
    except (TypeError, ValueError):
        return default


def build_rlp_lookup(matches_path, refs_path, ref_matches_path):
    """
    Join RLP files into a lookup:
    (date, home_team_canonical, away_team_canonical) → {
        referee, home_penalties, away_penalties, total_penalties
    }
    """
    # Load referee names
    ref_names = {}
    with open(refs_path) as f:
        for r in csv.DictReader(f):
            ref_names[r['ref_id']] = r['full_name']

    # Load referee per match
    ref_by_match = {}
    with open(ref_matches_path) as f:
        for r in csv.DictReader(f):
            ref_by_match[r['match_id']] = ref_names.get(r['ref_id'], '')

    # Build lookup
    lookup = {}
    with open(matches_path) as f:
        for r in csv.DictReader(f):
            if r['competition'] != 'NRL':
                continue
            if r['competition_year'] < 'NRL 2009':
                continue

            home = canon_rlp(r['home_team'])
            away = canon_rlp(r['away_team'])
            date = r['date']
            mid  = r['match_id']
            ref  = ref_by_match.get(mid, '')

            hp = safe_int(r.get('home_team_penalties'))
            ap = safe_int(r.get('away_team_penalties'))
            tp = (hp + ap) if hp is not None and ap is not None else None

            key = (date, home, away)
            lookup[key] = {
                'referee':        ref,
                'home_penalties': hp,
                'away_penalties': ap,
                'total_penalties': tp,
            }

    return lookup


def build_referee_features(rows, rlp_lookup):
    """
    For each game in the log, look up referee and compute rolling
    pre-game stats for that referee. No look-ahead.
    """
    # Running stats per referee
    # {ref_name: {'totals': [], 'penalties': [], 'home_penalties': [],
    #             'away_penalties': [], 'home_wins': [], 'season_totals': {}}}
    ref_history = defaultdict(lambda: {
        'totals': [], 'penalties': [], 'home_pen': [],
        'away_pen': [], 'home_wins': []
    })

    # Season-level league averages (updated as we go)
    season_totals = defaultdict(list)

    out_rows = []

    for r in rows:
        date     = r['date']
        season   = int(r['season'])
        home     = r['home_team']
        away     = r['away_team']

        # Look up RLP data for this game
        rlp = rlp_lookup.get((date, home, away)) or \
              rlp_lookup.get((date, away, home))  # try flipped

        referee      = rlp['referee']        if rlp else ''
        home_pen     = rlp['home_penalties'] if rlp else None
        away_pen     = rlp['away_penalties'] if rlp else None
        total_pen    = rlp['total_penalties'] if rlp else None

        # League average total for this season so far
        league_avg = (sum(season_totals[season]) / len(season_totals[season])
                      if season_totals[season] else None)

        # Referee rolling stats (BEFORE this game)
        hist = ref_history[referee] if referee else None
        n    = len(hist['totals']) if hist else 0

        if hist and n >= MIN_SAMPLE:
            ref_avg_total     = round(sum(hist['totals']) / n, 2)
            ref_total_diff    = round(ref_avg_total - league_avg, 2) if league_avg else None
            ref_penalty_rate  = round(sum(hist['penalties']) / n, 2) if hist['penalties'] else None
            ref_home_bias     = round(
                (sum(hist['home_pen']) / n) - (sum(hist['away_pen']) / n), 2
            ) if hist['home_pen'] and hist['away_pen'] else None
            ref_home_win_pct  = round(sum(hist['home_wins']) / n, 4)
            ref_sample        = n
        else:
            ref_avg_total    = None
            ref_total_diff   = None
            ref_penalty_rate = None
            ref_home_bias    = None
            ref_home_win_pct = None
            ref_sample       = n

        row = dict(r)
        row.update({
            'referee':         referee,
            'ref_total_diff':  ref_total_diff  if ref_total_diff  is not None else '',
            'ref_penalty_rate': ref_penalty_rate if ref_penalty_rate is not None else '',
            'ref_home_bias':   ref_home_bias   if ref_home_bias   is not None else '',
            'ref_home_win_pct': ref_home_win_pct if ref_home_win_pct is not None else '',
            'ref_sample':      ref_sample,
            'home_penalties':  home_pen if home_pen is not None else '',
            'away_penalties':  away_pen if away_pen is not None else '',
        })
        out_rows.append(row)

        # Update rolling stats AFTER capturing snapshot
        actual_total = safe_int(r.get('actual_total'))
        home_win     = safe_int(r.get('home_win'), 0)

        if actual_total is not None:
            season_totals[season].append(actual_total)

        if referee and actual_total is not None:
            hist['totals'].append(actual_total)
            hist['home_wins'].append(home_win)
            if total_pen is not None:
                hist['penalties'].append(total_pen)
            if home_pen is not None:
                hist['home_pen'].append(home_pen)
            if away_pen is not None:
                hist['away_pen'].append(away_pen)

    return out_rows


def print_summary(rows):
    has_ref  = [r for r in rows if r['referee']]
    has_stats = [r for r in rows if r['ref_total_diff'] != '']
    no_ref   = len(rows) - len(has_ref)

    print(f"\n  {'─'*55}")
    print(f"  Referee features summary")
    print(f"  {'─'*55}")
    print(f"  Games with referee:       {len(has_ref)}")
    print(f"  Games with ref stats:     {len(has_stats)}")
    print(f"  Games without referee:    {no_ref}")

    if has_stats:
        diffs = [float(r['ref_total_diff']) for r in has_stats]
        pen   = [float(r['ref_penalty_rate']) for r in has_stats if r['ref_penalty_rate'] != '']
        print(f"\n  ref_total_diff range:   {min(diffs):.2f} – {max(diffs):.2f}")
        if pen:
            print(f"  ref_penalty_rate range: {min(pen):.1f} – {max(pen):.1f}")

        # Top refs by total deviation
        from collections import defaultdict
        ref_diffs = defaultdict(list)
        for r in has_stats:
            ref_diffs[r['referee']].append(float(r['ref_total_diff']))
        ref_avg = {ref: sum(v)/len(v) for ref, v in ref_diffs.items() if len(v) >= 20}
        by_diff = sorted(ref_avg.items(), key=lambda x: x[1])

        print(f"\n  Lowest scoring refs (total diff vs league avg):")
        for ref, diff in by_diff[:4]:
            print(f"    {ref:<30}  {diff:+.2f} pts")
        print(f"  Highest scoring refs:")
        for ref, diff in by_diff[-4:]:
            print(f"    {ref:<30}  {diff:+.2f} pts")


def main():
    parser = argparse.ArgumentParser(description='Add referee features to game log')
    parser.add_argument('--game-log',        default=str(ROOT / 'ml/results/game_log_weather.csv'))
    parser.add_argument('--rlp-matches',     default=str(ROOT / 'ml/data/rlp_match_data.csv'))
    parser.add_argument('--rlp-refs',        default=str(ROOT / 'ml/data/rlp_ref_data.csv'))
    parser.add_argument('--rlp-ref-matches', default=str(ROOT / 'ml/data/rlp_ref_match_data.csv'))
    parser.add_argument('--out',             default=str(ROOT / 'ml/results/game_log_referee.csv'))
    args = parser.parse_args()

    for p in [args.game_log, args.rlp_matches, args.rlp_refs, args.rlp_ref_matches]:
        if not Path(p).exists():
            print(f"ERROR: not found: {p}", file=sys.stderr)
            sys.exit(1)

    print("Building RLP referee lookup ...")
    rlp_lookup = build_rlp_lookup(
        args.rlp_matches, args.rlp_refs, args.rlp_ref_matches
    )
    print(f"  {len(rlp_lookup)} games in RLP lookup")

    print("Loading game log ...")
    with open(args.game_log) as f:
        rows = list(csv.DictReader(f))
    print(f"  {len(rows)} games")

    print("Building referee features (no look-ahead) ...")
    out_rows = build_referee_features(rows, rlp_lookup)

    print_summary(out_rows)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out_rows[0].keys())
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\n  Written {len(out_rows)} rows → {out}")
    print("\nDone.")


if __name__ == '__main__':
    main()
