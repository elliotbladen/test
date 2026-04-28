#!/usr/bin/env python3
"""
scripts/derive_t2_multipliers.py

Derives AFL Tier 2 style-matchup multipliers from historical data.

Approach:
  1. Load game-level margin data from ml/afl/results/features_afl.csv (2013-2023)
  2. Load season-average team stats from data/footywire_team_stats.csv
  3. For each game, compute home-vs-away differentials for:
       - CP per game
       - Clearances per game
       - Inside 50s per game
       - Rebound 50s per game
       - Marks inside 50 per game
       - Goal conversion %
  4. Run OLS regression:
       margin ~ elo_diff + cp_diff + clearance_diff + inside50_diff
                + rebound50_diff + marks_i50_diff + goal_conv_diff
     (ELO controls for baseline quality; style diffs show incremental effect)
  5. Print findings: coefficients, t-stats, p-values, R² and what multipliers
     to use in T2_CONFIG.

Usage:
    python3 scripts/derive_t2_multipliers.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import statsmodels.api as sm
except ImportError:
    print("statsmodels not installed. Run: pip3 install statsmodels")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# 1. Load data
# ─────────────────────────────────────────────────────────────────────────────
print("Loading data...")

games = pd.read_csv(ROOT / 'ml/afl/results/features_afl.csv')
fw    = pd.read_csv(ROOT / 'data/footywire_team_stats.csv')

# Filter to training years (Footywire data starts 2013; keep through 2023 to
# avoid data leakage into 2024/2025 test set)
games = games[(games['season'] >= 2013) & (games['season'] <= 2023)].copy()
games = games[games['split'].isin(['train', 'validate'])].copy()

# Exclude finals (style matchup is most useful in regular season)
games = games[games['is_final'] == 0].copy()

print(f"  Games (reg season, 2013-2023): {len(games)}")
print(f"  Footywire rows: {len(fw)}, seasons: {fw['season'].min()}-{fw['season'].max()}")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Build per-game style differentials
# ─────────────────────────────────────────────────────────────────────────────
print("\nBuilding style differentials...")

# Create lookup: (season, team) → stats dict
fw_lookup: dict = {}
for _, row in fw.iterrows():
    fw_lookup[(row['season'], row['team_name'])] = row.to_dict()

STYLE_COLS = {
    'cp_pg':            'cp_diff',
    'clearances_pg':    'cl_diff',
    'inside_50s_pg':    'i50_diff',
    'rebound_50s_pg':   'r50_diff',
    'marks_i50_pg':     'mi50_diff',
    'goal_conv_pct':    'gconv_diff',
}

records = []
missing = 0
for _, g in games.iterrows():
    key_h = (g['season'], g['home_team'])
    key_a = (g['season'], g['away_team'])
    h = fw_lookup.get(key_h)
    a = fw_lookup.get(key_a)
    if h is None or a is None:
        missing += 1
        continue

    rec = {
        'season':      g['season'],
        'home_team':   g['home_team'],
        'away_team':   g['away_team'],
        'margin':      g['home_margin'],
        'elo_diff':    g['elo_diff'],
    }
    ok = True
    for stat, diff_name in STYLE_COLS.items():
        hv = h.get(stat)
        av = a.get(stat)
        if hv is None or av is None or (hv != hv) or (av != av):
            ok = False
            break
        rec[diff_name] = hv - av
    if ok:
        records.append(rec)

df = pd.DataFrame(records)
print(f"  Games with complete style data: {len(df)}  (skipped {missing} missing)")
print(f"  Margin range: {df['margin'].min():.0f} – {df['margin'].max():.0f}  "
      f"mean={df['margin'].mean():.1f}")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Correlation summary before regression
# ─────────────────────────────────────────────────────────────────────────────
print("\n──────────────────────────────────────────────────────────────────────────")
print("Correlation of style differentials with final margin (home perspective):")
print("──────────────────────────────────────────────────────────────────────────")

diff_cols = ['elo_diff', 'cp_diff', 'cl_diff', 'i50_diff', 'r50_diff',
             'mi50_diff', 'gconv_diff']
col_labels = {
    'elo_diff':   'ELO difference',
    'cp_diff':    'CP/game difference',
    'cl_diff':    'Clearances/game difference',
    'i50_diff':   'Inside 50s/game difference',
    'r50_diff':   'Rebound 50s/game difference',
    'mi50_diff':  'Marks i50/game difference',
    'gconv_diff': 'Goal conv % difference',
}
corr = df[diff_cols + ['margin']].corr()['margin'].drop('margin')
for col in diff_cols:
    print(f"  {col_labels[col]:<35} r = {corr[col]:+.3f}")

# ─────────────────────────────────────────────────────────────────────────────
# 4. OLS Regression: margin ~ elo + style diffs
# ─────────────────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════════════════════════════")
print("OLS REGRESSION: margin ~ elo_diff + style_diffs")
print("══════════════════════════════════════════════════════════════════════════\n")

X_cols = diff_cols
X = sm.add_constant(df[X_cols])
y = df['margin']

model = sm.OLS(y, X).fit()
print(model.summary(xname=['const'] + X_cols))

# ─────────────────────────────────────────────────────────────────────────────
# 5. Style-only regression (controlling for ELO)
# ─────────────────────────────────────────────────────────────────────────────
# Partial out ELO to see pure style effects
print("\n══════════════════════════════════════════════════════════════════════════")
print("STYLE-ONLY REGRESSION: margin_residual ~ style_diffs (ELO partialled out)")
print("══════════════════════════════════════════════════════════════════════════\n")

elo_model = sm.OLS(y, sm.add_constant(df[['elo_diff']])).fit()
df['margin_resid'] = model.resid + elo_model.params['elo_diff'] * df['elo_diff']  # not quite residual, just informational
# Proper residual:
df['margin_resid'] = y - elo_model.predict(sm.add_constant(df[['elo_diff']]))

style_cols = ['cp_diff', 'cl_diff', 'i50_diff', 'r50_diff', 'mi50_diff', 'gconv_diff']
X2 = sm.add_constant(df[style_cols])
model2 = sm.OLS(df['margin_resid'], X2).fit()
print(model2.summary(xname=['const'] + style_cols))

# ─────────────────────────────────────────────────────────────────────────────
# 6. Practical multiplier derivation
# ─────────────────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════════════════════════════")
print("PRACTICAL T2 MULTIPLIERS")
print("══════════════════════════════════════════════════════════════════════════")
print()
print("Interpretation: these are points-per-unit-differential in each stat.")
print("A +1 unit advantage in cp_diff means home team averages 1 more CP/game.")
print()

full_params = model.params
full_pvals  = model.pvalues
full_tvals  = model.tvalues

sig = {col: '***' if full_pvals[col] < 0.01
            else '**'  if full_pvals[col] < 0.05
            else '*'   if full_pvals[col] < 0.10
            else ''
       for col in X_cols}

print(f"  {'Stat differential':<35} {'Coeff':>8}  {'t-stat':>7}  {'p':>7}  {'sig':>4}  Notes")
print(f"  {'-'*35} {'-'*8}  {'-'*7}  {'-'*7}  {'-'*4}  -----")
for col in X_cols:
    coeff = full_params[col]
    t     = full_tvals[col]
    p     = full_pvals[col]
    note  = ''
    if col == 'elo_diff':
        note = f'→ {coeff:.3f} pts/ELO pt'
    elif col == 'cp_diff':
        note = f'→ {coeff:.2f} pts per CP/game advantage'
    elif col == 'cl_diff':
        note = f'→ {coeff:.2f} pts per clearance/game advantage'
    elif col == 'i50_diff':
        note = f'→ {coeff:.2f} pts per inside50/game advantage'
    elif col == 'r50_diff':
        note = f'→ {coeff:.2f} pts per rebound50/game advantage'
    elif col == 'mi50_diff':
        note = f'→ {coeff:.2f} pts per marks-i50/game advantage'
    elif col == 'gconv_diff':
        note = f'→ {coeff:.1f} pts per 1.0 (100%) goal-conv advantage'
    print(f"  {col_labels.get(col, col):<35} {coeff:>8.3f}  {t:>7.2f}  {p:>7.4f}  {sig[col]:>4}  {note}")

print()
print(f"  Full model R² = {model.rsquared:.3f}  (adj R² = {model.rsquared_adj:.3f})")
print(f"  ELO-only  R² = {elo_model.rsquared:.3f}")
style_r2_add = model.rsquared - elo_model.rsquared
print(f"  Style vars add {style_r2_add:.3f} incremental R² on top of ELO")

# ─────────────────────────────────────────────────────────────────────────────
# 7. Typical stat differentials for scale context
# ─────────────────────────────────────────────────────────────────────────────
print()
print("──────────────────────────────────────────────────────────────────────────")
print("Scale context: typical matchup differentials (std dev across all games):")
print("──────────────────────────────────────────────────────────────────────────")
for col in style_cols:
    std = df[col].std()
    coeff = full_params[col]
    typical_pts = abs(coeff * std)
    print(f"  {col_labels[col]:<35} std={std:5.1f}  → typical pts impact: {typical_pts:4.1f}")

# ─────────────────────────────────────────────────────────────────────────────
# 8. Recommended config values
# ─────────────────────────────────────────────────────────────────────────────
print()
print("══════════════════════════════════════════════════════════════════════════")
print("RECOMMENDED T2_CONFIG VALUES  (only statistically significant vars)")
print("══════════════════════════════════════════════════════════════════════════")
print()
sig_cols = [c for c in style_cols if full_pvals[c] < 0.10]
insig_cols = [c for c in style_cols if full_pvals[c] >= 0.10]

for col in sig_cols:
    coeff = full_params[col]
    # Round to nearest 0.1 for config
    rounded = round(coeff * 10) / 10
    print(f"  {col:<20} → pts_per_unit = {rounded:.1f}  (raw coeff = {coeff:.3f}, p={full_pvals[col]:.3f})")

if insig_cols:
    print()
    print("  NOT recommended (p >= 0.10, use 0.0):")
    for col in insig_cols:
        coeff = full_params[col]
        print(f"    {col:<20} coeff = {coeff:.3f}, p={full_pvals[col]:.3f}")

print()
print("Notes:")
print("  - Apply as: style_pts_delta = Σ(coeff_i × (home_stat_i - away_stat_i))")
print("  - Use season averages as proxy for 'entering the match' style rating")
print("  - Cap total T2 adjustment at ±6 pts handicap to prevent over-fitting")
print("  - These are additive to the ELO baseline (ELO already captures quality)")
