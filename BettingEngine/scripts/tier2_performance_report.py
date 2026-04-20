#!/usr/bin/env python3
"""
scripts/tier2_performance_report.py

Tier 2 prediction performance report.

Compares Tier 1 baseline margin predictions against Tier 1 + Tier 2 final
margin predictions for all games with known results.

Reports:
  - Overall MAE comparison
  - Performance by family
  - Performance by combination
  - Performance by signal strength

USAGE
-----
    python scripts/tier2_performance_report.py --season 2026
    python scripts/tier2_performance_report.py --season 2026 --model-version 1.0.0-abc
"""

import argparse
import sqlite3
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def fmt_improvement(val):
    if val is None: return '   N/A'
    sign = '+' if val > 0 else ''
    return f'{sign}{val:.2f}'


def print_section(title: str):
    print(f"\n{'─'*70}")
    print(f"  {title}")
    print(f"{'─'*70}")


def _summary(rows):
    """Compute summary stats from a list of dicts with t1/t12/improvement fields."""
    n = len(rows)
    if n == 0:
        return None
    mae_t1  = sum(r['t1_abs_error']  for r in rows) / n
    mae_t12 = sum(r['t12_abs_error'] for r in rows) / n
    avg_imp = sum(r['abs_improvement'] for r in rows) / n
    n_helped = sum(1 for r in rows if r['abs_improvement'] > 0)
    n_hurt   = sum(1 for r in rows if r['abs_improvement'] < 0)
    n_neutral= sum(1 for r in rows if r['abs_improvement'] == 0)
    t1_win   = sum(1 for r in rows if r['t1_winner_correct'] == 1)
    t12_win  = sum(1 for r in rows if r['final_winner_correct'] == 1)
    direction = [r['t2_direction_correct'] for r in rows if r['t2_direction_correct'] is not None]
    dir_rate = sum(direction) / len(direction) if direction else None
    return {
        'n': n,
        'mae_t1': mae_t1,
        'mae_t12': mae_t12,
        'avg_imp': avg_imp,
        'n_helped': n_helped,
        'n_hurt': n_hurt,
        'n_neutral': n_neutral,
        't1_win_pct': t1_win / n,
        't12_win_pct': t12_win / n,
        'dir_rate': dir_rate,
    }


def print_stats(label, s, indent=4):
    sp = ' ' * indent
    if s is None:
        print(f"{sp}{label:<28}  no data")
        return
    imp_str = fmt_improvement(s['avg_imp'])
    dir_str = f"{s['dir_rate']:.0%}" if s['dir_rate'] is not None else 'N/A'
    helped_str = f"{s['n_helped']}/{s['n']} helped  {s['n_hurt']}/{s['n']} hurt"
    print(f"{sp}{label:<28}  n={s['n']:>3}  "
          f"MAE_T1={s['mae_t1']:>5.2f}  MAE_T12={s['mae_t12']:>5.2f}  "
          f"avg_imp={imp_str}  dir={dir_str}  ({helped_str})")


