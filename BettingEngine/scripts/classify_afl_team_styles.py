#!/usr/bin/env python3
"""
scripts/classify_afl_team_styles.py

Reads a Footywire round snapshot and classifies every AFL team into
five style families. Shows each team's z-score profile so you can verify
they are sitting in the right family before running the T2 engine.

Style Families
--------------
  A: Contested Possession   — CP, CCL, SCL, HO
  B: Territory / Ball Mvm't — MG/game, DE%, kicking_ratio (K/total disp)
  C: Forward Entry          — I50, MI5, T50, goal conversion
  D: Defensive Structure    — ITC, R50, 1%, CM
  E: Pressure / Turnovers   — Tackles, T50, TO (forced), clangers (allowed)

Each stat is z-scored against league average for that snapshot.
Family score = weighted average of constituent z-scores.
Teams are ranked within each family and tiered: ELITE / STRONG / AVG / WEAK / POOR.

USAGE
-----
    python3 scripts/classify_afl_team_styles.py --season 2026 --round 9
    python3 scripts/classify_afl_team_styles.py --season 2026 --round 9 --family A
    python3 scripts/classify_afl_team_styles.py --season 2025 --round 999  (full 2025 season)
"""

import argparse
import csv
import math
from pathlib import Path

ROOT      = Path(__file__).resolve().parent.parent
SNAP_CSV  = ROOT / 'data' / 'footywire_snapshots.csv'
HIST_CSV  = ROOT / 'data' / 'footywire_team_stats.csv'   # full-season fallback

# ── Family definitions ────────────────────────────────────────────────────────
# Each entry: (field_name, weight, higher_is_better)
# Weight determines contribution to family score.
# higher_is_better=False means we INVERT the z-score (e.g. clangers: fewer = better)
FAMILIES = {
    'A': {
        'label':  'Contested Possession',
        'emoji':  '⚔️',
        'stats': [
            ('cp_pg',           0.40, True),
            ('centre_cl_pg',    0.30, True),
            ('stoppage_cl_pg',  0.20, True),
            ('hitouts_pg',      0.10, True),
        ],
        'interpretation': 'High = wins the ball at stoppages and ruck contests',
    },
    'B': {
        'label':  'Territory / Ball Movement',
        'emoji':  '🏃',
        'stats': [
            ('mg_pg',           0.45, True),
            ('disposal_eff_pct',0.35, True),
            ('kicking_ratio',   0.20, True),   # kick-dominant style = more territory
        ],
        'interpretation': 'High = moves ball forward efficiently, gains metres',
    },
    'C': {
        'label':  'Forward Entry & Scoring',
        'emoji':  '🎯',
        'stats': [
            ('inside_50s_pg',   0.35, True),
            ('marks_i50_pg',    0.30, True),
            ('goal_conv_pct',   0.25, True),
            ('tackles_i50_pg',  0.10, True),
        ],
        'interpretation': 'High = gets forward and finishes — the most margin-predictive family',
    },
    'D': {
        'label':  'Defensive Structure',
        'emoji':  '🛡️',
        'stats': [
            ('intercepts_pg',   0.40, True),
            ('rebound_50s_pg',  0.30, True),
            ('one_pct_pg',      0.20, True),   # spoils, shepherds
            ('cont_marks_pg',   0.10, True),   # key position defensive marks
        ],
        'interpretation': 'High = intercept/rebound defence, reads ball, limits opposition I50s',
    },
    'E': {
        'label':  'Pressure / Turnovers',
        'emoji':  '💥',
        'stats': [
            ('tackles_pg',      0.40, True),
            ('turnovers_pg',    0.30, False),  # turnovers GIVEN AWAY — lower is better
            ('clangers_pg',     0.30, False),  # unforced errors — lower is better
        ],
        'interpretation': 'High = high tackle pressure, few turnovers and errors',
    },
}

TIER_LABELS = [
    (+1.25, 'ELITE',  '▲▲'),
    (+0.60, 'STRONG', '▲'),
    (-0.60, 'AVG',    '—'),
    (-1.25, 'WEAK',   '▼'),
    (-9.99, 'POOR',   '▼▼'),
]


def tier_label(z: float) -> tuple[str, str]:
    for threshold, label, arrow in TIER_LABELS:
        if z >= threshold:
            return label, arrow
    return 'POOR', '▼▼'


def load_snapshot(season: int, round_num: int) -> list[dict] | None:
    """Load rows from footywire_snapshots.csv for a specific season+round."""
    if not SNAP_CSV.exists():
        return None
    rows = []
    with open(SNAP_CSV) as f:
        for r in csv.DictReader(f):
            if int(r['season']) == season and int(r['round_number']) == round_num:
                rows.append(r)
    return rows if rows else None


def load_full_season(season: int) -> list[dict] | None:
    """Load from full-season CSV as fallback."""
    if not HIST_CSV.exists():
        return None
    rows = []
    with open(HIST_CSV) as f:
        for r in csv.DictReader(f):
            if int(r['season']) == season:
                rows.append(r)
    return rows if rows else None


def to_float(val) -> float | None:
    try:
        return float(val) if val not in (None, '', 'None') else None
    except (ValueError, TypeError):
        return None


def compute_league_norms(rows: list[dict], fields: list[str]) -> dict[str, tuple[float, float]]:
    """Returns {field: (mean, std)} across all teams in snapshot."""
    norms = {}
    for field in fields:
        vals = [to_float(r.get(field)) for r in rows]
        vals = [v for v in vals if v is not None]
        if not vals:
            norms[field] = (0.0, 1.0)
            continue
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / max(len(vals) - 1, 1)
        std = math.sqrt(variance) if variance > 0 else 1.0
        norms[field] = (mean, std)
    return norms


def z_score(val: float | None, mean: float, std: float) -> float | None:
    if val is None:
        return None
    return (val - mean) / std if std > 0 else 0.0


def compute_family_score(row: dict, family_def: dict, norms: dict) -> tuple[float, dict]:
    """Returns (weighted_z_score, {stat: z_score})."""
    total_weight = 0.0
    weighted_sum = 0.0
    breakdown = {}
    for field, weight, higher_is_better in family_def['stats']:
        val  = to_float(row.get(field))
        mean, std = norms.get(field, (0.0, 1.0))
        z = z_score(val, mean, std)
        if z is None:
            continue
        if not higher_is_better:
            z = -z
        breakdown[field] = round(z, 2)
        weighted_sum  += z * weight
        total_weight  += weight
    composite = weighted_sum / total_weight if total_weight > 0 else 0.0
    return round(composite, 3), breakdown