def main():
    parser = argparse.ArgumentParser(description='Tier 2 performance report')
    parser.add_argument('--season',        type=int, default=2026)
    parser.add_argument('--model-version', default='1.0.0-abc')
    parser.add_argument('--settings',      default='config/settings.yaml')
    args = parser.parse_args()

    settings = yaml.safe_load(open(args.settings))
    conn = sqlite3.connect(settings['database']['path'])
    conn.row_factory = sqlite3.Row

    # All rows with results
    rows = conn.execute("""
        SELECT tp.*, h.team_name as home_name, a.team_name as away_name
        FROM tier2_performance tp
        JOIN teams h ON tp.home_team_id = h.team_id
        JOIN teams a ON tp.away_team_id = a.team_id
        WHERE tp.season = ?
          AND tp.model_version = ?
          AND tp.actual_margin IS NOT NULL
        ORDER BY tp.round_number, tp.match_id
    """, (args.season, args.model_version)).fetchall()

    rows = [dict(r) for r in rows]

    all_count = conn.execute(
        "SELECT COUNT(*) FROM tier2_performance WHERE season=? AND model_version=?",
        (args.season, args.model_version)
    ).fetchone()[0]

    print(f"\n{'='*70}")
    print(f"  TIER 2 PERFORMANCE REPORT  —  Season {args.season}  model={args.model_version}")
    print(f"{'='*70}")
    print(f"  Total priced: {all_count}  |  With results: {len(rows)}  |  Pending: {all_count - len(rows)}")

    if not rows:
        print("\n  No results available yet.")
        conn.close()
        return

    # -------------------------------------------------------------------------
    # 1. Per-game detail
    # -------------------------------------------------------------------------
    print_section("PER-GAME DETAIL")
    print(f"  {'Game':<44}  {'T1':>6}  {'2A':>4} {'2B':>4} {'2C':>4}  "
          f"{'final':>6}  {'actual':>6}  {'T1err':>5}  {'T12err':>5}  {'imp':>6}  families")
    print(f"  {'─'*44}  {'─'*6}  {'─'*4} {'─'*4} {'─'*4}  "
          f"{'─'*6}  {'─'*6}  {'─'*5}  {'─'*5}  {'─'*6}  {'─'*8}")
    for r in rows:
        game = f"R{r['round_number']} {r['home_name']} vs {r['away_name']}"
        imp  = fmt_improvement(r['abs_improvement'])
        fam  = r['fired_families'] or '—'
        print(f"  {game:<44}  {r['t1_margin']:>+6.1f}  "
              f"{r['t2a_home_delta']:>+4.0f} {r['t2b_home_delta']:>+4.0f} {r['t2c_home_delta']:>+4.0f}  "
              f"{r['final_margin']:>+6.1f}  {r['actual_margin']:>+6.1f}  "
              f"{r['t1_abs_error']:>5.1f}  {r['t12_abs_error']:>5.1f}  {imp}  {fam}")

    # -------------------------------------------------------------------------
    # 2. Overall
    # -------------------------------------------------------------------------
    print_section("OVERALL")
    s = _summary(rows)
    print_stats("All games", s)
    fired_rows   = [r for r in rows if r['fired_families']]
    neutral_rows = [r for r in rows if not r['fired_families']]
    print_stats("Tier 2 fired",    _summary(fired_rows))
    print_stats("Tier 2 neutral",  _summary(neutral_rows))

    # -------------------------------------------------------------------------
    # 3. By family
    # -------------------------------------------------------------------------
    print_section("BY FAMILY  (all games where that family fired)")
    for fam_char, label in [('A', '2A — Territory & Control'),
                             ('B', '2B — Creation & Shape'),
                             ('C', '2C — Physical Carry')]:
        subset = [r for r in rows if fam_char in r['fired_families'].split(',')]
        print_stats(label, _summary(subset))

    # -------------------------------------------------------------------------
    # 4. By combination (exact match)
    # -------------------------------------------------------------------------
    print_section("BY COMBINATION  (exact family set)")
    combos = [
        ('A',     '2A only'),
        ('B',     '2B only'),
        ('C',     '2C only'),
        ('A,B',   '2A + 2B'),
        ('A,C',   '2A + 2C'),
        ('B,C',   '2B + 2C'),
        ('A,B,C', '2A + 2B + 2C'),
        ('',      'none (neutral)'),
    ]
    for key, label in combos:
        subset = [r for r in rows if r['fired_families'] == key]
        print_stats(label, _summary(subset))

    # -------------------------------------------------------------------------
    # 5. By signal strength
    # -------------------------------------------------------------------------
    print_section("BY SIGNAL STRENGTH  (strongest label across any firing family)")

    def max_strength(r):
        order = {'strong': 3, 'average': 2, 'weak': 1, 'none': 0}
        labels = [
            r.get('t2a_label_h'), r.get('t2a_label_a'),
            r.get('t2b_label_h'), r.get('t2b_label_a'),
            r.get('t2c_label_h'), r.get('t2c_label_a'),
        ]
        return max((order.get(l, 0) for l in labels if l), default=0)

    for strength_val, label in [(3, 'strong  (≥1 strong signal)'),
                                 (2, 'average (≥1 average, no strong)'),
                                 (1, 'weak    (only weak signals)')]:
        subset = [r for r in rows if max_strength(r) == strength_val]
        print_stats(label, _summary(subset))

    # -------------------------------------------------------------------------
    # 6. Winner direction accuracy
    # -------------------------------------------------------------------------
    print_section("WINNER DIRECTION ACCURACY")
    n = len(rows)
    t1_w  = sum(1 for r in rows if r['t1_winner_correct'] == 1)
    t12_w = sum(1 for r in rows if r['final_winner_correct'] == 1)
    print(f"    T1  correct winner: {t1_w}/{n}  ({t1_w/n:.0%})")
    print(f"    T1+T2 correct winner: {t12_w}/{n}  ({t12_w/n:.0%})")

    conn.close()
    print()


if __name__ == '__main__':
    main()