def print_family_report(family_key: str, family_def: dict, team_scores: list[tuple],
                        norms: dict, show_detail: bool = True):
    label  = family_def['label']
    emoji  = family_def['emoji']
    interp = family_def['interpretation']

    print()
    print(f'  ┌─────────────────────────────────────────────────────────────────────────────┐')
    print(f'  │  Family {family_key}: {emoji}  {label:<52}   │')
    print(f'  │  {interp:<75}│')
    print(f'  └─────────────────────────────────────────────────────────────────────────────┘')
    print()

    # Column header
    stat_fields = [s[0] for s in family_def['stats']]
    stat_cols   = '  '.join(f'{f[:8]:>8}' for f in stat_fields)
    print(f"  {'Team':<40}  {'Score':>7}  {'Tier':<8}  {stat_cols}")
    print('  ' + '─' * (40 + 7 + 8 + len(stat_fields) * 10 + 8))

    for team, composite, breakdown in team_scores:
        tier, arrow = tier_label(composite)
        stat_zs = '  '.join(
            f'{breakdown.get(f, 0.0):>+8.2f}' for f, _, _ in family_def['stats']
        )
        marker = '  ◀' if tier in ('ELITE', 'POOR') else ''
        print(f'  {team:<40}  {composite:>+7.3f}  {arrow} {tier:<6}  {stat_zs}{marker}')

    # Stat averages for context
    print()
    print(f'  League averages for this snapshot:')
    for field, weight, _ in family_def['stats']:
        mean, std = norms.get(field, (0.0, 1.0))
        print(f'    {field:<28} avg={mean:7.2f}  std={std:5.2f}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--round',  type=int, default=999,
                        help='Round snapshot to use (default 999 = full season)')
    parser.add_argument('--family', type=str, default='ALL',
                        help='Show specific family only (A/B/C/D/E/ALL)')
    parser.add_argument('--detail', action='store_true', default=True)
    args = parser.parse_args()

    # Load data
    rows = load_snapshot(args.season, args.round)
    source = f'{args.season} R{args.round} snapshot'

    if rows is None:
        # Try full season fallback
        rows = load_full_season(args.season)
        source = f'{args.season} full-season averages (no round snapshot found)'
        if rows is None:
            print(f'No data found for {args.season} R{args.round}.')
            print(f'Run: python3 scripts/scrape_footywire_round_snapshot.py '
                  f'--season {args.season} --round {args.round}')
            return

    print()
    print('═' * 80)
    print(f'  AFL Team Style Profiles  —  {source}')
    print(f'  {len(rows)} teams loaded')
    print('═' * 80)

    # Gather all fields needed
    all_fields = list({f for fam in FAMILIES.values() for f, _, _ in fam['stats']})
    norms = compute_league_norms(rows, all_fields)

    # Compute family scores for all teams
    family_results = {}
    for fam_key, fam_def in FAMILIES.items():
        scores = []
        for row in rows:
            team = row['team_name']
            composite, breakdown = compute_family_score(row, fam_def, norms)
            scores.append((team, composite, breakdown))
        # Sort by composite score descending
        scores.sort(key=lambda x: -x[1])
        family_results[fam_key] = scores

    # ── Summary table ─────────────────────────────────────────────────────────
    families_to_show = (list(FAMILIES.keys())
                        if args.family.upper() == 'ALL'
                        else [args.family.upper()])

    if args.family.upper() == 'ALL':
        print()
        print('  SUMMARY — Team tier in each family  (ELITE▲▲ STRONG▲ AVG— WEAK▼ POOR▼▼)')
        print()
        hdr = f"  {'Team':<40}"
        for fk in FAMILIES:
            hdr += f'  {fk:>8}'
        print(hdr)
        print('  ' + '─' * 82)

        for row in rows:
            team = row['team_name']
            line = f'  {team:<40}'
            for fk in FAMILIES:
                scores = family_results[fk]
                match  = next((s for s in scores if s[0] == team), None)
                if match:
                    _, arrow = tier_label(match[1])
                    z_str   = f'{match[1]:+.2f}'
                    line += f'  {arrow}{z_str:>6}'
                else:
                    line += f'  {"?":>8}'
            print(line)

        print()
        print('  Score = composite z-score (positive = above league avg)')

    # ── Per-family detail ─────────────────────────────────────────────────────
    for fk in families_to_show:
        if fk not in FAMILIES:
            print(f'Unknown family: {fk}. Choose from A B C D E ALL')
            continue
        print_family_report(fk, FAMILIES[fk], family_results[fk], norms)

    # ── Style label summary ───────────────────────────────────────────────────
    if args.family.upper() == 'ALL':
        print()
        print('═' * 80)
        print('  STYLE LABELS  (dominant families per team)')
        print('═' * 80)
        print()
        print(f"  {'Team':<40}  {'Primary style':<30}  Notes")
        print('  ' + '─' * 78)

        for row in rows:
            team = row['team_name']
            # Get composite z per family for this team
            zs = {}
            for fk in FAMILIES:
                match = next((s for s in family_results[fk] if s[0] == team), None)
                zs[fk] = match[1] if match else 0.0

            # Sort families by absolute z-score descending to find dominant
            dominant = sorted(zs.items(), key=lambda x: -x[1])
            best_fk,  best_z  = dominant[0]
            worst_fk, worst_z = min(zs.items(), key=lambda x: x[1])

            best_label  = FAMILIES[best_fk]['label']
            worst_label = FAMILIES[worst_fk]['label']

            if best_z > 0.5:
                style = f'{FAMILIES[best_fk]["emoji"]} {best_fk}:{best_label}'
            else:
                style = 'Balanced / Average'

            note = ''
            if worst_z < -0.5:
                note = f'weak: {worst_fk} ({worst_label})'

            print(f'  {team:<40}  {style:<30}  {note}')

    print()
    print('═' * 80)


if __name__ == '__main__':
    main()
